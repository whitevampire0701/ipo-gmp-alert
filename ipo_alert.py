import os
import requests
import pandas as pd
from io import StringIO
from datetime import datetime

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

URLS = [
    "https://www.investorgain.com/report/ipo-gmp-live/331/",
]

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    })

def fetch_tables(url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))
    return tables

def clean(value):
    if pd.isna(value):
        return "-"
    return str(value).replace("\n", " ").strip()

def main():
    all_rows = []

    for url in URLS:
        try:
            tables = fetch_tables(url)
            for table in tables:
                cols = [str(c).lower() for c in table.columns]

                if any("gmp" in c for c in cols) or any("ipo" in c for c in cols):
                    for _, row in table.head(20).iterrows():
                        values = [clean(v) for v in row.tolist()]
                        if len(values) >= 3:
                            all_rows.append(values)
            if all_rows:
                break
        except Exception as e:
            continue

    today = datetime.now().strftime("%d %b %Y")

    if not all_rows:
        send_telegram(
            f"📊 <b>Daily IPO GMP Update - {today}</b>\n\n"
            "No IPO GMP table found today.\n"
            "The website may have changed or blocked scraping."
        )
        return

    msg = f"📊 <b>Daily IPO GMP Update - {today}</b>\n\n"

    for i, values in enumerate(all_rows[:12], start=1):
        msg += f"<b>{i}. {values[0]}</b>\n"

        labels = ["IPO", "Price", "GMP", "Est Listing", "Gain", "Lot", "Open", "Close"]
        for label, value in zip(labels[1:], values[1:8]):
            msg += f"{label}: {value}\n"

        msg += "\n"

    msg += "⚠️ GMP is unofficial and changes frequently. Use only as an indicator."

    send_telegram(msg)

if __name__ == "__main__":
    main()
