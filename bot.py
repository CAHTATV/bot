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


# ================== 1 ТАЙМ ПОЛНАЯ СТАТИСТИКА ==================

def team_1t_stats(team_id, is_home):
    fixtures = get_team_last_matches(team_id).get("response", [])

    played = 0
    scored = 0
    conceded = 0
    total_goals = 0
    last5 = []

    for f in fixtures:
        teams = f.get("teams", {})
        score = f.get("score", {})
        ht = score.get("halftime") or {}

        ht_home = ht.get("home")
        ht_away = ht.get("away")

        # защита от кривых данных API
        if ht_home is None or ht_away is None:
            continue

        if is_home and teams.get("home", {}).get("id") != team_id:
            continue
        if not is_home and teams.get("away", {}).get("id") != team_id:
            continue

        played += 1

        goals_for = ht_home if is_home else ht_away
        goals_against = ht_away if is_home else ht_home

        total_goals += goals_for + goals_against

        if goals_for > 0:
            scored += 1
        if goals_against > 0:
            conceded += 1

        last5.append(1 if goals_for > 0 else 0)

        if len(last5) > 5:
            last5.pop(0)

    if played == 0:
        return {
            "score_pct": 0,
            "concede_pct": 0,
            "avg_total": 0,
            "last5": 0
        }

    return {
        "score_pct": scored / played,
        "concede_pct": conceded / played,
        "avg_total": total_goals / played,
        "last5": sum(last5) / len(last5) if last5 else 0
    }

# ================== CALC SIGNAL 1T ==================
# ================== CALC SIGNAL 1T ==================

def calc_signal_1t(home_id, away_id):
    home = team_1t_stats(home_id, True)
    away = team_1t_stats(away_id, False)

    # базовая вероятность что в 1Т будет гол
    base = (
        home["score_pct"] +
        away["score_pct"] +
        home["concede_pct"] +
        away["concede_pct"]
    ) / 4

    # усиление средним тоталом
    total_boost = (home["avg_total"] + away["avg_total"]) / 4

    # усиление формой последних 5
    form_boost = (home["last5"] + away["last5"]) / 2

    signal = base * 0.6 + total_boost * 0.2 + form_boost * 0.2

    sig_percent = int(signal * 100)

    return max(70, min(sig_percent, 100))


def signal_level(sig):
    if sig >= 91:
        return "🔥 СИЛЬНЫЙ"
    elif sig >= 81:
        return "⚡ СРЕДНИЙ"
    return "📊 СЛАБЫЙ"

def get_btts_odds(fixture_id):
    data = safe_request(
        "https://v3.football.api-sports.io/odds",
        {"fixture": fixture_id}
    ).get("response", [])

    for bookmaker in data:
        for bet in bookmaker.get("bets", []):
            if bet.get("name") == "Both Teams Score":
                for value in bet.get("values", []):
                    if value.get("value") == "Yes":
                        try:
                            return float(value.get("odd"))
                        except:
                            return None
    return None
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

        score = f.get("score") or {}
        ht = score.get("halftime") or {}
        ft = score.get("fulltime") or {}

        ht_home = ht.get("home") or 0
        ht_away = ht.get("away") or 0
        ft_home = ft.get("home") or 0
        ft_away = ft.get("away") or 0

        # пропускаем матчи без финального счёта (ещё идут или кривые)
        if ft_home == 0 and ft_away == 0:
            continue

        # анализ только матчей где 0:0 к перерыву
        if ht_home == 0 and ht_away == 0:
            zero_zero += 1

            goals_after = (ft_home - ht_home) + (ft_away - ht_away)
            total_goals += goals_after

            if goals_after > 0:
                goal_after += 1

    if zero_zero == 0:
        return 0, 0

    prob_goal_after = goal_after / zero_zero
    avg_goals_after = total_goals / zero_zero

    return prob_goal_after, avg_goals_after

