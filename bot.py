print("BOT VERSION: MERGED + DAILY REPORT + RU LOCALE")
 
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
MSK = timezone(timedelta(hours=3))
 
MATCHES_TO_CHECK = 7
GOAL_THRESHOLD = 0.70
SEND_BEFORE = 900
CHECK_INTERVAL = 1800  # проверка матчей каждые 30 минут
 
LIVE_SECOND_HALF_THRESHOLD = 0.65
LIVE_CHECK_INTERVAL = 120
 
# ================== ФАЙЛЫ СОСТОЯНИЯ ==================
CACHE_FILE = "stats_cache.json"
SENT_FILE = "sent_matches.json"
LIVE_SENT_FILE = "live_sent.json"
TRACKED_FILE = "tracked_matches.json"
REPORT_SENT_FILE = "report_sent.json"
 
# ================== СЛОВАРИ ПЕРЕВОДОВ ==================
 
COUNTRY_FLAGS = {
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Spain": "🇪🇸", "Germany": "🇩🇪", "Italy": "🇮🇹",
    "France": "🇫🇷", "Portugal": "🇵🇹", "Netherlands": "🇳🇱", "Belgium": "🇧🇪",
    "Turkey": "🇹🇷", "Russia": "🇷🇺", "Ukraine": "🇺🇦", "Poland": "🇵🇱",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Greece": "🇬🇷", "Switzerland": "🇨🇭", "Austria": "🇦🇹",
    "Denmark": "🇩🇰", "Sweden": "🇸🇪", "Norway": "🇳🇴", "Finland": "🇫🇮",
    "Czech-Republic": "🇨🇿", "Slovakia": "🇸🇰", "Croatia": "🇭🇷", "Serbia": "🇷🇸",
    "Romania": "🇷🇴", "Hungary": "🇭🇺", "Bulgaria": "🇧🇬", "Israel": "🇮🇱",
    "USA": "🇺🇸", "Brazil": "🇧🇷", "Argentina": "🇦🇷", "Mexico": "🇲🇽",
    "Colombia": "🇨🇴", "Chile": "🇨🇱", "Uruguay": "🇺🇾", "Japan": "🇯🇵",
    "South Korea": "🇰🇷", "China": "🇨🇳", "Australia": "🇦🇺", "Morocco": "🇲🇦",
    "Egypt": "🇪🇬", "Nigeria": "🇳🇬", "South Africa": "🇿🇦", "Saudi Arabia": "🇸🇦",
    "Iran": "🇮🇷", "World": "🌍", "Europe": "🇪🇺", "Belarus": "🇧🇾",
    "Kazakhstan": "🇰🇿", "Georgia": "🇬🇪", "Armenia": "🇦🇲", "Azerbaijan": "🇦🇿",
    "Slovenia": "🇸🇮", "Bosnia": "🇧🇦", "Albania": "🇦🇱", "North Macedonia": "🇲🇰",
    "Montenegro": "🇲🇪", "Kosovo": "🇽🇰", "Luxembourg": "🇱🇺", "Cyprus": "🇨🇾",
    "Malta": "🇲🇹", "Iceland": "🇮🇸", "Ireland": "🇮🇪", "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
    "Northern-Ireland": "🇬🇧", "Canada": "🇨🇦", "Ecuador": "🇪🇨", "Peru": "🇵🇪",
    "Venezuela": "🇻🇪", "Bolivia": "🇧🇴", "Paraguay": "🇵🇾", "Honduras": "🇭🇳",
    "Costa Rica": "🇨🇷", "Panama": "🇵🇦", "Jamaica": "🇯🇲", "Tunisia": "🇹🇳",
    "Algeria": "🇩🇿", "Senegal": "🇸🇳", "Ghana": "🇬🇭", "Cameroon": "🇨🇲",
    "Ivory-Coast": "🇨🇮", "Kenya": "🇰🇪", "Qatar": "🇶🇦", "UAE": "🇦🇪",
    "Iraq": "🇮🇶", "Jordan": "🇯🇴", "Indonesia": "🇮🇩", "Thailand": "🇹🇭",
    "Vietnam": "🇻🇳", "India": "🇮🇳",
}
 
