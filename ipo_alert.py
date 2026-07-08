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
    headers = {"User-Agent": "Mozilla/5.0"}
    html = requests.get(URL, headers=headers, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n", strip=True)

    today = datetime.now().strftime("%d %b %Y")
    msg = f"📊 <b>Daily IPO GMP Update - {today}</b>\n\n"

    keywords = [
        "Laser Power & Infra",
        "Kusumgar",
        "IC Electricals",
        "Knack Packaging",
        "Devson Catalyst",
        "Happy Steels",
        "Shree Balaji Mala",
        "Millworks Technologies",
        "SBI Funds Management",
    ]

    found = 0
    for name in keywords:
        if name.lower() in text.lower():
            found += 1
            msg += f"{found}. <b>{name}</b>\n"
            msg += "Status: Found in live GMP tracker\n\n"

    if found == 0:
        msg += "No IPO GMP data found from current source today.\n"

    msg += "⚠️ GMP is unofficial and changes frequently."

    send_telegram(msg)

if __name__ == "__main__":
    main()
