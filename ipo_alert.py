import os, requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

URL = "https://www.investorgain.com/report/live-ipo-gmp/331/"

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg}
    )

def main():
    html = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}).text
    soup = BeautifulSoup(html, "html.parser")

    rows = soup.find_all("tr")
    msg = "📊 Daily IPO GMP Update\n\n"

    count = 0
    for row in rows[1:15]:
        cols = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        if len(cols) < 4:
            continue

        count += 1
        msg += f"{count}. {cols[0]}\n"
        msg += f"Details: {' | '.join(cols[1:6])}\n\n"

    if count == 0:
        msg += "No IPO GMP data found today."

    send(msg)

if __name__ == "__main__":
    main()