COUNTRY_RU = {
    "England": "Англия", "Spain": "Испания", "Germany": "Германия",
    "Italy": "Италия", "France": "Франция", "Portugal": "Португалия",
    "Netherlands": "Нидерланды", "Belgium": "Бельгия", "Turkey": "Турция",
    "Russia": "Россия", "Ukraine": "Украина", "Poland": "Польша",
    "Scotland": "Шотландия", "Greece": "Греция", "Switzerland": "Швейцария",
    "Austria": "Австрия", "Denmark": "Дания", "Sweden": "Швеция",
    "Norway": "Норвегия", "Finland": "Финляндия", "Czech-Republic": "Чехия",
    "Slovakia": "Словакия", "Croatia": "Хорватия", "Serbia": "Сербия",
    "Romania": "Румыния", "Hungary": "Венгрия", "Bulgaria": "Болгария",
    "Israel": "Израиль", "USA": "США", "Brazil": "Бразилия",
    "Argentina": "Аргентина", "Mexico": "Мексика", "Colombia": "Колумбия",
    "Chile": "Чили", "Uruguay": "Уругвай", "Japan": "Япония",
    "South Korea": "Южная Корея", "China": "Китай", "Australia": "Австралия",
    "Morocco": "Марокко", "Egypt": "Египет", "Nigeria": "Нигерия",
    "South Africa": "ЮАР", "Saudi Arabia": "Саудовская Аравия", "Iran": "Иран",
    "World": "Мир", "Europe": "Европа", "Belarus": "Беларусь",
    "Kazakhstan": "Казахстан", "Georgia": "Грузия", "Armenia": "Армения",
    "Azerbaijan": "Азербайджан", "Slovenia": "Словения", "Bosnia": "Босния",
    "Albania": "Албания", "North Macedonia": "Северная Македония",
    "Montenegro": "Черногория", "Kosovo": "Косово", "Luxembourg": "Люксембург",
    "Cyprus": "Кипр", "Malta": "Мальта", "Iceland": "Исландия",
    "Ireland": "Ирландия", "Wales": "Уэльс", "Northern-Ireland": "Северная Ирландия",
    "Canada": "Канада", "Ecuador": "Эквадор", "Peru": "Перу",
    "Venezuela": "Венесуэла", "Bolivia": "Боливия", "Paraguay": "Парагвай",
    "Honduras": "Гондурас", "Costa Rica": "Коста-Рика", "Panama": "Панама",
    "Tunisia": "Тунис", "Algeria": "Алжир", "Senegal": "Сенегал",
    "Ghana": "Гана", "Cameroon": "Камерун", "Ivory-Coast": "Кот-д'Ивуар",
    "Qatar": "Катар", "UAE": "ОАЭ", "Iraq": "Ирак", "Jordan": "Иордания",
    "Indonesia": "Индонезия", "Thailand": "Таиланд", "Vietnam": "Вьетнам",
    "India": "Индия",
}
 
LEAGUE_RU = {
    # Англия
    "Premier League": "Премьер-лига",
    "Championship": "Чемпионшип",
    "League One": "Первая лига",
    "League Two": "Вторая лига",
    "FA Cup": "Кубок Англии",
    "EFL Cup": "Кубок Лиги",
    # Испания
    "La Liga": "Ла Лига",
    "Segunda División": "Сегунда",
    "Copa del Rey": "Кубок Испании",
    # Германия
    "Bundesliga": "Бундеслига",
    "2. Bundesliga": "2. Бундеслига",
    "3. Liga": "3. Лига",
    "DFB Pokal": "Кубок Германии",
    # Италия
    "Serie A": "Серия А",
    "Serie B": "Серия Б",
    "Coppa Italia": "Кубок Италии",
    # Франция
    "Ligue 1": "Лига 1",
    "Ligue 2": "Лига 2",
    "Coupe de France": "Кубок Франции",
    # Португалия
    "Primeira Liga": "Примейра Лига",
    "Liga Portugal 2": "Лига Португалии 2",
    # Нидерланды
    "Eredivisie": "Эредивизи",
    "Eerste Divisie": "Eerste Divisie",
    # Бельгия
    "First Division A": "Первый дивизион А",
    "First Division B": "Первый дивизион Б",
    # Турция
    "Süper Lig": "Суперлига",
    "1. Lig": "1. Лига",
    # Россия
    "Premier League": "Премьер-лига",
    "FNL": "ФНЛ",
    # Украина
    "Premier League": "Премьер-лига",
    # Польша
    "Ekstraklasa": "Экстракласа",
    # Шотландия
    "Premiership": "Премьершип",
    # Греция
    "Super League 1": "Суперлига 1",
    # Европа / Мир
    "UEFA Champions League": "Лига Чемпионов",
    "UEFA Europa League": "Лига Европы",
    "UEFA Europa Conference League": "Лига Конференций",
    "UEFA Nations League": "Лига Наций",
    "UEFA Super Cup": "Суперкубок УЕФА",
    "World Cup": "Чемпионат Мира",
    "World Cup - Qualification": "Отбор ЧМ",
    "Euro Championship": "Чемпионат Европы",
    "Euro Championship - Qualification": "Отбор ЕВРО",
    "Copa America": "Копа Америка",
    "African Cup of Nations": "Кубок Африки",
    "Club World Cup": "Клубный ЧМ",
    # Бразилия
    "Série A": "Серия А",
    "Série B": "Серия Б",
    # Аргентина
    "Liga Profesional": "Профессиональная Лига",
    # США
    "Major League Soccer": "MLS",
    # Япония
    "J1 League": "Лига Дж1",
    # Саудовская Аравия
    "Saudi Professional League": "Саудовская Про-Лига",
}
 
