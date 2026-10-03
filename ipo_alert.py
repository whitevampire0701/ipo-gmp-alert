import os
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SOURCE_URL = "https://ipomarkets.com/"
IST = ZoneInfo("Asia/Kolkata")

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/143.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def fetch_page(url, retries=MAX_RETRIES):
    """
    Fetch webpage with retries.
    Returns HTML or None.
    """

    for attempt in range(1, retries + 1):
        try:
            logging.info(f"Fetching: {url}")

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT
            )

            response.raise_for_status()

            if not response.text:
                raise ValueError("Empty response")

            logging.info(
                f"Fetched successfully: {url} "
                f"({len(response.text)} bytes)"
            )

            return response.text

        except Exception as e:
            logging.warning(
                f"Fetch failed ({attempt}/{retries}) "
                f"{url}: {e}"
            )

            if attempt < retries:
                time.sleep(3)

    return None


def parse_number(text):
    """
    Extract first number from text.
    Supports:
    1,600
    ₹14,960
    15.31%
    """

    if text is None:
        return None

    text = str(text).replace(",", "")

    match = re.search(r"-?\d+(?:\.\d+)?", text)

    if not match:
        return None

    try:
        return float(match.group())
    except Exception:
        return None


def parse_integer(text):
    value = parse_number(text)

    if value is None:
        return None

    return int(value)


def money(value):
    if value is None:
        return "Data unavailable"

    return f"₹{int(round(value)):,}"


def format_date(d):
    if not d:
        return "Data unavailable"

    return d.strftime("%d %b %Y")


# ============================================================
# DATE PARSING
# ============================================================

DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"(?:\s+(\d{4}))?",
    re.IGNORECASE
)


def parse_single_date(text, default_year=None):
    """
    Parse dates such as:
    5 Oct 2026
    5 Oct
    30 Sept 2026
    """

    if not text:
        return None

    text = clean(text)

    match = DATE_PATTERN.search(text)

    if not match:
        return None

    day = int(match.group(1))
    month_text = match.group(2).lower()
    year = match.group(3)

    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "sept": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    month = months.get(month_text[:3])

    if not month:
        return None

    if year:
        year = int(year)
    else:
        year = default_year or datetime.now(IST).year

    try:
        return date(year, month, day)
    except Exception:
        return None


def parse_open_close(text):
    """
    Parses:
    30 Sept 2026 – 5 Oct 2026
    """

    if not text:
        return None, None

    text = clean(text)

    matches = list(DATE_PATTERN.finditer(text))

    if len(matches) < 2:
        return None, None

    first = matches[0]
    second = matches[1]

    first_text = first.group(0)
    second_text = second.group(0)

    open_date = parse_single_date(first_text)

    # If second date has no year, use open date year
    second_year = open_date.year if open_date else datetime.now(IST).year

    close_date = parse_single_date(
        second_text,
        default_year=second_year
    )

    # Handle year rollover just in case
    if open_date and close_date and close_date < open_date:
        try:
            close_date = date(
                close_date.year + 1,
                close_date.month,
                close_date.day
            )
        except Exception:
            pass

    return open_date, close_date


# ============================================================
# PRICE PARSING
# ============================================================

def parse_price_band(text):
    """
    Converts:

    ₹208–₹220
    ₹77–₹82
    ₹55

    into:

    low
    high
    display
    """

    if not text:
        return None, None

    nums = re.findall(
        r"\d+(?:,\d+)*(?:\.\d+)?",
        text.replace("₹", "")
    )

    values = []

    for n in nums:
        try:
            values.append(float(n.replace(",", "")))
        except Exception:
            pass

    if not values:
        return None, None

    low = min(values)
    high = max(values)

    return low, high


# ============================================================
# GMP
# ============================================================