# ================== TELEGRAM ==================
def send(text):
    for ch in CHANNELS:
        try:
            bot.send_message(chat_id=ch, text=text)
        except RetryAfter as e:
            time.sleep(e.retry_after)

# ================== АНАЛИЗ МАТЧА ==================
def analyze_match(m):
    home_id = m["teams"]["home"]["id"]
    away_id = m["teams"]["away"]["id"]

    home_games = safe_request(
        "https://v3.football.api-sports.io/fixtures",
        {"team": home_id, "last": 20}
    ).get("response", [])

    away_games = safe_request(
        "https://v3.football.api-sports.io/fixtures",
        {"team": away_id, "last": 20}
    ).get("response", [])

    if len(home_games) < 10 or len(away_games) < 10:
        return False, None

    # --- Домашняя статистика хозяев
    home_scored_home = 0
    home_conceded_home = 0
    home_played_home = 0

    for g in home_games:
        if g["teams"]["home"]["id"] == home_id:
            home_played_home += 1
            home_goals = g["goals"]["home"] or 0
            away_goals = g["goals"]["away"] or 0

            if home_goals > 0:
                home_scored_home += 1
            if away_goals > 0:
                home_conceded_home += 1

    # --- Гостевая статистика гостей
    away_scored_away = 0
    away_conceded_away = 0
    away_played_away = 0

    for g in away_games:
        if g["teams"]["away"]["id"] == away_id:
            away_played_away += 1
            home_goals = g["goals"]["home"] or 0
            away_goals = g["goals"]["away"] or 0

            if away_goals > 0:
                away_scored_away += 1
            if home_goals > 0:
                away_conceded_away += 1

    if home_played_home < 5 or away_played_away < 5:
        return False, None

    # --- Проценты
    p_home_score = home_scored_home / home_played_home
    p_home_concede = home_conceded_home / home_played_home

    p_away_score = away_scored_away / away_played_away
    p_away_concede = away_conceded_away / away_played_away

    # --- Форма последних 5 игр
    def last5_form(games, team_id, is_home):
        cnt = 0
        checked = 0

        for g in games[:5]:
            home_goals = g["goals"]["home"] or 0
            away_goals = g["goals"]["away"] or 0

            if is_home and g["teams"]["home"]["id"] == team_id:
                checked += 1
                if home_goals > 0:
                    cnt += 1

            if not is_home and g["teams"]["away"]["id"] == team_id:
                checked += 1
                if away_goals > 0:
                    cnt += 1

        if checked == 0:
            return 0

        return cnt / checked

    form_home = last5_form(home_games, home_id, True)
    form_away = last5_form(away_games, away_id, False)

    # --- Вероятность BTTS
    prob_home_scores = (p_home_score + p_away_concede) / 2
    prob_away_scores = (p_away_score + p_home_concede) / 2
    prob_btts = (prob_home_scores + prob_away_scores) / 2

    # --- Учет формы
    prob_btts = prob_btts * 0.7 + ((form_home + form_away) / 2) * 0.3

    # --- Усиление через 1Т сигнал
    sig_1t = calc_signal_1t(home_id, away_id)
    prob_btts = prob_btts * (1 + (sig_1t - 70) / 300)

    if prob_btts < 0.55:
        return False, None

    odds = get_btts_odds(m["fixture"]["id"])
    if not odds or odds < 1.4:
        return False, None

    implied = 1 / odds
    value = (prob_btts - implied) / implied * 100

    if value < 5:
        return False, None

    # --- Келли
    kelly = (prob_btts * odds - 1) / (odds - 1)
    bet = max(1, round(kelly * 10, 2))

    # --- Уровни сигнала
    sig = int(prob_btts * 100)

    if sig >= 91:
        level = "🔥 СИЛЬНЫЙ"
    elif sig >= 81:
        level = "💰 СРЕДНИЙ"
    else:
        level = "📊 СЛАБЫЙ"

    return True, {
        "odds": odds,
        "bet": bet,
        "value": value,
        "sig": sig,
        "level": level
    }

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