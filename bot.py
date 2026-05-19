print("BOT VERSION: LIVE FIX 1T STRONG")

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

CHANNELS = [CHAT_ID, CHANNEL_ID]

# ================== НАСТРОЙКИ ==================
LIVE_SECOND_HALF_THRESHOLD = 0.65
LIVE_CHECK_INTERVAL = 120

MSK = timezone(timedelta(hours=3))
bot = Bot(token=TOKEN)

CACHE_FILE = "stats_cache.json"
QUEUE_FILE = "matches_queue.json"
SENT_FILE = "sent_matches.json"
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
sent_matches = set(load_json(SENT_FILE, []))
live_sent = set(load_json(LIVE_SENT_FILE, []))

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

def get_team_last_matches(team_id):
    now = time.time()
    if team_id in stats_cache and now - stats_cache[team_id]["time"] < 36000:
        return stats_cache[team_id]["data"]

    url = "https://v3.football.api-sports.io/fixtures"
    data = safe_request(url, {"team": team_id, "last": 30})

    stats_cache[team_id] = {"time": now, "data": data}
    save_json(CACHE_FILE, stats_cache)
    return data

# ================== ГЛАВНАЯ ЛОГИКА 1Т ==================

def last10_first_half_goal_pct(team_id, is_home):
    fixtures = get_team_last_matches(team_id).get("response", [])
    checked = 0
    hits = 0

    for f in fixtures:
        teams = f.get("teams", {})
        score = f.get("score", {})
        ht = score.get("halftime") or {}

        ht_home = ht.get("home")
        ht_away = ht.get("away")

        if ht_home is None or ht_away is None:
            continue

        if is_home and teams.get("home", {}).get("id") != team_id:
            continue
        if not is_home and teams.get("away", {}).get("id") != team_id:
            continue

        checked += 1

        if (ht_home + ht_away) > 0:
            hits += 1

        if checked >= 10:
            break

    if checked < 5:
        return 0

    return hits / checked

def calc_signal_1t(home_id, away_id):
    home_pct = last10_first_half_goal_pct(home_id, True)
    away_pct = last10_first_half_goal_pct(away_id, False)
    return int(((home_pct + away_pct) / 2) * 100)

# ================== TELEGRAM ==================
def send(text):
    for ch in CHANNELS:
        try:
            bot.send_message(chat_id=ch, text=text)
        except RetryAfter as e:
            time.sleep(e.retry_after)

# ================== LIVE 2Т ==================
def analyze_team_second_half(team_id):
    fixtures = get_team_last_matches(team_id)
    zero_zero = 0
    goal_after = 0

    for f in fixtures.get("response", []):
        score = f.get("score") or {}
        ht = score.get("halftime") or {}
        ft = score.get("fulltime") or {}

        if ht.get("home") == 0 and ht.get("away") == 0:
            zero_zero += 1
            if (ft.get("home", 0) + ft.get("away", 0)) > 0:
                goal_after += 1

    if zero_zero == 0:
        return 0

    return goal_after / zero_zero

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

            final = (analyze_team_second_half(home) + analyze_team_second_half(away)) / 2

            if final >= LIVE_SECOND_HALF_THRESHOLD:
                text = f"""🚨 LIVE СИГНАЛ

0:0 в перерыве
{match['teams']['home']['name']} — {match['teams']['away']['name']}

📊 Вероятность гола во 2Т: {final*100:.1f}%
🎯 Гол во 2 тайме — ДА
"""
                send(text)
                live_sent.add(match_id)
                save_json(LIVE_SENT_FILE, list(live_sent))

        time.sleep(LIVE_CHECK_INTERVAL)

threading.Thread(target=live_second_half_monitor, daemon=True).start()

while True:
    safe_request("https://v3.football.api-sports.io/timezone", {})
    print("BOT KEEP ALIVE...")
    time.sleep(60)