TEAM_RU = {
    # Английская Премьер-лига
    "Arsenal": "Арсенал", "Chelsea": "Челси", "Liverpool": "Ливерпуль",
    "Manchester City": "Манчестер Сити", "Manchester United": "Манчестер Юнайтед",
    "Tottenham": "Тоттенхэм", "Newcastle": "Ньюкасл", "Aston Villa": "Астон Вилла",
    "West Ham": "Вест Хэм", "Brighton": "Брайтон", "Brentford": "Брентфорд",
    "Fulham": "Фулхэм", "Wolves": "Вулверхэмптон", "Everton": "Эвертон",
    "Crystal Palace": "Кристал Пэлас", "Nottingham Forest": "Ноттингем Форест",
    "Burnley": "Бёрнли", "Luton": "Лутон", "Sheffield Utd": "Шеффилд Юнайтед",
    "Leicester": "Лестер", "Ipswich": "Ипсвич", "Southampton": "Саутгемптон",
    "Bournemouth": "Борнмут",
    # Испания
    "Real Madrid": "Реал Мадрид", "Barcelona": "Барселона", "Atletico Madrid": "Атлетико",
    "Sevilla": "Севилья", "Valencia": "Валенсия", "Villarreal": "Вильярреал",
    "Athletic Club": "Атлетик", "Real Sociedad": "Реал Сосьедад",
    "Real Betis": "Бетис", "Getafe": "Хетафе", "Girona": "Жирона",
    "Celta Vigo": "Сельта", "Osasuna": "Осасуна", "Mallorca": "Мальорка",
    "Las Palmas": "Лас-Пальмас", "Rayo Vallecano": "Райо Вальекано",
    "Alaves": "Алавес", "Cadiz": "Кадис", "Granada": "Гранада",
    # Германия
    "Bayern Munich": "Бавария", "Borussia Dortmund": "Боруссия Дортмунд",
    "RB Leipzig": "РБ Лейпциг", "Bayer Leverkusen": "Байер Леверкузен",
    "Eintracht Frankfurt": "Айнтрахт Франкфурт", "Wolfsburg": "Вольфсбург",
    "Borussia Monchengladbach": "Боруссия Мёнхенгладбах", "Hoffenheim": "Хоффенхайм",
    "Freiburg": "Фрайбург", "Augsburg": "Аугсбург", "Union Berlin": "Унион Берлин",
    "Stuttgart": "Штутгарт", "Werder Bremen": "Вердер", "Mainz": "Майнц",
    "Darmstadt": "Дармштадт", "Heidenheim": "Хайденхайм",
    # Италия
    "Juventus": "Ювентус", "Inter": "Интер", "AC Milan": "Милан",
    "Napoli": "Наполи", "Roma": "Рома", "Lazio": "Лацио",
    "Atalanta": "Аталанта", "Fiorentina": "Фиорентина", "Torino": "Торино",
    "Bologna": "Болонья", "Udinese": "Удинезе", "Sassuolo": "Сассуоло",
    "Monza": "Монца", "Lecce": "Лечче", "Cagliari": "Кальяри",
    "Genoa": "Дженоа", "Hellas Verona": "Верона", "Empoli": "Эмполи",
    "Frosinone": "Фрозиноне", "Salernitana": "Салернитана",
    # Франция
    "Paris Saint Germain": "ПСЖ", "PSG": "ПСЖ", "Marseille": "Марсель",
    "Lyon": "Лион", "Monaco": "Монако", "Lille": "Лилль",
    "Nice": "Ницца", "Rennes": "Ренн", "Lens": "Ланс",
    "Strasbourg": "Страсбур", "Reims": "Реймс", "Montpellier": "Монпелье",
    "Toulouse": "Тулуза", "Nantes": "Нант", "Brest": "Брест",
    "Le Havre": "Гавр", "Metz": "Мец", "Clermont": "Клермон",
    # Португалия
    "Benfica": "Бенфика", "Porto": "Порту", "Sporting CP": "Спортинг",
    "Braga": "Брага", "Vitoria Guimaraes": "Витория",
    # Нидерланды
    "Ajax": "Аякс", "PSV Eindhoven": "ПСВ", "Feyenoord": "Фейеноорд",
    "AZ": "АЗ", "Utrecht": "Утрехт", "Twente": "Твенте",
    # Бельгия
    "Club Brugge": "Брюгге", "Anderlecht": "Андерлехт",
    "Gent": "Гент", "Genk": "Генк", "Antwerp": "Антверп",
    "Union Saint-Gilloise": "Юнион СЖ",
    # Турция
    "Galatasaray": "Галатасарай", "Fenerbahce": "Фенербахче",
    "Besiktas": "Бешикташ", "Trabzonspor": "Трабзонспор",
    # Россия
    "Zenit": "Зенит", "CSKA Moscow": "ЦСКА", "Spartak Moscow": "Спартак",
    "Lokomotiv Moscow": "Локомотив", "Dynamo Moscow": "Динамо",
    "Krasnodar": "Краснодар",
    # Украина
    "Shakhtar Donetsk": "Шахтёр", "Dynamo Kyiv": "Динамо Киев",
    # Лига Чемпионов / известные клубы
    "Real Madrid": "Реал Мадрид", "Celtic": "Селтик",
    "Rangers": "Рейнджерс", "Benfica": "Бенфика",
}
 
