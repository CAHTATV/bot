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
MIN_ODDS = 1.30            
CHECK_INTERVAL = 7200      
ODDS_CHECK_INTERVAL = 60   
 
LIVE_SECOND_HALF_THRESHOLD = 0.60 
LIVE_CHECK_INTERVAL = 120

# Настройки для лайва 1-го тайма
LIVE_1T_CHECK_INTERVAL = 90  # Проверка лайва 1Т каждые 1.5 минуты
 
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
        if is_home housing and teams.get("home", {}).get("id") != team_id:
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

    home_attack = first_half_scored_pct(home_id, True)
    away_attack = first_half_scored_pct(away_id, False)
    home_concede = first_half_concede_pct(home_id, True)
    away_concede = first_half_concede_pct(away_id, False)

    cross_1 = home_attack * away_concede   
    cross = (cross_1 + (away_attack * home_concede)) / 2

    if league_id in locale_data.FAST_LEAGUES:
        league_boost = 0.12
    elif league_id in locale_data.SLOW_LEAGUES:
        league_boost = -0.05 
    else:
        league_boost = 0

    home_avg_time = get_avg_first_goal_minute(home_id, True)
    away_avg_time = get_avg_first_goal_minute(away_id, False)
    avg_first_goal_time = (home_avg_time + away_avg_time) / 2

    if avg_first_goal_time <= 25:
        time_boost = 0.08     
    elif avg_first_goal_time >= 38:
        time_boost = -0.05    
    else:
        time_boost = 0

    final = base * 0.4 + cross * 0.4 + league_boost + time_boost
    return int(max(0, min(final, 1.0)) * 100)

def signal_level(pct):
    if pct >= 82:
        return "🔥🔥 СИЛЬНЫЙ"
    elif pct >= 72:
        return "⚡ СРЕДНИЙ"
    else:
        return "⚠️ СЛАБЫЙ"
 
# ================== ПОЛУЧЕНИЕ КОЭФФИЦИЕНТОВ ==================
def get_first_half_over_odds(fixture_id):
    try:
        data = safe_request(
            "https://v3.football.api-sports.io/odds",
            {"fixture": fixture_id, "bookmaker": 8, "bet": 23}
        )
        for item in data.get("response", []):
            for bm in item.get("bookmakers", []):
                for bet in bm.get("bets", []):
                    for odd in bet.get("values", []):
                        val = odd.get("value", "")
                        if "Over" in val and "0.5" in val:
                            return float(odd.get("odd", 0))
    except Exception as e:
        print(f"Ошибка получения КФ для {fixture_id}: {e}")
    return None

def get_live_1t_over_odds(fixture_id):
    try:
        data = safe_request(
            "https://v3.football.api-sports.io/odds/live",
            {"fixture": fixture_id, "bet": 23}
        )
        for item in data.get("response", []):
            for bm in item.get("bookmakers", []):
                for bet in bm.get("bets", []):
                    for odd in bet.get("values", []):
                        val = odd.get("value", "")
                        if "Over" in val and "0.5" in val:
                            return float(odd.get("odd", 0))
    except Exception as e:
        print(f"Ошибка получения live КФ 1Т: {e}")
    return None
 
# ================== ЗАГРУЗКА МАТЧЕЙ ДНЯ ==================
def load_matches():
    global match_queue
    print("LOAD MATCHES...")

    today = datetime.now(MSK).strftime("%Y-%m-%d")
    data = safe_request("https://v3.football.api-sports.io/fixtures", {"date": today})
    fixtures = data.get("response", [])
    
    print(f"Всего матчей в API на сегодня: {len(fixtures)}")

    with queue_lock:
        existing_ids = {m["match_id"] for m in match_queue}

    added = 0
    filtered_by_threshold = 0
    
    for f in fixtures:
        try:
            status = f["fixture"]["status"]["short"]
            if status != "NS":
                continue

            match_id = str(f["fixture"]["id"])
            if match_id in sent_matches:
                continue
            if match_id in existing_ids:
                continue  

            home_raw = f["teams"]["home"]["name"]
            away_raw = f["teams"]["away"]["name"]
            home_id = f["teams"]["home"]["id"]
            away_id = f["teams"]["away"]["id"]

            country = f.get("league", {}).get("country", "")
            league_name = f.get("league", {}).get("name", "")
            league_id = f.get("league", {}).get("id", 0)

            start = datetime.fromisoformat(
                f["fixture"]["date"].replace("Z", "+00:00")
            ).astimezone(MSK)

            if start <= datetime.now(MSK):
                continue

            signal_pct = calc_signal_1t(home_id, away_id, league_id)
            if signal_pct < int(GOAL_THRESHOLD * 100):
                filtered_by_threshold += 1
                continue

            with queue_lock:
                match_queue.append({
                    "match_id": match_id,
                    "home": home_raw,
                    "away": away_raw,
                    "home_ru": translate_team(home_raw),
                    "away_ru": translate_team(away_raw),
                    "country": country,
                    "league": league_name,
                    "time": start.strftime("%H:%M"),
                    "time_iso": start.isoformat(),
                    "date": today,
                    "rate": signal_pct
                })
            existing_ids.add(match_id)
            added += 1
            print(f"➕ Мониторинг КФ: {translate_team(home_raw)} — {translate_team(away_raw)} {signal_pct}%")

        except Exception as e:
            print(f"Ошибка обработки матча: {e}")
            continue

    print(f"Добавлено новых матчей: {added} | Отсеяно по порогу вероятности: {filtered_by_threshold} | Всего в очереди: {len(match_queue)}")

