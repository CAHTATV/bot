print("BOT VERSION: MERGED FINAL")
 
import requests
import time
import json
import threading
from datetime import datetime, timedelta, timezone
from telegram import Bot
from telegram.error import RetryAfter
from flask import Flask
 
# ================== КЛЮЧИ ==================
TOKEN = "8402411542:AAHDo48PYSv6SZ-ynkLA-UbS2Eb_rI83NYs"
API_KEY = "82a36cd1aba0ae5b0bc73dd442371916"
CHAT_ID = "532404021"
CHANNEL_ID = "@CAHTAFootboll"
 
CHANNELS = [CHAT_ID, CHANNEL_ID]
 
# ================== НАСТРОЙКИ ==================
MSK = timezone(timedelta(hours=3))
 
# Настройки сигнала на 1Т (предматчевые)
MATCHES_TO_CHECK = 7
GOAL_THRESHOLD = 0.70
SEND_BEFORE = 900          # Отправить за 15 минут до начала
CHECK_INTERVAL = 3600      # Обновлять список матчей каждый час
 
# Настройки live 2Т
LIVE_SECOND_HALF_THRESHOLD = 0.65
LIVE_CHECK_INTERVAL = 120  # Проверять live каждые 2 минуты
 
# ================== ФАЙЛЫ СОСТОЯНИЯ ==================
CACHE_FILE = "stats_cache.json"
SENT_FILE = "sent_matches.json"
LIVE_SENT_FILE = "live_sent.json"
 
# ================== ЗАГРУЗКА/СОХРАНЕНИЕ JSON ==================
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default
 
def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
 
# ================== ИНИЦИАЛИЗАЦИЯ ==================
bot = Bot(token=TOKEN)
stats_cache = load_json(CACHE_FILE, {})
sent_matches = set(load_json(SENT_FILE, []))
live_sent = set(load_json(LIVE_SENT_FILE, []))
match_queue = []
queue_lock = threading.Lock()
 
# ================== API ==================
def safe_request(url, params):
    while True:
        try:
            r = requests.get(
                url,
                headers={"x-apisports-key": API_KEY},
                params=params,
                timeout=20
            )
            if r.status_code == 429:
                print("Rate limit — ждём 60 сек...")
                time.sleep(60)
                continue
            return r.json()
        except Exception as e:
            print(f"Ошибка запроса: {e} — повтор через 15 сек")
            time.sleep(15)
 
# ================== КЭШ МАТЧЕЙ КОМАНДЫ ==================
def get_team_last_matches(team_id):
    now = time.time()
    key = str(team_id)
    if key in stats_cache and now - stats_cache[key]["time"] < 36000:
        return stats_cache[key]["data"]
 
    url = "https://v3.football.api-sports.io/fixtures"
    data = safe_request(url, {"team": team_id, "last": 20})
 
    stats_cache[key] = {"time": now, "data": data}
    save_json(CACHE_FILE, stats_cache)
    return data
 
# ================== СТАТИСТИКА 1Т (предматчевая) ==================
def team_first_half_goal_rate(team_id, is_home):
    """
    Считает долю матчей, в которых команда участвовала в голе в 1Т.
    is_home=True — смотрим только домашние матчи, is_home=False — гостевые.
    """
    fixtures = get_team_last_matches(team_id).get("response", [])
    goals = 0
    checked = 0
 
    for f in fixtures:
        try:
            teams = f.get("teams", {})
            ht = f["score"]["halftime"]
 
            if ht["home"] is None or ht["away"] is None:
                continue
 
            # Фильтруем по роли (дом/гость)
            if is_home and teams.get("home", {}).get("id") != team_id:
                continue
            if not is_home and teams.get("away", {}).get("id") != team_id:
                continue
 
            if ht["home"] > 0 or ht["away"] > 0:
                goals += 1
            checked += 1
 
            if checked >= MATCHES_TO_CHECK:
                break
        except:
            continue
 
    if checked < 3:
        return 0
 
    return goals / checked
 
def signal_level(pct):
    if pct >= 86:
        return "🔥🔥 СИЛЬНЫЙ"
    elif pct >= 76:
        return "⚡ СРЕДНИЙ"
    else:
        return "⚠️ СЛАБЫЙ"
 
# ================== ЗАГРУЗКА МАТЧЕЙ ДНЯ ==================
def load_matches():
    global match_queue
    print("LOAD MATCHES...")
 
    today = datetime.now(MSK).strftime("%Y-%m-%d")
    data = safe_request("https://v3.football.api-sports.io/fixtures", {"date": today})
    fixtures = data.get("response", [])
 
    new_queue = []
 
    for f in fixtures:
        try:
            status = f["fixture"]["status"]["short"]
            if status != "NS":
                continue
 
            match_id = str(f["fixture"]["id"])
            if match_id in sent_matches:
                continue
 
            home = f["teams"]["home"]["name"]
            away = f["teams"]["away"]["name"]
            home_id = f["teams"]["home"]["id"]
            away_id = f["teams"]["away"]["id"]
            start = datetime.fromisoformat(
                f["fixture"]["date"].replace("Z", "+00:00")
            ).astimezone(MSK)
 
            home_rate = team_first_half_goal_rate(home_id, True)
            away_rate = team_first_half_goal_rate(away_id, False)
            avg_rate = (home_rate + away_rate) / 2
 
            if avg_rate < GOAL_THRESHOLD:
                continue
 
            new_queue.append({
                "match_id": match_id,
                "home": home,
                "away": away,
                "time": start.isoformat(),
                "rate": round(avg_rate * 100, 1)
            })
 
        except Exception as e:
            print(f"Ошибка обработки матча: {e}")
            continue
 
    with queue_lock:
        match_queue = new_queue
 
    print(f"Загружено матчей с сигналом: {len(match_queue)}")
 