def translate_team(name):
    return TEAM_RU.get(name, name)
 
def translate_league(name):
    return LEAGUE_RU.get(name, name)
 
def translate_country(name):
    return COUNTRY_RU.get(name, name)
 
def get_flag(country):
    return COUNTRY_FLAGS.get(country, "🌍")
 
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
 
# ================== ПРОПУСКАЕМОСТЬ В 1Т ==================
def first_half_concede_pct(team_id, is_home):
    """Доля матчей, в которых команда пропустила в 1Т (в своей роли дом/гость)."""
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

# ================== СРЕДНЯЯ МИНУТА ПЕРВОГО ГОЛА В 1Т ==================
def avg_first_goal_minute(team_id):
    """Средняя минута первого гола (только до 45 мин), последние 7 матчей."""
    fixtures = get_team_last_matches(team_id).get("response", [])
    minutes = []

    for f in fixtures:
        events = f.get("events") or []
        for e in events:
            if e.get("type") == "Goal":
                m = e.get("time", {}).get("elapsed")
                if m and m <= 45:
                    minutes.append(m)
                    break

        if len(minutes) >= 7:
            break

    if not minutes:
        return 50  # нейтральное значение если нет данных

    return sum(minutes) / len(minutes)

# ================== ТЕМП ЛИГ ==================
# Быстрые лиги — много голов в 1Т
FAST_LEAGUES = {
    103,  # Норвегия
    113,  # Швеция
    88,   # Нидерланды (Эредивизи)
    78,   # Германия (Бундеслига)
    66,   # Франция Лига 2
    94,   # Португалия (Примейра)
    71,   # Бразилия Серия А
    2,    # Лига Чемпионов
    3,    # Лига Европы
}

# Медленные лиги — осторожный 1Т
SLOW_LEAGUES = {
    135,  # Италия (Серия А)
    140,  # Испания (Ла Лига)
    39,   # Англия (АПЛ)
    235,  # Россия (РПЛ) — низкий темп, осторожный 1Т
    236,  # Россия (ФНЛ)
    276,  # Украина (УПЛ)
    263,  # Беларусь (Вышэйшая лига)
    321,  # Казахстан (Премьер-лига)
}

# ================== СИЛА АТАКИ В 1Т ==================
def first_half_scored_pct(team_id, is_home):
    """Доля матчей, в которых команда сама забила в 1Т (в своей роли дом/гость)."""
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