def parse_gmp(text):
    """
    Examples:

    ₹27+12.27%
    ₹20+9.09%
    ₹0
    ₹15.25+9.13%
    """

    if not text:
        return None, None

    text = clean(text)

    rupee_match = re.search(
        r"₹\s*(-?\d+(?:\.\d+)?)",
        text
    )

    gmp = None

    if rupee_match:
        try:
            gmp = float(rupee_match.group(1))
        except Exception:
            pass

    percent_match = re.search(
        r"([+-]?\d+(?:\.\d+)?)\s*%",
        text
    )

    gmp_percent = None

    if percent_match:
        try:
            gmp_percent = float(percent_match.group(1))
        except Exception:
            pass

    return gmp, gmp_percent


# ============================================================
# LOT / MINIMUM INVESTMENT
# ============================================================

def parse_lot_min(text):
    """
    Examples:

    Lot / min
    68 sh
    ₹14,960

    or

    1,600 sh
    ₹2,84,800
    """

    if not text:
        return None, None

    text = clean(text)

    # Number of shares
    share_match = re.search(
        r"([\d,]+)\s*sh",
        text,
        re.IGNORECASE
    )

    shares = None

    if share_match:
        try:
            shares = int(
                share_match.group(1).replace(",", "")
            )
        except Exception:
            pass

    # Minimum amount
    amount_match = re.search(
        r"₹\s*([\d,]+(?:\.\d+)?)",
        text
    )

    amount = None

    if amount_match:
        try:
            amount = float(
                amount_match.group(1).replace(",", "")
            )
        except Exception:
            pass

    return shares, amount


# ============================================================
# FIND IPO LINKS ON MAIN PAGE
# ============================================================

def find_ipo_links(html):
    """
    Finds individual IPO detail pages from IPOMarkets homepage.
    """

    soup = BeautifulSoup(html, "html.parser")

    links = {}

    for a in soup.find_all("a", href=True):

        href = a.get("href", "").strip()

        if "/ipo/" not in href:
            continue

        full_url = urljoin(SOURCE_URL, href)

        name = clean(a.get_text(" ", strip=True))

        # Skip empty anchor text
        if not name:
            continue

        links[full_url] = name

    logging.info(
        f"Found {len(links)} IPO detail links"
    )

    return links


# ============================================================
# PARSE INDIVIDUAL IPO PAGE
# ============================================================

