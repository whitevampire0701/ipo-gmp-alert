import os, time, requests
from bs4 import BeautifulSoup
from datetime import datetime

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

SOURCES = [
    "https://www.finowings.com/IPO/live-ipo-gmp.php",
    "https://www.investorgain.com/report/ipo-gmp-live/331/",
]

def send_telegram(message):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
        timeout=30
    )

def clean(x):
    return " ".join(str(x).replace("\n", " ").split()).strip()

def fetch_url(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-IN,en;q=0.9"
    }

    for _ in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=45)
            if r.status_code == 200 and len(r.text) > 1000:
                return r.text
        except:
            time.sleep(5)

    return None

def calc_gain(price, gmp):
    try:
        price = float(str(price).replace("₹", "").replace(",", "").strip())
        gmp = float(str(gmp).replace("₹", "").replace(",", "").replace("--", "0").strip())
        if price <= 0 or gmp <= 0:
            return "-"
        return f"{(gmp / price) * 100:.2f}%"
    except:
        return "-"

def parse_finowings(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr")
    data = []

    for row in rows:
        cols = [clean(c.get_text(" ", strip=True)) for c in row.find_all(["td", "th"])]

        if len(cols) < 7:
            continue

        name, price, gmp, size, open_date, close_date, listing = cols[:7]

        if name.lower() in ["ipo name", ""]:
            continue

        data.append({
            "name": name.replace("Apply Now", "").strip(),
            "price": price,
            "gmp": gmp,
            "gain": calc_gain(price, gmp),
            "size": size,
            "open": open_date,
            "close": close_date,
            "listing": listing,
            "type": "SME" if "sme" in name.lower() else "Mainboard"
        })

    return data

def format_message(data, source):
    today = datetime.now().strftime("%d %b %Y")

    mainboard = [x for x in data if x["type"] == "Mainboard"]
    sme = [x for x in data if x["type"] == "SME"]

    msg = f"📈 <b>IPO GMP Morning Report</b>\n"
    msg += f"📅 <b>{today}</b>\n"
    msg += f"🔗 Source: {source}\n\n"

    def add_section(title, items):
        nonlocal msg
        if not items:
            return

        msg += f"{title}\n\n"

        for ipo in items[:8]:
            msg += f"🏢 <b>{ipo['name']}</b>\n"
            msg += f"💰 Price: ₹{ipo['price']}\n"
            msg += f"🔥 GMP: ₹{ipo['gmp']}\n"
            msg += f"📈 Est. Gain: {ipo['gain']}\n"
            msg += f"📦 Issue Size: ₹{ipo['size']}\n"
            msg += f"📅 Open: {ipo['open']}\n"
            msg += f"⏰ Close: {ipo['close']}\n"
            msg += f"🚀 Listing: {ipo['listing']}\n"
            msg += "━━━━━━━━━━━━━━━\n"

    add_section("🟢 <b>Mainboard IPOs</b>", mainboard)
    add_section("🟡 <b>SME IPOs</b>", sme)

    msg += "\n⚠️ GMP is unofficial and changes frequently."
    return msg

def main():
    for url in SOURCES:
        html = fetch_url(url)

        if not html:
            continue

        data = parse_finowings(html)

        if data:
            send_telegram(format_message(data, url))
            return

    today = datetime.now().strftime("%d %b %Y")
    send_telegram(
        f"📊 <b>IPO GMP Update - {today}</b>\n\n"
        "Unable to fetch IPO GMP data today.\n"
        "The source website may be slow or blocking requests.\n\n"
        "Bot is working ✅"
    )

if __name__ == "__main__":
    main()