# ================== ИТОГОВЫЙ РАСЧЁТ СИГНАЛА 1Т ==================
def calc_signal_1t(home_id, away_id, league_id):
    """
    Комплексный расчёт вероятности гола в 1Т.
    Формула: 50% базовая забиваемость + 50% перекрёстный атака/защита + темп лиги.
    """
    # Общая забиваемость в матчах (хоть один гол в 1Т)
    home_goal = team_first_half_goal_rate(home_id, True)
    away_goal = team_first_half_goal_rate(away_id, False)
    base = (home_goal + away_goal) / 2

    # Атака каждой команды vs защита соперника
    home_attack = first_half_scored_pct(home_id, True)
    away_attack = first_half_scored_pct(away_id, False)
    home_concede = first_half_concede_pct(home_id, True)
    away_concede = first_half_concede_pct(away_id, False)

    cross_1 = home_attack * away_concede   # хозяева забивают — гости пропускают
    cross_2 = away_attack * home_concede   # гости забивают — хозяева пропускают
    cross = (cross_1 + cross_2) / 2

    # Темп лиги
    if league_id in FAST_LEAGUES:
        league_boost = 0.12
    elif league_id in SLOW_LEAGUES:
        league_boost = -0.08
    else:
        league_boost = 0

    final = base * 0.5 + cross * 0.5 + league_boost

    return int(max(0, min(final, 1.0)) * 100)

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
 
            # Комплексный расчёт: забиваемость + пропускаемость + минута гола + лига
            signal_pct = calc_signal_1t(home_id, away_id, league_id)
 
            if signal_pct < int(GOAL_THRESHOLD * 100):
                continue
 
            new_queue.append({
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
 
            t = datetime.fromisoformat(m["time_iso"])
            diff = (t - now).total_seconds()
 
            if diff > SEND_BEFORE or diff < 0:
                continue
 
            level = signal_level(m["rate"])
            league_line = format_league_line(m.get("country", ""), m.get("league", ""))
 
            text = (
                f"⚽️ СИГНАЛ НА 1 ТАЙМ\n"
                f"{league_line}\n\n"
                f"{m['home_ru']} — {m['away_ru']}\n"
                f"⏰ {m['time']} МСК\n\n"
                f"📊 Забиваемость ({MATCHES_TO_CHECK} матчей): {m['rate']}%\n"
                f"🎯 Уровень сигнала: {level}\n\n"
                f"Ставка: Тотал 1Т Больше 0.5"
            )
 
            send(text)
            sent_matches.add(match_id)
            save_json(SENT_FILE, list(sent_matches))
            print(f"Отправлен сигнал: {m['home_ru']} — {m['away_ru']}")
 
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
                        "result": None,
                        "ht_score": None
                    })
                    save_json(TRACKED_FILE, tracked_matches)
                    print(f"Добавлен в отслеживание [{send_date}]: {m['home_ru']} — {m['away_ru']}")
 
        time.sleep(30)
 
# ================== ЦИКЛ ОБНОВЛЕНИЯ МАТЧЕЙ ==================
def loader_loop():
    global sent_matches
    last_reset_date = datetime.now(MSK).strftime("%Y-%m-%d")

    while True:
        now = datetime.now(MSK)
        today = now.strftime("%Y-%m-%d")

        # В полночь МСК сбрасываем sent_matches чтобы не копились старые ID
        if today != last_reset_date:
            sent_matches = set()
            save_json(SENT_FILE, [])
            last_reset_date = today
            print(f"Новый день {today} — sent_matches сброшен")

        load_matches()
        time.sleep(CHECK_INTERVAL)
 
# ================== LIVE 2Т АНАЛИЗ ==================

