print("BOT VERSION: LIVE FIX 15.05")
# ================== VALUE BETTING + LIVE 2ND HALF ==================

import requests
import time
import json
import threading
from datetime import datetime, timedelta, timezone
from telegram import Bot
from telegram.error import RetryAfter

# ================== КЛЮЧИ ==================
TOKEN = "8402411542:AAHDo48PYSv6SZ-ynkLA-UbS2Eb_rI83NYs"
API_KEY = "82a36cd1aba0ae5b0bc73dd442371916"
CHAT_ID = "532404021"
CHANNEL_ID = "@CAHTAFootboll"

# ================== НАСТРОЙКИ ==================
ALLOWED_LEAGUES = [39, 61, 135, 140, 78, 88]
MIN_HOME_HITS = 8
MIN_AWAY_HITS = 5
MIN_VALUE_PERCENT = 12
LIVE_SECOND_HALF_THRESHOLD = 0.65
LIVE_CHECK_INTERVAL = 120

KELLY_FRACTION = 0.25
BANKROLL = 10000

MSK = timezone(timedelta(hours=3))
bot = Bot(token=TOKEN)

# ================== ФАЙЛЫ ==================
CACHE_FILE = "stats_cache.json"
QUEUE_FILE = "matches_queue.json"
SENT_FILE = "sent_matches.json"
BANKROLL_FILE = "bankroll.json"
LIVE_SENT_FILE = "live_sent.json"

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

stats_cache = load_json(CACHE_FILE, {})
match_queue = load_json(QUEUE_FILE, [])
sent_matches = set(load_json(SENT_FILE, []))
live_sent = set(load_json(LIVE_SENT_FILE, []))
bankroll_data = load_json(BANKROLL_FILE, {"amount": BANKROLL})

