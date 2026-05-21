print("BOT VERSION: MERGED + DAILY REPORT + RU LOCALE (REFACTORED)")
 
import requests
import time
import json
import threading
from datetime import datetime, timezone, timedelta

from telegram import Bot
from telegram.error import RetryAfter
 
# Импортируем словари переводов и списки лиг из внешнего файла
import locale_data
from locale_data import TEAM_RU, LEAGUE_RU, COUNTRY_FLAGS

# ================== КЛЮЧИ ==================
TOKEN = "8402411542:AAHDo48PYSv6SZ-ynkLA-UbS2Eb_rI83NYs"
API_KEY = "82a36cd1aba0ae5b0bc73dd442371916"
CHAT_ID = "532404021"
CHANNEL_ID = "@CAHTAFootboll"
 
CHANNELS = [CHAT_ID, CHANNEL_ID]
 
# ================== НАСТРОЙКИ ==================
MSK = timezone(timedelta(hours=3))

MATCHES_TO_CHECK = 7
GOAL_THRESHOLD = 0.65      
MIN_ODDS = 1.30            # Минимальный КФ для старта мониторинга
CHECK_INTERVAL = 7200      # Обновление списка матчей раз в 2 часа
ODDS_CHECK_INTERVAL = 60   # Мониторинг КФ каждую минуту
 
LIVE_SECOND_HALF_THRESHOLD = 0.60 
LIVE_CHECK_INTERVAL = 120
 
# ================== ФАЙЛЫ СОСТОЯНИЯ ==================
CACHE_FILE = "stats_cache.json"
SENT_FILE = "sent_matches.json"
LIVE_SENT_FILE = "live_sent.json"
TRACKED_FILE = "tracked_matches.json"
REPORT_SENT_FILE = "report_sent.json"
 
# ================== ФУНКЦИИ ЛОКАЛИЗАЦИИ ==================
def translate_team(name):
    return locale_data.TEAM_RU.get(name, name)
 
def translate_league(name):
    return locale_data.LEAGUE_RU.get(name, name)
 
def translate_country(name):
    return locale_data.COUNTRY_RU.get(name, name)
 
def get_flag(country):
    return locale_data.COUNTRY_FLAGS.get(country, "🌍")
 
def format_league_line(country, league_name):
    flag = get_flag(country)
    country_ru = translate_country(country)
    league_ru = translate_league(league_name)
    return f"{flag} {country_ru} · {league_ru}"
 
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
tracked_matches = load_json(TRACKED_FILE, [])
report_sent = set(load_json(REPORT_SENT_FILE, []))
match_queue = []

queue_lock = threading.Lock()
tracked_lock = threading.Lock()
cache_lock = threading.Lock()
 
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
 
CACHE_TTL = 36000        
CACHE_MAX_AGE = 172800   

# ================== КЭШ МАТЧЕЙ КОМАНДЫ ==================
def cleanup_cache():
    now = time.time()
    old_keys = [k for k, v in stats_cache.items() if now - v.get("time", 0) > CACHE_MAX_AGE]
    for k in old_keys:
        del stats_cache[k]
    if old_keys:
        print(f"🧹 Кэш очищен: удалено {len(old_keys)} устаревших записей")

def get_team_last_matches(team_id):
    now = time.time()
    key = str(team_id)
    
    with cache_lock:
        if key in stats_cache and now - stats_cache[key]["time"] < CACHE_TTL:
            return stats_cache[key]["data"]

    url = "https://v3.football.api-sports.io/fixtures"
    data = safe_request(url, {"team": team_id, "last": 20})

    with cache_lock:
        stats_cache[key] = {"time": now, "data": data}
        cleanup_cache()
        save_json(CACHE_FILE, stats_cache)
    return data
 
# ================== СТАТИСТИКА 1Т ==================
def team_first_half_goal_rate(team_id, is_home):
    fixtures = get_team_last_matches(team_id).get("response", [])
    goals = 0
    checked = 0
 
    for f in fixtures:
        try:
            teams = f.get("teams", {})
            ht = f["score"]["halftime"]
 
            if ht["home"] is None or ht["away"] is None:
                continue
 
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
 
def first_half_concede_pct(team_id, is_home):
    fixtures = get_team_last_matches(team_id).get("response", [])
    checked = 0
    concede = 0

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

        if is_home and ht_away > 0:
            concede += 1
        if not is_home and ht_home > 0:
            concede += 1

        if checked >= 7:
            break

    if checked < 5:
        return 0

    return concede / checked

def first_half_scored_pct(team_id, is_home):
    fixtures = get_team_last_matches(team_id).get("response", [])
    checked = 0
    scored = 0

    for f in fixtures:
        teams = f.get("teams", {})
        score = f.get("score", {})
        ht = score.get("halftime") or {}

        if is_home and teams.get("home", {}).get("id") != team_id:
            continue
        if not is_home and teams.get("away", {}).get("id") != team_id:
            continue

        goals = ht.get("home") if is_home else ht.get("away")

        if goals is None:
            continue

        checked += 1
        if goals > 0:
            scored += 1

        if checked >= 7:
            break

    if checked < 5:
        return 0

    return scored / checked

def get_avg_first_goal_minute(team_id, is_home):
    fixtures = get_team_last_matches(team_id).get("response", [])
    minutes = []
    checked = 0

    for f in fixtures:
        teams = f.get("teams", {})
        if is_home and teams.get("home", {}).get("id") != team_id:
            continue
        if not is_home and teams.get("away", {}).get("id") != team_id:
            continue

        events = f.get("events") or []
        first_goal_in_match = None
        
        for e in events:
            if e.get("type") == "Goal":
                m = e.get("time", {}).get("elapsed")
                if m and m <= 45:
                    if first_goal_in_match is None or m < first_goal_in_match:
                        first_goal_in_match = m

        if first_goal_in_match is not None:
            minutes.append(first_goal_in_match)
        
        checked += 1
        if checked >= 7:
            break

    if not minutes:
        return 35 

    return sum(minutes) / len(minutes)

# ================== ИТОГОВЫЙ РАСЧЁТ СИГНАЛА 1Т ==================
def calc_signal_1t(home_id, away_id, league_id):
    home_goal = team_first_half_goal_rate(home_id, True)
    away_goal = team_first_half_goal_rate(away_id, False)
    base = (home_goal + away_goal) / 2

    home_attack = first