def parse_ipo_detail(url, fallback_name=None):

    html = fetch_page(url)

    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Get clean page text
    text = clean(
        soup.get_text(" ", strip=True)
    )

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    name = fallback_name

    h1 = soup.find("h1")

    if h1:
        possible_name = clean(h1.get_text(" ", strip=True))

        if possible_name:
            name = possible_name

    if not name:
        return None

    # Remove common suffix
    name = re.sub(
        r"\s+IPO\s*$",
        "",
        name,
        flags=re.IGNORECASE
    ).strip()

    # --------------------------------------------------------
    # TYPE
    # --------------------------------------------------------

    ipo_type = "Unknown"

    if re.search(r"\bSME\b", text, re.IGNORECASE):
        ipo_type = "SME"
    elif re.search(r"\bMainboard\b", text, re.IGNORECASE):
        ipo_type = "Mainboard"

    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

    price_low = None
    price_high = None

    price_match = re.search(
        r"Price\s+(?:band|range)?\s*₹?\s*([\d,]+)"
        r"(?:\s*[–\-]\s*₹?\s*([\d,]+))?",
        text,
        re.IGNORECASE
    )

    if price_match:

        try:
            price_low = float(
                price_match.group(1).replace(",", "")
            )

            if price_match.group(2):
                price_high = float(
                    price_match.group(2).replace(",", "")
                )
            else:
                price_high = price_low

        except Exception:
            pass

    # Fallback: look for "Price band"
    if price_high is None:

        match = re.search(
            r"Price band\s+₹?([\d,]+)"
            r"(?:\s*[–\-]\s*₹?([\d,]+))?",
            text,
            re.IGNORECASE
        )

        if match:
            price_low = float(
                match.group(1).replace(",", "")
            )

            if match.group(2):
                price_high = float(
                    match.group(2).replace(",", "")
                )
            else:
                price_high = price_low

    # --------------------------------------------------------
    # OPEN / CLOSE
    # --------------------------------------------------------

    open_date = None
    close_date = None

    date_match = re.search(
        r"Open\s*[–\-]\s*Close\s+"
        r"(.{5,40}?)"
        r"(?:\s+\d+\s+days?\s+open|\s+Closes?\s+in|\s+Issue size|\s+Subscription)",
        text,
        re.IGNORECASE
    )

    if date_match:

        date_text = clean(date_match.group(1))

        open_date, close_date = parse_open_close(
            date_text
        )

    # More direct fallback
    if not open_date or not close_date:

        date_match = re.search(
            r"Open\s*[–\-]\s*Close\s+"
            r"(\d{1,2}\s+\w+\s+\d{4})"
            r"\s*[–\-]\s*"
            r"(\d{1,2}\s+\w+\s+\d{4})",
            text,
            re.IGNORECASE
        )

        if date_match:

            open_date = parse_single_date(
                date_match.group(1)
            )

            close_date = parse_single_date(
                date_match.group(2)
            )

    # --------------------------------------------------------
    # LOT SIZE / MINIMUM INVESTMENT
    # --------------------------------------------------------

    lot_shares = None
    min_investment = None

    lot_match = re.search(
        r"Lot\s*/\s*min\s+"
        r"([\d,]+)\s*sh\s+"
        r"₹\s*([\d,]+)",
        text,
        re.IGNORECASE
    )

    if lot_match:

        try:
            lot_shares = int(
                lot_match.group(1).replace(",", "")
            )

            min_investment = float(
                lot_match.group(2).replace(",", "")
            )

        except Exception:
            pass

    # Another fallback
    if lot_shares is None:

        lot_match = re.search(
            r"Lot\s*/\s*min.*?"
            r"([\d,]+)\s*sh.*?"
            r"₹\s*([\d,]+)",
            text,
            re.IGNORECASE
        )

        if lot_match:

            try:
                lot_shares = int(
                    lot_match.group(1).replace(",", "")
                )

                min_investment = float(
                    lot_match.group(2).replace(",", "")
                )

            except Exception:
                pass

    # --------------------------------------------------------
    # GMP
    # --------------------------------------------------------

    gmp = None
    gmp_percent = None

    # First try the main GMP display
    gmp_match = re.search(
        r"Grey market premium.*?"
        r"₹\s*(-?\d+(?:\.\d+)?)"
        r"\s*([+-]?\d+(?:\.\d+)?)?%",
        text,
        re.IGNORECASE
    )

    if gmp_match:

        try:
            gmp = float(gmp_match.group(1))
        except Exception:
            pass

        if gmp_match.group(2):

            try:
                gmp_percent = float(
                    gmp_match.group(2)
                )
            except Exception:
                pass

    # Handle zero GMP where percentage may not exist
    if gmp is None:

        gmp_match = re.search(
            r"Grey market premium.*?"
            r"₹\s*(-?\d+(?:\.\d+)?)",
            text,
            re.IGNORECASE
        )

        if gmp_match:

            try:
                gmp = float(
                    gmp_match.group(1)
                )
            except Exception:
                pass

    # Calculate percentage ourselves if necessary
    if (
        gmp_percent is None
        and gmp is not None
        and price_high
        and price_high > 0
    ):

        gmp_percent = (
            gmp / price_high
        ) * 100

        gmp_percent = round(
            gmp_percent,
            2
        )

    # --------------------------------------------------------
    # ESTIMATED LISTING PRICE
    # --------------------------------------------------------

    estimated_listing = None

    if price_high is not None and gmp is not None:

        estimated_listing = (
            price_high + gmp
        )

    # --------------------------------------------------------
    # ESTIMATED GAIN
    # --------------------------------------------------------

    estimated_gain_per_share = None
    estimated_gain_per_lot = None

    if (
        gmp is not None
        and lot_shares is not None
    ):

        estimated_gain_per_share = gmp

        estimated_gain_per_lot = (
            gmp * lot_shares
        )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    today = datetime.now(IST).date()

    if open_date and open_date > today:
        status = "UPCOMING"

    elif close_date and close_date >= today:
        status = "ACTIVE"

    else:
        status = "CLOSED"

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return {
        "name": name,
        "type": ipo_type,
        "url": url,

        "open_date": open_date,
        "close_date": close_date,

        "price_low": price_low,
        "price_high": price_high,

        "lot_shares": lot_shares,
        "min_investment": min_investment,

        "gmp": gmp,
        "gmp_percent": gmp_percent,

        "estimated_listing": estimated_listing,

        "estimated_gain_per_share":
            estimated_gain_per_share,

        "estimated_gain_per_lot":
            estimated_gain_per_lot,

        "status": status,
    }


