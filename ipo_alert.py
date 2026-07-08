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
    return " ".join(x.replace("\n", " ").split()).strip()

def main():
    html = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    today = datetime.now().strftime("%d %b %Y")
    msg = f"📊 <b>Daily IPO GMP Update - {today}</b>\n\n"

    rows = soup.find_all("tr")
    found = 0

    for row in rows:
        cols = [clean(c.get_text(" ", strip=True)) for c in row.find_all(["td", "th"])]
        if len(cols) < 4:
            continue

        row_text = " | ".join(cols)
        if "gmp" in row_text.lower() or any(char.isdigit() for char in row_text):
            found += 1
            msg += f"<b>{found}. {cols[0]}</b>\n"
            for item in cols[1:7]:
                msg += f"• {item}\n"
            msg += "\n"

        if found >= 12:
            break

    if found == 0:
        msg += "No detailed IPO GMP rows found today.\n"

    msg += "⚠️ GMP is unofficial and changes frequently."
    send_telegram(msg)

if __name__ == "__main__":
    main()
