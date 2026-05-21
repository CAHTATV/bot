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
GOAL_THRESHOLD = 0.70
MIN_ODDS = 1.40            # минимальный КФ на Тотал 1Т > 0.5
CHECK_INTERVAL = 7200      # обновление списка матчей раз в 2 часа
ODDS_CHECK_INTERVAL = 60   # мониторинг КФ каждую минуту
 
LIVE_SECOND_HALF_THRESHOLD = 0.65
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
 
            if is_home smash teams.get("home", {}).get("id") != team_id:
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
        return 45

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
    cross_2 = away_attack * home_concede   
    cross = (cross_1 + cross_2) / 2

    if league_id in locale_data.FAST_LEAGUES:
        league_boost = 0.12
    elif league_id in locale_data.SLOW_LEAGUES:
        league_boost = -0.08
    else:
        league_boost = 0

    home_avg_time = get_avg_first_goal_minute(home_id, True)
    away_avg_time = get_avg_first_goal_minute(away_id, False)
    avg_first_goal_time = (home_avg_time + away_avg_time) / 2

    if avg_first_goal_time <= 23:
        time_boost = 0.10     
    elif avg_first_goal_time >= 35:
        time_boost = -0.08    
    else:
        time_boost = 0

    final = base * 0.4 + cross * 0.4 + league_boost + time_boost
    return int(max(0, min(final, 1.0)) * 100)

def signal_level(pct):
    if pct >= 86:
        return "🔥🔥 СИЛЬНЫЙ"
    elif pct >= 76:
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
 
# ================== ЗАГРУЗКА МАТЧЕЙ ДНЯ ==================
def load_matches():
    global match_queue
    print("LOAD MATCHES...")

    today = datetime.now(MSK).strftime("%Y-%m-%d")
    data = safe_request("https://v3.football.api-sports.io/fixtures", {"date": today})
    fixtures = data.get("response", [])

    with queue_lock:
        existing_ids = {m["match_id"] for m in match_queue}

    added = 0
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

    print(f"Добавлено новых матчей: {added} | Всего в мониторинге: {len(match_queue)}")

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
            if t <= now:
                with queue_lock:
                    match_queue[:] = [x for x in match_queue if x["match_id"] != match_id]
                print(f"⏰ Матч начался, убран из мониторинга: {m['home_ru']} — {m['away_ru']}")
                continue

            odds = get_first_half_over_odds(match_id)
            print(f"   {m['home_ru']} — {m['away_ru']}: КФ={odds} (нужно ≥{MIN_ODDS})")

            # Защитная микро-пауза перед следующим запросом в API-Sports
            time.sleep(1.5)

            if odds is None or odds < MIN_ODDS:
                continue  

            league_line = format_league_line(m.get("country", ""), m.get("league", ""))
            level = signal_level(m["rate"])

            text = (
                f"⚽️ СИГНАЛ НА 1 ТАЙМ\n"
                f"{league_line}\n\n"
                f"{m['home_ru']} — {m['away_ru']}\n"
                f"⏰ {m['time']} МСК\n\n"
                f"📊 Вероятность гола в 1Т: {m['rate']}%\n"
                f"🎯 Уровень сигнала: {level}\n"
                f"💰 Коэффициент: {odds:.2f}\n\n"
                f"Ставка: Тотал 1Т Больше 0.5"
            )

            send(text)
            
            with queue_lock:
                sent_matches.add(match_id)
                save_json(SENT_FILE, list(sent_matches))
                match_queue[:] = [x for x in match_queue if x["match_id"] != match_id]

            print(f"✅ Сигнал отправлен: {m['home_ru']} — {m['away_ru']} КФ={odds:.2f}")

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
                        "odds": odds,
                        "result": None,
                        "ht_score": None,
                        "type": "1Т"  # ГРУППИРОВКА: Маркируем как прематч на 1 тайм
                    })
                    save_json(TRACKED_FILE, tracked_matches)

            # Искусственная задержка 6 секунд между отправкой РАЗНЫХ матчей в ТГ
            print("⏳ Ожидание 6 секунд перед проверкой/отправкой следующего сигнала...")
            time.sleep(6)

        time.sleep(ODDS_CHECK_INTERVAL)  

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

                if odds is not None and odds < MIN_ODDS:
                    print(f"Live КФ {odds} ниже порога, пропускаем")
                    continue

                league_line = format_league_line(country, league_name)
                odds_line = f"💰 Коэффициент: {odds:.2f}" if odds is not None else "💰 Коэффициент: уточните у букмекера"

                text = (
                    f"🚨 LIVE СИГНАЛ\n"
                    f"{league_line}\n\n"
                    f"0:0 в перерыве\n"
                    f"{translate_team(home_raw)} — {translate_team(away_raw)}\n\n"
                    f"📊 Вероятность гола во 2Т: {final * 100:.1f}%\n"
                    f"🎯 Гол во 2 тайме — ДА\n"
                    f"{odds_line}\n\n"
                    f"Ставка: Тотал 2Т Больше 0.5"
                )
                send(text)
                
                with queue_lock:
                    live_sent.add(match_id)
                    save_json(LIVE_SENT_FILE, list(live_sent))
                print(f"Live сигнал: {translate_team(home_raw)} — {translate_team(away_raw)} КФ={odds}")
                
                # Запись 2Т сигнала в историю результатов
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
                            "odds": odds if odds is not None else 0,
                            "result": None,
                            "ht_score": "0:0",
                            "type": "2Т"  # ГРУППИРОВКА: Маркируем как Live-сигнал на 2 тайм
                        })
                        save_json(TRACKED_FILE, tracked_matches)

                # Такая же пауза 6 секунд для Live-сигналов, если совпало несколько матчей
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

            # ГРУППИРОВКА РЕЗУЛЬТАТОВ: Проверяем по типу сохраненного сигнала
            m_type = m.get("type", "1Т")
            
            if m_type == "2Т":
                # Для второго тайма считаем только голы, забитые ПОСЛЕ перерыва
                goals_2t = (full_home - ht_home) + (full_away - ht_away)
                result = "win" if goals_2t > 0 else "loss"
                score_str = f"2Т ({full_home - ht_home}:{full_away - ht_away})"
            else:
                # Для первого тайма всё стандартно
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
 
