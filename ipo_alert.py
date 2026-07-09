import os
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SOURCES = [
    "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/",
    "https://www.ipopremium.in/",
]

def clean(text):
    return re.sub(r"\s+", " ", text).strip()

def fetch_page(url, retries=3):
    headers = {"User-Agent": "Mozilla/5.0"}
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logging.warning(f"Failed {url}, attempt {attempt + 1}: {e}")
            time.sleep(3)
    return None

def extract_number(text):
    match = re.search(r"\d+(\.\d+)?", text.replace(",", ""))
    return float(match.group()) if match else None

def calculate_gmp_percent(price, gmp):
    price_num = extract_number(price)
    gmp_num = extract_number(gmp)

    if price_num and gmp_num:
        return round((gmp_num / price_num) * 100, 2)

    return None

def parse_ipos():
    ipos = []

    for url in SOURCES:
        html = fetch_page(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")

        for table in soup.find_all("table"):
            rows = table.find_all("tr")

            for row in rows[1:]:
                cols = [clean(td.get_text(" ")) for td in row.find_all("td")]

                if len(cols) < 3:
                    continue

                name = cols[0]

                if len(name) < 3:
                    continue

                row_text = " | ".join(cols)

                price = "Data unavailable"
                gmp = "Data unavailable"
                close_date = "Data unavailable"
                lot_size = "Data unavailable"

                for col in cols:
                    if "₹" in col and price == "Data unavailable":
                        price = col

                    if "GMP" in col.upper() or "+" in col or "%" in col:
                        gmp = col

                    if any(month in col.lower() for month in ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]):
                        close_date = col

                    if "lot" in col.lower():
                        lot_size = col

                price_num = extract_number(price)
                lot_num = extract_number(lot_size)

                min_investment = "Data unavailable"
                if price_num and lot_num:
                    min_investment = f"₹{int(price_num * lot_num):,}"

                gmp_percent = calculate_gmp_percent(price, gmp)
                gmp_text = gmp

                if gmp_percent:
                    gmp_text = f"{gmp} ({gmp_percent}%)"

                expected_gain = "Data unavailable"
                recommendation = "WAIT"

                if gmp_percent:
                    if gmp_percent >= 25:
                        expected_gain = "High"
                        recommendation = "APPLY"
                    elif gmp_percent >= 10:
                        expected_gain = "Moderate"
                        recommendation = "MAY APPLY"
                    elif gmp_percent > 0:
                        expected_gain = "Low"
                        recommendation = "AVOID / WAIT"
                    else:
                        expected_gain = "Negative / Flat"
                        recommendation = "AVOID"

                ipos.append({
                    "name": name,
                    "close_date": close_date,
                    "price": price,
                    "lot_size": lot_size,
                    "min_investment": min_investment,
                    "gmp": gmp_text,
                    "expected_gain": expected_gain,
                    "recommendation": recommendation,
                })

    unique = []
    seen = set()

    for ipo in ipos:
        key = ipo["name"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(ipo)

    return unique[:8]

def build_message():
    now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p")
    ipos = parse_ipos()

    msg = "📊 <b>PERSONAL INVESTMENT ASSISTANT</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📅 {now}\n"
    msg += "🟢 Status: Bot running successfully\n\n"

    msg += "🔥 <b>LIVE IPOs</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"

    if not ipos:
        msg += "\nNo live IPO data available right now.\n"
        msg += "IPO source may be down or changed.\n\n"
        msg += "⚠️ Bot is working, but data source failed."
        return msg

    for index, ipo in enumerate(ipos, start=1):
        msg += f"\n{index}️⃣ <b>{ipo['name']}</b>\n"
        msg += f"💰 Price: {ipo['price']}\n"
        msg += f"📦 Lot Size: {ipo['lot_size']}\n"
        msg += f"💵 Min Investment: {ipo['min_investment']}\n"
        msg += f"📅 Closes: {ipo['close_date']}\n"
        msg += f"📊 GMP: {ipo['gmp']}\n"
        msg += f"🎯 Expected Gain: {ipo['expected_gain']}\n"
        msg += f"⭐ View: {ipo['recommendation']}\n"
        msg += "\n━━━━━━━━━━━━━━━━━━━━━━\n"

    msg += "\n⚠️ GMP is unofficial and not investment advice."
    return msg

def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        raise ValueError("BOT_TOKEN or CHAT_ID missing")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        },
        timeout=20,
    )

    response.raise_for_status()

def main():
    message = build_message()
    send_telegram_message(message)

if __name__ == "__main__":
    main()