# ============================================================
# DISCOVER ACTIVE / UPCOMING IPOs
# ============================================================

def get_active_upcoming_ipos():

    html = fetch_page(SOURCE_URL)

    if not html:
        raise RuntimeError(
            "Could not fetch IPOMarkets homepage"
        )

    links = find_ipo_links(html)

    if not links:
        raise RuntimeError(
            "No IPO detail links found. "
            "The source website structure may have changed."
        )

    results = []

    for url, fallback_name in links.items():

        try:

            ipo = parse_ipo_detail(
                url,
                fallback_name
            )

            if not ipo:
                continue

            # Only active/upcoming
            if ipo["status"] not in (
                "ACTIVE",
                "UPCOMING"
            ):
                continue

            results.append(ipo)

            logging.info(
                f"IPO found: "
                f"{ipo['name']} | "
                f"{ipo['status']} | "
                f"{ipo['close_date']}"
            )

        except Exception as e:

            logging.warning(
                f"Could not parse {url}: {e}"
            )

    # Remove duplicates
    unique = {}

    for ipo in results:
        key = ipo["name"].lower().strip()
        unique[key] = ipo

    results = list(unique.values())

    # Sort:
    # Active first, then closing date
    results.sort(
        key=lambda x: (
            0 if x["status"] == "ACTIVE" else 1,
            x["close_date"] or date.max
        )
    )

    return results


# ============================================================
# DISPLAY HELPERS
# ============================================================

def format_price(ipo):

    low = ipo["price_low"]
    high = ipo["price_high"]

    if low is None:
        return "Data unavailable"

    if high is None:
        return money(low)

    if low == high:
        return money(low)

    return f"{money(low)}–{money(high)}"


def format_gmp(ipo):

    gmp = ipo["gmp"]
    percent = ipo["gmp_percent"]

    if gmp is None:
        return "Unavailable"

    if percent is None:
        return money(gmp)

    return (
        f"{money(gmp)} "
        f"({percent:.2f}%)"
    )


def get_gmp_signal(percent):

    if percent is None:
        return "⚪ GMP unavailable"

    if percent >= 25:
        return "🟢 Strong GMP"

    if percent >= 10:
        return "🟡 Positive GMP"

    if percent > 0:
        return "🟠 Low GMP"

    if percent == 0:
        return "⚪ No GMP"

    return "🔴 Negative GMP"


