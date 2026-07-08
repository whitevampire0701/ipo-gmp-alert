import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

URL = "https://www.finowings.com/IPO/live-ipo-gmp.php"

def send_telegram(message):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
        timeout=20
    )

def clean(x):
    return " ".join(str(x).replace("\n", " ").split()).strip()

def calc_gain(price, gmp):
    try:
        price = float(str(price).replace("₹", "").replace(",", "").strip())
        gmp = float(str(gmp).replace("₹", "").replace(",", "").strip())
        if price <= 0:
            return "-"
        return f"{(gmp / price) * 100:.2f}%"
    except:
        return "-"

def main():
    html = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    rows = soup.find_all("tr")
    today = datetime.now().strftime("%d %b %Y")

    mainboard = []
    sme = []

    for row in rows:
        cols = [clean(c.get_text(" ", strip=True)) for c in row.find_all(["td", "th"])]

        if len(cols) < 7:
            continue

        name, price, gmp, size, open_date, close_date, listing = cols[:7]

        if name.lower() in ["ipo name", ""]:
            continue

        gain = calc_gain(price, gmp)

        item = {
            "name": name.replace("Apply Now", "").strip(),
            "price": price,
            "gmp": gmp,
            "gain": gain,
            "size": size,
            "open": open_date,
            "close": close_date,
            "listing": listing
        }

        if "sme" in name.lower():
            sme.append(item)
        else:
            mainboard.append(item)

    msg = f"📈 <b>IPO GMP Morning Report</b>\n"
    msg += f"📅 <b>{today}</b>\n\n"

    if mainboard:
        msg += "🟢 <b>Mainboard IPOs</b>\n\n"
        for ipo in mainboard[:8]:
            msg += f"🏢 <b>{ipo['name']}</b>\n"
            msg += f"💰 Price: ₹{ipo['price']}\n"
            msg += f"🔥 GMP: ₹{ipo['gmp']}\n"
            msg += f"📈 Est. Gain: {ipo['gain']}\n"
            msg += f"📦 Issue Size: ₹{ipo['size']}\n"
            msg += f"📅 Open: {ipo['open']}\n"
            msg += f"⏰ Close: {ipo['close']}\n"
            msg += f"🚀 Listing: {ipo['listing']}\n"
            msg += "━━━━━━━━━━━━━━━\n"

    if sme:
        msg += "\n🟡 <b>SME IPOs</b>\n\n"
        for ipo in sme[:8]:
            msg += f"🏢 <b>{ipo['name']}</b>\n"
            msg += f"💰 Price: ₹{ipo['price']}\n"
            msg += f"🔥 GMP: ₹{ipo['gmp']}\n"
            msg += f"📈 Est. Gain: {ipo['gain']}\n"
            msg += f"📦 Issue Size: ₹{ipo['size']}\n"
            msg += f"📅 Open: {ipo['open']}\n"
            msg += f"⏰ Close: {ipo['close']}\n"
            msg += f"🚀 Listing: {ipo['listing']}\n"
            msg += "━━━━━━━━━━━━━━━\n"

    if not mainboard and not sme:
        msg += "No IPO GMP data found today.\n"

    msg += "\n⚠️ GMP is unofficial and changes frequently."

    send_telegram(msg)

if __name__ == "__main__":
    main()
