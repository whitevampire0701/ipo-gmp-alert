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

URL = "https://www.ipopremium.in/"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def money(value):
    return f"₹{int(value):,}"


def fetch_page(url, retries=3):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=25)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logging.warning(f"Fetch failed attempt {attempt + 1}: {e}")
            time.sleep(3)

    return None


def extract_number(text):
    if not text:
        return None

    match = re.search(r"-?\d+(\.\d+)?", text.replace(",", ""))
    return float(match.group()) if match else None


def extract_price_high(price_text):
    nums = re.findall(r"\d+(\.\d+)?", price_text.replace(",", ""))
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", price_text.replace(",", ""))]
    return max(nums) if nums else None


def calculate_gmp_percent(price, gmp):
    price_num = extract_price_high(price)
    gmp_num = extract_number(gmp)

    if price_num and gmp_num is not None:
        return round((gmp_num / price_num) * 100, 2)

    return None


def parse_ipopremium():
    html = fetch_page(URL)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    ipos = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        headers = [clean(h.get_text(" ")) for h in rows[0].find_all(["th", "td"])]
        headers_lower = [h.lower() for h in headers]

        if not any("company" in h for h in headers_lower):
            continue
        if not any("gmp" in h for h in headers_lower):
            continue
        if not any("close" in h for h in headers_lower):
            continue
        if not any("price" in h for h in headers_lower):
            continue

        for row in rows[1:]:
            cols = [clean(td.get_text(" ")) for td in row.find_all("td")]

            if len(cols) < len(headers):
                continue

            data = dict(zip(headers_lower, cols))

            name = next((data[h] for h in data if "company" in h), "")
            gmp = next((data[h] for h in data if "gmp" in h), "Data unavailable")
            open_date = next((data[h] for h in data if "open" in h), "Data unavailable")
            close_date = next((data[h] for h in data if "close" in h), "Data unavailable")
            price = next((data[h] for h in data if "price" in h), "Data unavailable")
            lot_size = next((data[h] for h in data if "lot" in h), "Data unavailable")

            if not name or name.lower() in ["company name", "rumors"]:
                continue

            gmp_percent = calculate_gmp_percent(price, gmp)

            lot_num = extract_number(lot_size)
            price_num = extract_price_high(price)

            min_investment = "Data unavailable"
            if lot_num and price_num:
                min_investment = money(lot_num * price_num)

            if gmp_percent is None:
                gmp_display = gmp
                expected_gain = "Data unavailable"
                view = "WAIT"
            else:
                gmp_display = f"{gmp} ({gmp_percent}%)"

                if gmp_percent >= 25:
                    expected_gain = "High"
                    view = "APPLY"
                elif gmp_percent >= 10:
                    expected_gain = "Moderate"
                    view = "MAY APPLY"
                elif gmp_percent > 0:
                    expected_gain = "Low"
                    view = "AVOID / WAIT"
                else:
                    expected_gain = "Flat / Negative"
                    view = "AVOID"

            ipos.append({
                "name": name,
                "open_date": open_date,
                "close_date": close_date,
                "price": price,
                "lot_size": lot_size,
                "min_investment": min_investment,
                "gmp": gmp_display,
                "expected_gain": expected_gain,
                "view": view,
            })

    return ipos[:10]


def build_message():
    now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p")
    ipos = parse_ipopremium()

    msg = "📊 <b>PERSONAL INVESTMENT ASSISTANT</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📅 {now}\n"
    msg += "🟢 Status: Bot running successfully\n\n"
    msg += f"🔥 <b>LIVE IPOs ({len(ipos)})</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"

    if not ipos:
        msg += "\nNo live IPO data available right now.\n"
        msg += "Bot is working, but IPO source did not return usable data.\n"
        return msg

    for i, ipo in enumerate(ipos, 1):
        msg += f"\n{i}️⃣ <b>{ipo['name']}</b>\n"
        msg += f"🟢 Opens: {ipo['open_date']}\n"
        msg += f"📅 Closes: {ipo['close_date']}\n"
        msg += f"💰 Price: {ipo['price']}\n"
        msg += f"📦 Lot Size: {ipo['lot_size']}\n"
        msg += f"💵 Min Investment: {ipo['min_investment']}\n"
        msg += f"📊 GMP: {ipo['gmp']}\n"
        msg += f"🎯 Expected Gain: {ipo['expected_gain']}\n"
        msg += f"⭐ View: {ipo['view']}\n"
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
    send_telegram_message(build_message())


if __name__ == "__main__":
    main()