# ================== МОНИТОРИНГ КФ И ОТПРАВКА СИГНАЛА ==================
def odds_monitor_loop():
    while True:
        now = datetime.now(MSK)

        with queue_lock:
            queue_copy = list(match_queue)

        if queue_copy:
            print(f"🔍 Мониторинг КФ: {len(queue_copy)} матчей в очереди")

        for m in queue_copy:
            match_id = m["match_id"]

            if match_id in sent_matches:
                with queue_lock:
                    match_queue[:] = [x for x in match_queue if x["match_id"] != match_id]
                continue

            t = datetime.fromisoformat(m["time_iso"])
            time_until_match = (t - now).total_seconds()
            
            odds = get_first_half_over_odds(match_id)
            print(f"   {m['home_ru']} — {m['away_ru']}: КФ={odds} (нужно ≥{MIN_ODDS}), до начала: {time_until_match//60} мин")

            time.sleep(1.5)

            force_send = False
            if odds is None and time_until_match <= 180 and time_until_match > -60:
                force_send = True
                odds_str = f"В лайве (от {MIN_ODDS})"
            elif odds is not None and odds >= MIN_ODDS:
                force_send = True
                odds_str = f"{odds:.2f}"
            else:
                if time_until_match <= 0:
                    # ОПТИМИЗАЦИЯ: НЕ удаляем матч, если КФ pre-match не нашли. 
                    # Мы убираем его из прематч-списка, но даем шанс потоку лайва поймать его на 10-й минуте!
                    with queue_lock:
                        match_queue[:] = [x for x in match_queue if x["match_id"] != match_id]
                    print(f"⏰ Прематч закончен, игра {m['home_ru']} передана в Live 1Т...")
                continue

            if force_send:
                league_line = format_league_line(m.get("country", ""), m.get("league", ""))
                level = signal_level(m["rate"])

                msg_lines = [
                    f"🟢 *НОВЫЙ СИГНАЛ* | {league_line}",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    f"⚽ *МАТЧ:* {m['home_ru']} — {m['away_ru']}",
                    f"⏰ *НАЧАЛО:* `{m['time']}` МСК",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    f"📈 *Аналитика:* {m['rate']}% (Уровень: {level})",
                    f"💰 *Стартовый КФ:* `{odds_str}`",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    "🔥 *СТАВКА:* `Тотал 1-го тайма Больше (0.5)`",
                    "⚠️ _Рекомендуемый флэт: 1-2% от банка_",
                ]
                text = "\n".join(msg_lines)

                send(text)
                
                with queue_lock:
                    sent_matches.add(match_id)
                    save_json(SENT_FILE, list(sent_matches))
                    match_queue[:] = [x for x in match_queue if x["match_id"] != match_id]

                print(f"✅ Сигнал отправлен: {m['home_ru']} — {m['away_ru']} КФ={odds_str}")

                with tracked_lock:
                    already = any(tm["match_id"] == match_id for tm in tracked_matches)
                    if not already:
                        send_date = datetime.now(MSK).strftime("%Y-%m-%d")
                        tracked_matches.append({
                            "match_id": match_id,
                            "home": m["home_ru"],
                            "away": m["away_ru"],
                            "time": m["time"],
                            "date": send_date,
                            "rate": m["rate"],
                            "odds": odds if odds else MIN_ODDS,
                            "result": None,
                            "ht_score": None,
                            "type": "1Т"  
                        })
                        save_json(TRACKED_FILE, tracked_matches)

                print("⏳ Ожидание 6 секунд перед проверкой/отправкой следующего сигнала...")
                time.sleep(6)

        time.sleep(ODDS_CHECK_INTERVAL)  

