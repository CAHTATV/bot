import requests
import time
from datetime import datetime, timezone, timedelta
from telegram import Bot
from telegram.error import RetryAfter

# ================== CONFIG ==================
TOKEN = "8402411542:AAHDo48PYSv6SZ-ynkLA-UbS2Eb_rI83NYs"
API_KEY = "82a36cd1aba0ae5b0bc73dd442371916"
CHAT_ID = "532404021"

bot = Bot(token=TOKEN)
headers = {"x-apisports-key": API_KEY}

MSK = timedelta(hours=3)

scheduled = {}
sent_log = {}   # <<< ЛОГ СИГНАЛОВ
last_report_date = None

# ================== SAFE SEND ==================
last_send_time = 0

def safe_send(chat_id, text):
    global last_send_time

    while True:
        try:
            wait = max(1.5, 2.5 - (time.time() - last_send_time))
            if wait > 0:
                time.sleep(wait)

            bot.send_message(chat_id, text)
            last_send_time = time.time()
            return

        except RetryAfter as e:
            time.sleep(e.retry_after + 2)

        except Exception as e:
            print("Telegram error:", e)
            time.sleep(3)

# ================== API ==================
def get_matches():
    url = f"https://v3.football.api-sports.io/fixtures?date={datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    return requests.get(url, headers=headers).json().get("response", [])

def get_fixture(mid):
    url = f"https://v3.football.api-sports.io/fixtures?id={mid}"
    return requests.get(url, headers=headers).json().get("response", [])[0]

# ================== MODEL ==================
def calc_signal():
    return 80

def stake_level(sig):
    if sig >= 85:
        return "🔥 ЭЛИТНЫЙ"
    elif sig >= 75:
        return "💰 ВЫСОКИЙ"
    return "📊 РИСК"

# ================== SCAN ==================
def scan():

    matches = get_matches()
    now = datetime.now(timezone.utc)

    for m in matches:

        mid = m["fixture"]["id"]

        if mid in scheduled:
            continue

        home = m["teams"]["home"]["name"]
        away = m["teams"]["away"]["name"]

        match_time = datetime.fromisoformat(
            m["fixture"]["date"].replace("Z", "+00:00")
        )

        mins_to_start = int((match_time - now).total_seconds() / 60)

        if mins_to_start < 15 or mins_to_start > 60:
            continue

        sig = calc_signal()

        if sig < 65:
            continue

        send_time = match_time - timedelta(minutes=15)

        msg = f"""
⚽ LIVE ALERT

🏆 {home} vs {away}

📊 {sig}% | {stake_level(sig)}
"""

        scheduled[mid] = {
            "time": send_time,
            "msg": msg,
            "home": home,
            "away": away,
            "match_time": match_time
        }

# ================== DISPATCH ==================
def dispatch():

    now = datetime.now(timezone.utc)
    to_remove = []

    for mid, data in list(scheduled.items()):

        if now >= data["time"]:

            safe_send(CHAT_ID, data["msg"])
            safe_send(CHANNEL_ID, data["msg"])

            # <<< ЛОГИРУЕМ СИГНАЛ
            sent_log[mid] = {
                "home": data["home"],
                "away": data["away"],
                "match_time": data["match_time"],
                "checked": False
            }

            to_remove.append(mid)
            time.sleep(3.5)

    for mid in to_remove:
        del scheduled[mid]

# ================== CHECK 1st HALF ==================
def check_results():

    now = datetime.now(timezone.utc)

    for mid, data in sent_log.items():

        if data["checked"]:
            continue

        # прошло 70 минут с начала матча
        if now < data["match_time"] + timedelta(minutes=70):
            continue

        fixture = get_fixture(mid)

        ht = fixture["score"]["halftime"]

        home_ht = ht["home"]
        away_ht = ht["away"]

        result_icon = "✅" if home_ht != away_ht else "❌"

        data["checked"] = True
        data["result"] = result_icon
        data["score"] = f"{home_ht}:{away_ht}"

# ================== REPORT ==================
def daily_report():

    global last_report_date

    msk = datetime.now(timezone.utc) + MSK

    if msk.hour != 9:
        return

    if last_report_date == msk.date():
        return

    text = "📊 ОТЧЁТ ЗА 24 ЧАСА\n\n"

    for data in sent_log.values():
        if not data.get("checked"):
            continue

        text += f"{data['result']} {data['home']} vs {data['away']} ({data['score']})\n"

    safe_send(CHANNEL_ID, text)
    last_report_date = msk.date()

# ================== LOOP ==================
last_scan = 0

while True:

    now = time.time()

    if now - last_scan >= 3600:
        scan()
        last_scan = now

    dispatch()
    check_results()
    daily_report()

    time.sleep(60)