# ================== API ==================
def safe_request(url, params):
    while True:
        try:
            r = requests.get(url, headers={"x-apisports-key": API_KEY}, params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(60)
                continue
            return r.json()
        except:
            time.sleep(15)

# ================== СТАТИСТИКА ==================
def get_team_last_matches(team_id):
    now = time.time()
    if team_id in stats_cache and now - stats_cache[team_id]["time"] < 36000:
        return stats_cache[team_id]["data"]

    url = "https://v3.football.api-sports.io/fixtures"
    data = safe_request(url, {"team": team_id, "last": 30})

    stats_cache[team_id] = {"time": now, "data": data}
    save_json(CACHE_FILE, stats_cache)
    return data

def team_scores_first_half(fixtures):
    count = 0
    for f in fixtures.get("response", []):
        ht = f["score"]["halftime"]
        if ht["home"] > 0 or ht["away"] > 0:
            count += 1
    return count

# ================== CALC SIGNAL 1T ==================
def calc_signal_1t(home_id, away_id):

    def team_1t_percent(team_id, home=True):
        fixtures = get_team_last_matches(team_id).get("response", [])[:20]

        hits = 0
        total = 0

        for f in fixtures:
            is_home = f["teams"]["home"]["id"] == team_id
            if is_home != home:
                continue

            ht = f["score"]["halftime"]
            if ht["home"] > 0 or ht["away"] > 0:
                hits += 1
            total += 1

        if total == 0:
            return 0.5

        return hits / total

    home_home = team_1t_percent(home_id, True)
    away_away = team_1t_percent(away_id, False)

    base = (home_home + away_away) / 2
    signal = int(base * 100)

    return max(70, min(signal, 100))


def signal_level(sig):
    if sig >= 91:
        return "🔥 СИЛЬНЫЙ"
    elif sig >= 81:
        return "⚡ СРЕДНИЙ"
    return "📊 СЛАБЫЙ"

# ================== ODDS ==================
def get_match_odds(match_id):
    url = "https://v3.football.api-sports.io/odds"
    data = safe_request(url, {"fixture": match_id, "bookmaker": 8})

    for bookmaker in data.get("response", [{}])[0].get("bookmakers", []):
        for bet in bookmaker.get("bets", []):
            if "Both Teams Score" in bet.get("name", ""):
                for v in bet.get("values", []):
                    if v["value"] == "Yes":
                        return float(v["odd"])
    return None

def calculate_value(prob, odds):
    fair = 1 / prob
    return ((odds - fair) / fair) * 100

def kelly(prob, odds, bankroll):
    b = odds - 1
    q = 1 - prob
    k = (prob * b - q) / b
    return max(0, bankroll * k * KELLY_FRACTION)

# ================== LIVE 2 ТАЙМ АНАЛИЗ ==================
def analyze_team_second_half(team_id):
    fixtures = get_team_last_matches(team_id)

    zero_zero = 0
    goal_after = 0
    total_goals = 0

    for f in fixtures.get("response", []):
        ht = f.get("score", {}).get("halftime", {})
        ft = f.get("score", {}).get("fulltime", {})

        ht_home = ht.get("home") if ht.get("home") is not None else 0
        ht_away = ht.get("away") if ht.get("away") is not None else 0
        ft_home = ft.get("home") if ft.get("home") is not None else 0
        ft_away = ft.get("away") if ft.get("away") is not None else 0

        # только матчи с валидными данными
        if ht_home == 0 and ht_away == 0:
            zero_zero += 1

            goals = (ft_home - ht_home) + (ft_away - ht_away)
            total_goals += goals

            if goals > 0:
                goal_after += 1

    if zero_zero == 0:
        return 0, 0

    return goal_after / zero_zero, total_goals / zero_zero

# ================== TELEGRAM ==================
def send(text):
    for ch in CHANNELS:
        try:
            bot.send_message(chat_id=ch, text=text)
        except RetryAfter as e:
            time.sleep(e.retry_after)

# ================== АНАЛИЗ МАТЧА ==================
def analyze_match(match):
    league_id = match["league"]["id"]
    if league_id not in ALLOWED_LEAGUES:
        return False, ""

    home_id = match["teams"]["home"]["id"]
    away_id = match["teams"]["away"]["id"]

    # --- НОВЫЙ СИГНАЛ 1Т ---
    sig = calc_signal_1t(home_id, away_id)
    level = signal_level(sig)

    home_hits = team_scores_first_half(get_team_last_matches(home_id))
    away_hits = team_scores_first_half(get_team_last_matches(away_id))

    if home_hits < MIN_HOME_HITS or away_hits < MIN_AWAY_HITS:
        return False, ""

    prob = (home_hits/30) * (away_hits/30)
    odds = get_match_odds(match["fixture"]["id"])
    if not odds:
        return False, ""

    value = calculate_value(prob, odds)

    if value >= MIN_VALUE_PERCENT:
        bet = kelly(prob, odds, bankroll_data["amount"])
        return True, (prob, odds, bet, value, sig, level)

    return False, ""

# ================== ЗАГРУЗКА МАТЧЕЙ ==================
def load_matches():
    url = "https://v3.football.api-sports.io/fixtures"
    date = datetime.now(MSK).strftime("%Y-%m-%d")
    data = safe_request(url, {"date": date})
    for m in data.get("response", []):
        match_id = m["fixture"]["id"]
        if str(match_id) in sent_matches:
            continue
        ok, info = analyze_match(m)
        if not ok:
            continue
        # Пробуем распаковать данные из info
        if isinstance(info, dict):
            odds = info.get("odds")
            bet = info.get("bet")
            value = info.get("value")
            sig = info.get("sig")
            level = info.get("level")
        else:
            # Предполагаем кортеж: (odds, bet, value, sig, level)
            try:
                odds, bet, value, sig, level = info
            except Exception:
                continue
        start = datetime.fromisoformat(
            m["fixture"]["date"].replace("Z", "+00:00")
        ).astimezone(MSK)
        match_queue.append({
            "id": match_id,
            "time": start.isoformat(),
            "home": m["teams"]["home"]["name"],
            "away": m["teams"]["away"]["name"],
            "odds": odds,
            "bet": round(bet, 2) if isinstance(bet, (int, float)) else bet,
            "value": round(value, 1) if isinstance(value, (int, float)) else value,
            "sig": sig,
            "level": level
        })

    save_json(QUEUE_FILE, match_queue)

# ================== ОТПРАВКА ПРЕМАТЧ ==================
def sender_loop():
    now = datetime.now(MSK)
    for m in match_queue[:]:
        t = datetime.fromisoformat(m["time"])
        diff = (t - now).total_seconds()

        text = f"""⚽️ VALUE BET + 1Т SIGNAL

{m['home']} — {m['away']}

📊 Сигнал 1Т: {m['sig']}% | {m['level']}

💰 Ставка: Обе забьют ДА
📈 Кэф: {m['odds']}
💵 Сумма: {m['bet']}
📊 Value: {m['value']}%
"""
            send(text)
            sent_matches.add(str(m["id"]))
            match_queue.remove(m)
            save_json(SENT_FILE, list(sent_matches))
            save_json(QUEUE_FILE, match_queue)

# ================== LIVE МОНИТОР ==================
def live_second_half_monitor():
    while True:
        data = safe_request(
            "https://v3.football.api-sports.io/fixtures",
            {"live": "all"}
        )

        for match in data.get("response", []):
            match_id = str(match["fixture"]["id"])
            if match_id in live_sent:
                continue

            if match["fixture"]["status"]["short"] != "HT":
                continue

            if match["goals"]["home"] != 0 or match["goals"]["away"] != 0:
                continue

            home = match["teams"]["home"]["id"]
            away = match["teams"]["away"]["id"]

            p1, _ = analyze_team_second_half(home)
            p2, _ = analyze_team_second_half(away)

            final = (p1 + p2) / 2

            if final >= LIVE_SECOND_HALF_THRESHOLD:
                text = f"""🚨 LIVE СИГНАЛ

0:0 в перерыве
{match['teams']['home']['name']} — {match['teams']['away']['name']}

📊 Вероятность гола во 2Т: {final*100:.1f}%
🎯 Ставка: Гол во 2 тайме — ДА
"""
                send(text)
                live_sent.add(match_id)
                save_json(LIVE_SENT_FILE, list(live_sent))

        time.sleep(LIVE_CHECK_INTERVAL)

# ================== ЗАПУСК ==================
threading.Thread(target=live_second_half_monitor, daemon=True).start()

last_load = 0

while True:
    if time.time() - last_load > 21600:
        load_matches()
        last_load = time.time()

    print("BOT KEEP ALIVE...")
    time.sleep(300)