# ================== ОТПРАВКА TELEGRAM ==================
def send(text, specific_chat_id=None):
    target_chats = [specific_chat_id] if specific_chat_id else CHANNELS
    for ch in target_chats:
        try:
            bot.send_message(chat_id=ch, text=text, parse_mode="Markdown")
            time.sleep(0.5)
        except RetryAfter as e:
            time.sleep(e.retry_after)
            bot.send_message(chat_id=ch, text=text, parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка отправки в {ch}: {e}")
 
# ================== ЦИКЛ ОБНОВЛЕНИЯ МАТЧЕЙ ==================
def loader_loop():
    global sent_matches
    last_reset_date = datetime.now(MSK).strftime("%Y-%m-%d")

    while True:
        now = datetime.now(MSK)
        today = now.strftime("%Y-%m-%d")

        if today != last_reset_date:
            with queue_lock:
                sent_matches = set()
                save_json(SENT_FILE, [])
            last_reset_date = today
            with cache_lock:
                cleanup_cache()
            print(f"Новый день {today} — sent_matches сброшен, кэш очищен")

        load_matches()
        time.sleep(CHECK_INTERVAL)

# ================== 🔥 НОВЫЙ ПОТОК: LIVE ЛАЙВ МОНИТОРИНГ 1ГО ТАЙМА (NEW) ==================
def live_first_half_monitor():
    """Сканирует идущие сейчас матчи. Если идет 1-й тайм, счет 0:0, а аналитика прематча была хорошей — дает сигнал."""
    while True:
        try:
            data = safe_request("https://v3.football.api-sports.io/fixtures", {"live": "all"})
            today = datetime.now(MSK).strftime("%Y-%m-%d")
            
            for match in data.get("response", []):
                match_id = str(match["fixture"]["id"])
                
                # Если сигнал на этот матч уже улетал в прематче — пропускаем
                if match_id in sent_matches:
                    continue
                
                status = match["fixture"]["status"]["short"]
                elapsed = match["fixture"]["status"]["elapsed"] or 0
                
                # Ищем строго матчи 1-го тайма на отрезке от 8 до 25 минуты
                if status != "1H" or elapsed < 8 or elapsed > 25:
                    continue
                    
                # Ищем только сухие матчи (0:0)
                if match["goals"]["home"] != 0 or match["goals"]["away"] != 0:
                    continue
                    
                home_id = match["teams"]["home"]["id"]
                away_id = match["teams"]["away"]["id"]
                league_id = match["league"]["id"]
                
                # Считаем вероятность. Если она ниже порога — скипаем
                final_prob = calc_signal_1t(home_id, away_id, league_id)
                if final_prob < int(GOAL_THRESHOLD * 100):
                    continue
                    
                odds = get_live_1t_over_odds(match_id)
                if odds is not None and odds < MIN_ODDS:
                    continue
                    
                # Формируем и шлем полноценный сочный LIVE-сигнал на первый тайм
                league_line = format_league_line(match["league"]["country"], match["league"]["name"])
                level = signal_level(final_prob)
                odds_str = f"{odds:.2f}" if odds is not None else f"от {MIN_ODDS}"
                
                live_1t_lines = [
                    f"⚡ *LIVE СИГНАЛ (1-Й ТАЙМ)* | {league_line}",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    f"⏱ *Минута матча:* `{elapsed}-я мин` | Счет: `0 : 0`",
                    f"⚔ *ИГРАЮТ:* {translate_team(match['teams']['home']['name'])} — {translate_team(match['teams']['away']['name'])}",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    f"📊 *Вероятность гола в 1Т:* {final_prob}% (Уровень: {level})",
                    f"💰 *Коэффициент в БК:* `{odds_str}`",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    "🎯 *СТАВКА:* `Тотал 1-го тайма Больше (0.5)`",
                    "💵 _Идеальная точка входа прямо сейчас!_",
                ]
                text = "\n".join(live_1t_lines)
                send(text)
                
                with queue_lock:
                    sent_matches.add(match_id)
                    save_json(SENT_FILE, list(sent_matches))
                    
                with tracked_lock:
                    already = any(tm["match_id"] == match_id for tm in tracked_matches)
                    if not already:
                        tracked_matches.append({
                            "match_id": match_id,
                            "home": translate_team(match["teams"]["home"]["name"]),
                            "away": translate_team(match["teams"]["away"]["name"]),
                            "time": datetime.now(MSK).strftime("%H:%M"),
                            "date": today,
                            "rate": final_prob,
                            "odds": odds if odds else MIN_ODDS,
                            "result": None,
                            "ht_score": None,
                            "type": "1Т"
                        })
                        save_json(TRACKED_FILE, tracked_matches)
                        
                time.sleep(6)
                
        except Exception as e:
            print(f"Ошибка лайв-мониторинга 1Т: {e}")
            
        time.sleep(LIVE_1T_CHECK_INTERVAL)
 
# ================== LIVE 2Т АНАЛИЗ ==================
def second_half_concede_pct(team_id):
    fixtures = get_team_last_matches(team_id).get("response", [])
    checked = 0
    concede = 0

    for f in fixtures:
        score = f.get("score") or {}
        ht = score.get("halftime") or {}
        ft = score.get("fulltime") or {}

        if ht.get("home") == 0 and ht.get("away") == 0:
            checked += 1
            if (ft.get("home", 0) or 0) + (ft.get("away", 0) or 0) > 0:
                concede += 1

        if checked >= 7:
            break

    if checked < 3:
        return 0

    return concede / checked

def avg_second_half_goal_minute(team_id):
    fixtures = get_team_last_matches(team_id).get("response", [])
    minutes = []

    for f in fixtures:
        events = f.get("events") or []
        for e in events:
            if e.get("type") == "Goal":
                m = e.get("time", {}).get("elapsed")
                if m and m > 45:
                    minutes.append(m)
                    break

        if len(minutes) >= 7:
            break

    if not minutes:
        return 90

    return sum(minutes) / len(minutes)

def analyze_team_second_half(team_id):
    base = second_half_concede_pct(team_id)
    minute = avg_second_half_goal_minute(team_id)
    if minute < 65:
        minute_boost = 0.15
    elif minute < 75:
        minute_boost = 0.08
    else:
        minute_boost = 0

    return min(base + minute_boost, 1.0)
 
def get_second_half_over_odds(fixture_id):
    try:
        data = safe_request(
            "https://v3.football.api-sports.io/odds/live",
            {"fixture": fixture_id, "bet": 57}
        )
        for item in data.get("response", []):
            for bm in item.get("bookmakers", []):
                for bet in bm.get("bets", []):
                    for odd in bet.get("values", []):
                        val = odd.get("value", "")
                        if "Over" in val and "0.5" in val:
                            return float(odd.get("odd", 0))
    except Exception as e:
        print(f"Ошибка получения live КФ 2Т для {fixture_id}: {e}")
    return None

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
                if match["fixture"]["status"]["short"] != "HT":
                    continue
                if match["goals"]["home"] != 0 or match["goals"]["away"] != 0:
                    continue
 
                home_id = match["teams"]["home"]["id"]
                away_id = match["teams"]["away"]["id"]
                home_raw = match["teams"]["home"]["name"]
                away_raw = match["teams"]["away"]["name"]
                country = match.get("league", {}).get("country", "")
                league_name = match.get("league", {}).get("name", "")
 
                home_prob = analyze_team_second_half(home_id)
                away_prob = analyze_team_second_half(away_id)
                final = (home_prob + away_prob) / 2
 
                if final < LIVE_SECOND_HALF_THRESHOLD:
                    continue

                odds = get_second_half_over_odds(match_id)
                print(f"🔍 Live 2Т {translate_team(home_raw)} — {translate_team(away_raw)}: КФ={odds}")

                league_line = format_league_line(country, league_name)
                odds_str = f"{odds:.2f}" if odds is not None else f"в Live при КФ от {MIN_ODDS}"

                # ИСПРАВЛЕНО: Убрали паразитную кавычку f'🚨 из начала строки списка
                live_msg_lines = [
                    f"🚨 *LIVE СИГНАЛ* | {league_line}",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    "👑 *Счет после 1Т:* `0 : 0` (Перерыв)",
                    f"⚔️ *ИГРАЮТ:* {translate_team(home_raw)} — {translate_team(away_raw)}",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    f"📊 *Вероятность гола во 2Т:* {final * 100:.1f}%",
                    f"💰 *Текущий КФ:* `{odds_str}`",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    "🎯 *СТАВКА:* `Гол во 2-м тайме (ТБ 0.5)`",
                    "💵 _Ждем КФ для максимальной выгоды!_",
                ]
                text = "\n".join(live_msg_lines)
                
                send(text)
                
                with queue_lock:
                    live_sent.add(match_id)
                    save_json(LIVE_SENT_FILE, list(live_sent))
                print(f"Live signal: {translate_team(home_raw)} — {translate_team(away_raw)}")
                
                with tracked_lock:
                    already = any(tm["match_id"] == match_id for tm in tracked_matches)
                    if not already:
                        send_date = datetime.now(MSK).strftime("%Y-%m-%d")
                        current_time_str = datetime.now(MSK).strftime("%H:%M")
                        tracked_matches.append({
                            "match_id": match_id,
                            "home": translate_team(home_raw),
                            "away": translate_team(away_raw),
                            "time": current_time_str,
                            "date": send_date,
                            "rate": int(final * 100),
                            "odds": odds if odds is not None else MIN_ODDS,
                            "result": None,
                            "ht_score": "0:0",
                            "type": "2Т"  
                        })
                        save_json(TRACKED_FILE, tracked_matches)

                time.sleep(6)
 
        except Exception as e:
            print(f"Ошибка live мониторинга: {e}")
 
        time.sleep(LIVE_CHECK_INTERVAL)
 
# ================== ОБНОВЛЕНИЕ РЕЗУЛЬТАТОВ ==================
def update_results():
    with tracked_lock:
        pending = [m for m in tracked_matches if m["result"] is None]
 
    for m in pending:
        try:
            data = safe_request(
                "https://v3.football.api-sports.io/fixtures",
                {"id": m["match_id"]}
            )
            resp = data.get("response", [])
            if not resp:
                continue
 
            fixture = resp[0]
            status = fixture["fixture"]["status"]["short"]
 
            if status not in ("FT", "AET", "PEN", "AWD", "WO"):
                continue
 
            ht = fixture["score"]["halftime"]
            full = fixture["score"]["fulltime"]
            
            ht_home = ht.get("home") if ht.get("home") is not None else 0
            ht_away = ht.get("away") if ht.get("away") is not None else 0
            
            full_home = full.get("home") if full.get("home") is not None else 0
            full_away = full.get("away") if full.get("away") is not None else 0

            m_type = m.get("type", "1Т")
            
            if m_type == "2Т":
                goals_2t = (full_home - ht_home) + (full_away - ht_away)
                result = "win" if goals_2t > 0 else "loss"
                score_str = f"2Т ({full_home - ht_home}:{full_away - ht_away})"
            else:
                total_1t = ht_home + ht_away
                result = "win" if total_1t > 0 else "loss"
                score_str = f"{ht_home}:{ht_away}"
 
            with tracked_lock:
                for tm in tracked_matches:
                    if tm["match_id"] == m["match_id"]:
                        tm["result"] = result
                        tm["ht_score"] = score_str
                        break
                save_json(TRACKED_FILE, tracked_matches)
 
            print(f"Результат [{result.upper()}] {m['home']} — {m['away']} Тип: {m_type} Счет: {score_str}")
 
        except Exception as e:
            print(f"Ошибка получения результата {m['match_id']}: {e}")
 
def results_updater_loop():
    while True:
        time.sleep(300)
        update_results()
 
# ================== СБОРКА ТЕКСТА ОТЧЕТА ДЛЯ ДНЯ ==================
def build_report_text(target_date):
    update_results()
    with tracked_lock:
        day_matches = [m for m in tracked_matches if m["date"] == target_date]
    if len(day_matches) == 0:
        return f"📊 *ОТЧЕТ ЗА {target_date}:*\nСигналов в этот день не зафиксировано."
    matches_1t = [m for m in day_matches if m.get("type", "1Т") == "1Т"]
    matches_2t = [m for m in day_matches if m.get("type", "1Т") == "2Т"]
    wins = [m for m in day_matches if m["result"] == "win"]
    losses = [m for m in day_matches if m["result"] == "loss"]
    win_rate = round(len(wins) / len(day_matches) * 100) if day_matches else 0
    report_lines = [
        f"📊 *ИТОГИ ДНЯ — {target_date}*",
        f"Всего сигналов: *{len(day_matches)}*",
        f"✅ Выиграло: *{len(wins)}* |  ❌ Проиграло: *{len(losses)}*",
        f"📈 Итоговая точность: *{win_rate}%*",
        "━━━━━━━━━━━━━━━━━━━━━━━\n",
        "🔥 *СИГНАЛЫ НА 1 ТАЙМ (ТБ 0.5 в 1Т):*"
    ]
    if not matches_1t:
        report_lines.append("  _Сигналов не было_")
    for m in matches_1t:
        icon = "✅" if m["result"] == "win" else "❌" if m["result"] == "loss" else "⏳"
        report_lines.append(f"  {icon} {m['home']} — {m['away']} (`{m['time']}`) -> счет 1Т: `{m.get('ht_score', '0:0')}`")
    report_lines.extend([
        "\n━━━━━━━━━━━━━━━━━━━━━━━\n",
        "🚨 *LIVE СИГНАЛЫ НА 2 ТАЙМ (Гол во 2Т):*"
    ])
    if not matches_2t:
        report_lines.append("  _Сигналов не было_")
    for m in matches_2t:
        icon = "✅" if m["result"] == "win" else "❌" if m["result"] == "loss" else "⏳"
        score_info = m.get('ht_score', '0:0')
        report_lines.append(f"  {icon} {m['home']} — {m['away']} (`{m['time']}`) -> `{score_info}`")
    return "\n".join(report_lines)

# ================== ЕЖЕДНЕВНЫЙ ОТЧЁТ В 23:59 МСК ==================
def daily_report_loop():
    while True:
        now = datetime.now(MSK)
        if now.hour == 23 and now.minute == 59:
            today = now.strftime("%Y-%m-%d")
            if today not in report_sent:
                text = build_report_text(today)
                send(text)
                with tracked_lock:
                    report_sent.add(today)
                    save_json(REPORT_SENT_FILE, list(report_sent))
            time.sleep(61)
        else:
            time.sleep(30)

# ================== ИНТЕРАКТИВНЫЙ ПОТОК ВХОДЯЩИХ КОМАНД ==================
def telegram_commands_loop():
    offset = 0
    print("🤖 Поток прослушивания команд запущен успешно...")
    while True:
        try:
            updates = bot.get_updates(offset=offset, timeout=10, allowed_updates=["message"])
            for u in updates:
                offset = u.update_id + 1
                if not u.message or not u.message.text:
                    continue
                
                user_id = str(u.message.chat_id)
                text = u.message.text.strip()
                
                if user_id != CHAT_ID:
                    continue
                
                if text == "/start":
                    send("👋 Привет! Я твой футбольный аналитический бот. Работаю полностью автоматически, но готов выполнять команды:\n\n"
                         "📋 `/queue` — Посмотреть матчи в текущей очереди\n"
                         "📊 `/stats` — Посмотреть статистику за сегодня", specific_chat_id=CHAT_ID)
                
                elif text == "/queue":
                    with queue_lock:
                        q = list(match_queue)
                    if not q:
                        send("📋 *Очередь прематч-мониторинга пуста.*\nОстальные матчи отслеживаются в Лайве.", specific_chat_id=CHAT_ID)
                    else:
                        lines = ["📋 *МАТЧИ В ОЧЕРЕДИ НА ПРЕМАТЧ-МОНИТОРИНГ КФ:*"]
                        for index, m in enumerate(q, 1):
                            lines.append(f"{index}. `{m['time']}` *{m['home_ru']} — {m['away_ru']}* (Вероятность: {m['rate']}%)")
                        send("\n".join(lines), specific_chat_id=CHAT_ID)
                        
                elif text == "/stats":
                    today_str = datetime.now(MSK).strftime("%Y-%m-%d")
                    send("⏳ _Собираю актуальные данные по сыгранным матчам..._", specific_chat_id=CHAT_ID)
                    current_report = build_report_text(today_str)
                    send(current_report, specific_chat_id=CHAT_ID)
                    
        except Exception as e:
            print(f"Ошибка в обработчике команд (авто-восстановление): {e}")
            time.sleep(5)  # Оптимизация: пауза при ошибках API Telegram, чтобы не зацикливать поток
        time.sleep(1)
 
# ================== ЗАПУСК ==================
threading.Thread(target=loader_loop, daemon=True).start()
threading.Thread(target=odds_monitor_loop, daemon=True).start()
threading.Thread(target=live_first_half_monitor, daemon=True).start()  # 🔥 Новый поток лайв 1-го тайма
threading.Thread(target=live_second_half_monitor, daemon=True).start()
threading.Thread(target=results_updater_loop, daemon=True).start()
threading.Thread(target=daily_report_loop, daemon=True).start()
threading.Thread(target=telegram_commands_loop, daemon=True).start() 
 
print("BOT STARTED...")
while True:
    time.sleep(3600)