def second_half_concede_pct(team_id):
    """
    Доля матчей где команда играла 0:0 в перерыве и пропустила во 2Т.
    Это базовая вероятность гола во 2Т при счёте 0:0 в HT.
    """
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
    """
    Средняя минута первого гола во 2Т (события после 45-й минуты).
    Если данных нет — возвращает нейтральные 90.
    """
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
    """
    Комплексная вероятность гола во 2Т при счёте 0:0 в перерыве.
    Учитывает: базовую пропускаемость во 2Т + буст если голы ранние.
    """
    base = second_half_concede_pct(team_id)

    minute = avg_second_half_goal_minute(team_id)
    if minute < 65:
        minute_boost = 0.15
    elif minute < 75:
        minute_boost = 0.08
    else:
        minute_boost = 0

    return min(base + minute_boost, 1.0)
 
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
 
                if final >= LIVE_SECOND_HALF_THRESHOLD:
                    league_line = format_league_line(country, league_name)
                    text = (
                        f"🚨 LIVE СИГНАЛ\n"
                        f"{league_line}\n\n"
                        f"0:0 в перерыве\n"
                        f"{translate_team(home_raw)} — {translate_team(away_raw)}\n\n"
                        f"📊 Вероятность гола во 2Т: {final * 100:.1f}%\n"
                        f"🎯 Гол во 2 тайме — ДА"
                    )
                    send(text)
                    live_sent.add(match_id)
                    save_json(LIVE_SENT_FILE, list(live_sent))
                    print(f"Live сигнал: {translate_team(home_raw)} — {translate_team(away_raw)}")
 
        except Exception as e:
            print(f"Ошибка live мониторинга: {e}")
 
        time.sleep(LIVE_CHECK_INTERVAL)
 
# ================== ОБНОВЛЕНИЕ РЕЗУЛЬТАТОВ 1Т ==================
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
            ht_home = ht.get("home") or 0
            ht_away = ht.get("away") or 0
            total_1t = ht_home + ht_away
            result = "win" if total_1t > 0 else "loss"
 
            with tracked_lock:
                for tm in tracked_matches:
                    if tm["match_id"] == m["match_id"]:
                        tm["result"] = result
                        tm["ht_score"] = f"{ht_home}:{ht_away}"
                        break
                save_json(TRACKED_FILE, tracked_matches)
 
            print(f"Результат [{result.upper()}] {m['home']} — {m['away']} HT {ht_home}:{ht_away}")
 
        except Exception as e:
            print(f"Ошибка получения результата {m['match_id']}: {e}")
 
def results_updater_loop():
    while True:
        time.sleep(300)
        update_results()
 
# ================== ЕЖЕДНЕВНЫЙ ОТЧЁТ В 23:59 МСК ==================
def daily_report_loop():
    while True:
        now = datetime.now(MSK)
 
        if now.hour == 23 and now.minute == 59:
            today = now.strftime("%Y-%m-%d")
 
            if today not in report_sent:
                update_results()
 
                with tracked_lock:
                    today_matches = [m for m in tracked_matches if m["date"] == today]
 
                wins    = [m for m in today_matches if m["result"] == "win"]
                losses  = [m for m in today_matches if m["result"] == "loss"]
                pending = [m for m in today_matches if m["result"] is None]
                total   = len(today_matches)
 
                if total == 0:
                    report_sent.add(today)
                    save_json(REPORT_SENT_FILE, list(report_sent))
                    time.sleep(61)
                    continue
 
                win_rate = round(len(wins) / total * 100) if total > 0 else 0
 
                lines = [f"📊 ИТОГИ ДНЯ — {now.strftime('%d.%m.%Y')}\n"]
                lines.append(f"Всего сигналов: {total}")
                lines.append(f"✅ Выиграло: {len(wins)}")
                lines.append(f"❌ Проиграло: {len(losses)}")
                if pending:
                    lines.append(f"⏳ Без результата: {len(pending)}")
                lines.append(f"📈 Точность за день: {win_rate}%\n")
 
                if wins:
                    lines.append("✅ Победы:")
                    for m in wins:
                        ht = m.get("ht_score", "?:?")
                        lines.append(f"  {m['home']} — {m['away']}  {m['time']} МСК  HT {ht}")
 
                if losses:
                    lines.append("\n❌ Проигрыши:")
                    for m in losses:
                        ht = m.get("ht_score", "0:0")
                        lines.append(f"  {m['home']} — {m['away']}  {m['time']} МСК  HT {ht}")
 
                send("\n".join(lines))
                print("Ежедневный отчёт отправлен.")
 
                report_sent.add(today)
                save_json(REPORT_SENT_FILE, list(report_sent))
 
            time.sleep(61)
        else:
            time.sleep(30)
 
# ================== ЗАПУСК ==================
threading.Thread(target=loader_loop, daemon=True).start()
threading.Thread(target=sender_loop, daemon=True).start()
threading.Thread(target=live_second_half_monitor, daemon=True).start()
threading.Thread(target=results_updater_loop, daemon=True).start()
threading.Thread(target=daily_report_loop, daemon=True).start()
 
print("BOT STARTED...")
 
while True:
    print("BOT KEEP ALIVE...")
    time.sleep(60)