def format_investment(amount):

    if amount is None:
        return "Data unavailable"

    amount = int(round(amount))

    # Useful human-readable form
    if amount >= 100000:
        return f"₹{amount:,} (~₹{amount / 100000:.2f}L)"

    if amount >= 1000:
        return f"₹{amount:,} (~₹{amount / 1000:.1f}K)"

    return f"₹{amount:,}"


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def build_message(ipos):

    now = datetime.now(IST).strftime(
        "%d %b %Y, %I:%M %p"
    )

    message = (
        "📊 <b>PERSONAL INVESTMENT ASSISTANT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {now}\n"
        "🟢 Status: Data fetched successfully\n\n"
    )

    message += (
        f"🔥 <b>ACTIVE / UPCOMING IPOs "
        f"({len(ipos)})</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    if not ipos:

        message += (
            "\n⚪ No active/upcoming IPOs found.\n\n"
            "This is a genuine zero result after "
            "checking the data source."
        )

        return message

    for index, ipo in enumerate(ipos, 1):

        status_icon = (
            "🟢"
            if ipo["status"] == "ACTIVE"
            else "🔵"
        )

        message += "\n"

        message += (
            f"{index}️⃣ "
            f"<b>{ipo['name']}</b>\n"
        )

        message += (
            f"{status_icon} "
            f"<b>{ipo['status']}</b>"
        )

        if ipo["type"] != "Unknown":
            message += f" | {ipo['type']}"

        message += "\n"

        # Dates
        message += (
            f"🟢 Opens: "
            f"{format_date(ipo['open_date'])}\n"
        )

        message += (
            f"🔴 Closes: "
            f"{format_date(ipo['close_date'])}\n"
        )

        # Price
        message += (
            f"💰 Price: "
            f"{format_price(ipo)}\n"
        )

        # Lot
        if ipo["lot_shares"]:

            message += (
                f"📦 Lot Size: "
                f"{ipo['lot_shares']:,} shares\n"
            )

        else:

            message += (
                "📦 Lot Size: Data unavailable\n"
            )

        # Minimum investment
        message += (
            f"💵 Min Investment: "
            f"{format_investment(ipo['min_investment'])}\n"
        )

        # GMP
        message += (
            f"📊 GMP: "
            f"{format_gmp(ipo)}\n"
        )

        # GMP signal
        message += (
            f"📈 "
            f"{get_gmp_signal(ipo['gmp_percent'])}\n"
        )

        # Estimated listing
        if ipo["estimated_listing"]:

            message += (
                f"🎯 Est. Listing: "
                f"{money(ipo['estimated_listing'])}\n"
            )

        else:

            message += (
                "🎯 Est. Listing: "
                "Data unavailable\n"
            )

        # Estimated gain
        if ipo["estimated_gain_per_lot"]:

            message += (
                f"💰 Est. GMP Gain/Lot: "
                f"{money(ipo['estimated_gain_per_lot'])}\n"
            )

        # Source
        message += (
            f"🔗 "
            f'<a href="{ipo["url"]}">View IPO Details</a>\n'
        )

        message += (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
        )

    message += (
        "\n⚠️ <b>Important:</b>\n"
        "GMP is unofficial and can change frequently. "
        "It is not a guaranteed listing price.\n"
        "Minimum investment and lot size are taken "
        "from the IPO detail data when available.\n"
        "Always verify the final IPO details before applying."
    )

    return message


# ============================================================
# ERROR MESSAGE
# ============================================================

def build_error_message(error):

    now = datetime.now(IST).strftime(
        "%d %b %Y, %I:%M %p"
    )

    return (
        "📊 <b>PERSONAL INVESTMENT ASSISTANT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {now}\n"
        "🔴 Status: IPO DATA FETCH FAILED\n\n"
        "The Telegram bot is running, but the IPO "
        "data source could not be read.\n\n"
        f"❌ Error:\n<code>{str(error)[:1000]}</code>\n\n"
        "This message is intentionally NOT showing "
        "0 IPOs so that a scraper failure is not "
        "mistaken for an empty IPO market."
    )


# ============================================================
# SEND TELEGRAM
# ============================================================

def send_telegram_message(message):

    if not BOT_TOKEN:
        raise ValueError(
            "BOT_TOKEN GitHub Secret is missing"
        )

    if not CHAT_ID:
        raise ValueError(
            "CHAT_ID GitHub Secret is missing"
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram API error: {result}"
        )

    logging.info(
        "Telegram message sent successfully"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    logging.info(
        "=================================================="
    )

    logging.info(
        "Starting IPO Personal Investment Assistant"
    )

    logging.info(
        "=================================================="
    )

    try:

        ipos = get_active_upcoming_ipos()

        logging.info(
            f"Total active/upcoming IPOs: {len(ipos)}"
        )

        message = build_message(ipos)

        send_telegram_message(message)

        logging.info(
            "IPO report completed successfully"
        )

    except Exception as e:

        logging.exception(
            "IPO processing failed"
        )

        # Send an explicit error to Telegram
        # instead of falsely reporting 0 IPOs.
        try:

            error_message = build_error_message(e)

            send_telegram_message(
                error_message
            )

        except Exception:

            logging.exception(
                "Could not send error message"
            )

        # Important:
        # Make GitHub Actions visibly fail.
        raise


if __name__ == "__main__":
    main()