# ================== ОТПРАВКА TELEGRAM ==================
def send(text):
    for ch in CHANNELS:
        try:
            bot.send_message(chat_id=ch, text=text)
            time.sleep(1)
        except RetryAfter as e:
            print(f"RetryAfter: ждём {e.retry_after} сек")
            time.sleep(e.retry_after)
            bot.send_message(chat_id=ch, text=text)
        except Exception as e:
            print(f"Ошибка отправки в {ch}: {e}")
 
# ================== ЦИКЛ ОТПРАВКИ (1Т ПРЕДМАТЧ) ==================
def sender_loop():
    while True:
        now = datetime.now(MSK)
 
        with queue_lock:
            queue_copy = list(match_queue)
 
        for m in queue_copy:
            match_id = m["match_id"]
            if match_id in sent_matches:
                continue
 
            t = datetime.fromisoformat(m["time"])
            diff = (t - now).total_seconds()
 
            # Отправляем только в окне от SEND_BEFORE до 0 секунд до начала
            if diff > SEND_BEFORE or diff < 0:
                continue
 
            level = signal_level(m["rate"])
            text = (
                f"⚽️ СИГНАЛ НА 1 ТАЙМ\n\n"
                f"{m['home']} — {m['away']}\n"
                f"⏰ {t.strftime('%H:%M')}\n\n"
                f"📊 Забиваемость ({MATCHES_TO_CHECK} матчей): {m['rate']}%\n"
                f"🎯 Уровень сигнала: {level}\n\n"
                f"Ставка: Тотал 1Т Больше 0.5"
            )
 
            send(text)
            sent_matches.add(match_id)
            save_json(SENT_FILE, list(sent_matches))
            print(f"Отправлен сигнал: {m['home']} — {m['away']}")
 
        time.sleep(30)
 
# ================== ЦИКЛ ОБНОВЛЕНИЯ МАТЧЕЙ ==================
def loader_loop():
    while True:
        load_matches()
        time.sleep(CHECK_INTERVAL)
 
# ================== LIVE 2Т АНАЛИЗ ==================
def analyze_team_second_half(team_id):
    """
    Считает: в скольких матчах команды был счёт 0:0 в перерыве,
    и в скольких из них был гол во 2Т.
    """
    fixtures = get_team_last_matches(team_id).get("response", [])
    zero_zero = 0
    goal_after = 0
 
    for f in fixtures:
        score = f.get("score") or {}
        ht = score.get("halftime") or {}
        ft = score.get("fulltime") or {}
 
        if ht.get("home") == 0 and ht.get("away") == 0:
            zero_zero += 1
            if (ft.get("home", 0) or 0) + (ft.get("away", 0) or 0) > 0:
                goal_after += 1
 
    if zero_zero == 0:
        return 0
 
    return goal_after / zero_zero
 
def live_second_half_monitor():
    while True:
        try:
            data = safe_request(
                "https://v3.football.api-sports.io/fixtures",
                {"live": "all"}
            )
 
            for match in data.get("response", []):
                match_id = str(match["fixture"]["id"])
                if match_id in live_sent:
                    continue
 
                # Только матчи в перерыве
                if match["fixture"]["status"]["short"] != "HT":
                    continue
 
                # Только со счётом 0:0
                if match["goals"]["home"] != 0 or match["goals"]["away"] != 0:
                    continue
 
                home_id = match["teams"]["home"]["id"]
                away_id = match["teams"]["away"]["id"]
 
                home_prob = analyze_team_second_half(home_id)
                away_prob = analyze_team_second_half(away_id)
                final = (home_prob + away_prob) / 2
 
                if final >= LIVE_SECOND_HALF_THRESHOLD:
                    text = (
                        f"🚨 LIVE СИГНАЛ\n\n"
                        f"0:0 в перерыве\n"
                        f"{match['teams']['home']['name']} — {match['teams']['away']['name']}\n\n"
                        f"📊 Вероятность гола во 2Т: {final * 100:.1f}%\n"
                        f"🎯 Гол во 2 тайме — ДА"
                    )
                    send(text)
                    live_sent.add(match_id)
                    save_json(LIVE_SENT_FILE, list(live_sent))
                    print(f"Live сигнал: {match['teams']['home']['name']} — {match['teams']['away']['name']}")
 
        except Exception as e:
            print(f"Ошибка live мониторинга: {e}")
 
        time.sleep(LIVE_CHECK_INTERVAL)
 
# ================== FLASK KEEP-ALIVE ==================
app = Flask(__name__)
 
@app.route("/")
def home():
    return "BOT WORKING", 200
 
def run_web():
    app.run(host="0.0.0.0", port=8080)
 
# ================== ЗАПУСК ==================
threading.Thread(target=run_web, daemon=True).start()
threading.Thread(target=loader_loop, daemon=True).start()
threading.Thread(target=sender_loop, daemon=True).start()
threading.Thread(target=live_second_half_monitor, daemon=True).start()
 
print("BOT STARTED...")
 
while True:
    print("BOT KEEP ALIVE...")
    time.sleep(60)