# ================== НАГЛЯДНЫЙ ЕЖЕДНЕВНЫЙ ОТЧЁТ В 23:59 МСК ==================
def daily_report_loop():
    while True:
        now = datetime.now(MSK)
 
        if now.hour == 23 and now.minute == 59:
            today = now.strftime("%Y-%m-%d")
 
            if today not in report_sent:
                update_results()
 
                with tracked_lock:
                    today_matches = [m for m in tracked_matches if m["date"] == today]
 
                if len(today_matches) == 0:
                    with tracked_lock:
                        report_sent.add(today)
                        save_json(REPORT_SENT_FILE, list(report_sent))
                    time.sleep(61)
                    continue
 
                # Делим матчи дня на две группы
                matches_1t = [m for m in today_matches if m.get("type", "1Т") == "1Т"]
                matches_2t = [m for m in today_matches if m.get("type", "1Т") == "2Т"]

                wins = [m for m in today_matches if m["result"] == "win"]
                losses = [m for m in today_matches if m["result"] == "loss"]
                win_rate = round(len(wins) / len(today_matches) * 100) if today_matches else 0
 
                lines = [f"📊 ИТОГИ ДНЯ — {now.strftime('%d.%m.%Y')}\n"]
                lines.append(f"Всего сигналов: {len(today_matches)}")
                lines.append(f"✅ Выиграло: {len(wins)}  |  ❌ Проиграло: {len(losses)}")
                lines.append(f"📈 Итоговая точность: {win_rate}%\n")
                lines.append("=" * 25 + "\n")
 
                # ГРУППА 1: Сигналы на 1-й тайм
                lines.append("🔥 СИГНАЛЫ НА 1 ТАЙМ (ТБ 0.5 в 1Т):")
                if not matches_1t:
                    lines.append("  *Сигналов не было*")
                for m in matches_1t:
                    icon = "✅" if m["result"] == "win" else "❌" if m["result"] == "loss" else "⏳"
                    lines.append(f"  {icon} {m['home']} — {m['away']} ({m['time']}) -> счет 1Т: {m.get('ht_score', '0:0')}")
                
                lines.append("\n" + "=" * 25 + "\n")

                # ГРУППА 2: Сигналы на 2-й тайм
                lines.append("🚨 LIVE СИГНАЛЫ НА 2 ТАЙМ (Гол во 2Т):")
                if not matches_2t:
                    lines.append("  *Сигналов не было*")
                for m in matches_2t:
                    icon = "✅" if m["result"] == "win" else "❌" if m["result"] == "loss" else "⏳"
                    # Извлекаем красивый счет чисто за 2-й тайм
                    score_info = m.get('ht_score', '0:0')
                    lines.append(f"  {icon} {m['home']} — {m['away']} ({m['time']}) -> {score_info}")
 
                send("\n".join(lines))
                print("Наглядный структурированный ежедневный отчёт отправлен.")
 
                with tracked_lock:
                    report_sent.add(today)
                    save_json(REPORT_SENT_FILE, list(report_sent))
 
            time.sleep(61)
        else:
            time.sleep(30)
 
# ================== ЗАПУСК ==================
threading.Thread(target=loader_loop, daemon=True).start()
threading.Thread(target=odds_monitor_loop, daemon=True).start()
threading.Thread(target=live_second_half_monitor, daemon=True).start()
threading.Thread(target=results_updater_loop, daemon=True).start()
threading.Thread(target=daily_report_loop, daemon=True).start()
 
print("BOT STARTED...")
while True:
    time.sleep(3600)