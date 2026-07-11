import html
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

IST = ZoneInfo("Asia/Kolkata")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Liquid NSE names only. Add/remove symbols later as needed.
WATCHLIST = [
    "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS",
    "KOTAKBANK.NS", "TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS",
    "LT.NS", "BHARTIARTL.NS", "MARUTI.NS", "M&M.NS", "TATAMOTORS.NS",
    "SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "ITC.NS", "HINDUNILVR.NS",
    "ASIANPAINT.NS", "TITAN.NS", "ULTRACEMCO.NS", "NTPC.NS", "POWERGRID.NS",
    "COALINDIA.NS", "ONGC.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "BAJFINANCE.NS",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


@dataclass
class Setup:
    symbol: str
    close: float
    entry_low: float
    entry_high: float
    stop_loss: float
    target_1: float
    target_2: float
    score: int
    volume_ratio: float
    rsi: float
    breakout_level: float
    risk_percent: float
    latest_date: str


def send_telegram(message: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("BOT_TOKEN or CHAT_ID is missing.")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    response.raise_for_status()


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = frame["Close"].shift(1)
    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def normalize_download(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if raw.empty:
        return raw

    frame = raw.copy()

    if isinstance(frame.columns, pd.MultiIndex):
        if ticker in frame.columns.get_level_values(-1):
            frame = frame.xs(ticker, axis=1, level=-1)
        elif ticker in frame.columns.get_level_values(0):
            frame = frame.xs(ticker, axis=1, level=0)

    required = ["Open", "High", "Low", "Close", "Volume"]
    if not all(column in frame.columns for column in required):
        return pd.DataFrame()

    return frame[required].dropna()


def analyse_ticker(ticker: str) -> Setup | None:
    try:
        raw = yf.download(
            ticker,
            period="9mo",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        frame = normalize_download(raw, ticker)

        if len(frame) < 80:
            logging.info("%s skipped: insufficient data", ticker)
            return None

        frame["EMA20"] = frame["Close"].ewm(span=20, adjust=False).mean()
        frame["EMA50"] = frame["Close"].ewm(span=50, adjust=False).mean()
        frame["RSI14"] = calculate_rsi(frame["Close"])
        frame["ATR14"] = calculate_atr(frame)
        frame["VOL20"] = frame["Volume"].rolling(20).mean()
        frame["PREV_20D_HIGH"] = frame["High"].shift(1).rolling(20).max()
        frame["RETURN20"] = frame["Close"].pct_change(20) * 100

        last = frame.iloc[-1]
        close = float(last["Close"])
        ema20 = float(last["EMA20"])
        ema50 = float(last["EMA50"])
        rsi = float(last["RSI14"])
        atr = float(last["ATR14"])
        prev_high = float(last["PREV_20D_HIGH"])
        return20 = float(last["RETURN20"])
        volume_average = float(last["VOL20"])
        volume_ratio = (
            float(last["Volume"]) / volume_average
            if volume_average > 0
            else 0.0
        )
        atr_percent = (atr / close) * 100 if close > 0 else 0.0

        checks = {
            "trend": close > ema20 > ema50,
            "breakout": close > prev_high,
            "volume": volume_ratio >= 1.50,
            "momentum": 55 <= rsi <= 70,
            "not_overextended": 0 < return20 <= 20,
            "controlled_volatility": 1.0 <= atr_percent <= 5.0,
        }
        score = sum(checks.values())

        # Publish only when every strict rule passes.
        if score < len(checks):
            logging.info("%s rejected: %s (%s/6)", ticker, checks, score)
            return None

        recent_swing_low = float(frame["Low"].iloc[-11:-1].min())
        breakout_stop = prev_high - (0.50 * atr)
        atr_stop = close - (1.50 * atr)
        stop_loss = min(breakout_stop, atr_stop)

        # Avoid setups with an impractically wide or tiny stop.
        risk = close - stop_loss
        risk_percent = (risk / close) * 100
        if risk <= 0 or not 2.0 <= risk_percent <= 8.0:
            logging.info("%s rejected: risk %.2f%%", ticker, risk_percent)
            return None

        # If the recent swing low is close enough, place the stop below it.
        if recent_swing_low < close and ((close - recent_swing_low) / close) * 100 <= 8:
            stop_loss = min(stop_loss, recent_swing_low - (0.10 * atr))
            risk = close - stop_loss
            risk_percent = (risk / close) * 100

        if risk_percent > 8:
            logging.info("%s rejected after swing-low adjustment: risk %.2f%%", ticker, risk_percent)
            return None

        entry_low = close
        entry_high = close + (0.20 * atr)
        target_1 = entry_low + (2.0 * risk)
        target_2 = entry_low + (3.0 * risk)

        latest_date = pd.Timestamp(frame.index[-1]).strftime("%d %b %Y")

        return Setup(
            symbol=ticker.replace(".NS", ""),
            close=close,
            entry_low=entry_low,
            entry_high=entry_high,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            score=score,
            volume_ratio=volume_ratio,
            rsi=rsi,
            breakout_level=prev_high,
            risk_percent=risk_percent,
            latest_date=latest_date,
        )

    except Exception:
        logging.exception("Failed to analyse %s", ticker)
        return None


def find_best_setup() -> Setup | None:
    candidates: list[Setup] = []

    for ticker in WATCHLIST:
        setup = analyse_ticker(ticker)
        if setup:
            candidates.append(setup)

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (item.score, item.volume_ratio),
        reverse=True,
    )
    return candidates[0]


def build_message(setup: Setup | None) -> str:
    now = datetime.now(IST)

    header = (
        "📈 <b>HIGH-CONVICTION SWING SCANNER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {now.strftime('%d %b %Y, %I:%M %p')} IST\n"
    )

    if now.weekday() >= 5:
        return (
            header
            + "\n⏸ <b>No fresh setup today</b>\n"
            + "Reason: Indian equity market is closed for the weekend.\n\n"
            + "The scanner will evaluate fresh daily data on the next trading day.\n\n"
            + "⚠️ No trade is guaranteed. Educational use only."
        )

    if setup is None:
        return (
            header
            + "\n❌ <b>NO TRADE TODAY</b>\n\n"
            + "No stock in the liquid watchlist passed every strict rule:\n"
            + "• Uptrend above 20 & 50 EMA\n"
            + "• Fresh 20-day breakout\n"
            + "• Volume ≥ 1.5× average\n"
            + "• RSI between 55 and 70\n"
            + "• Not excessively extended\n"
            + "• Controlled volatility\n\n"
            + "Waiting is better than forcing a weak trade.\n\n"
            + "⚠️ No trade is guaranteed. Educational use only."
        )

    name = html.escape(setup.symbol)

    return (
        header
        + f"\n✅ <b>QUALIFYING SETUP: {name}</b>\n"
        + f"📊 Data through: {setup.latest_date}\n"
        + "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        + f"💰 <b>Entry zone:</b> ₹{setup.entry_low:.2f}–₹{setup.entry_high:.2f}\n"
        + f"🛑 <b>Stop loss:</b> ₹{setup.stop_loss:.2f}\n"
        + f"🎯 <b>Target 1:</b> ₹{setup.target_1:.2f}\n"
        + f"🎯 <b>Target 2:</b> ₹{setup.target_2:.2f}\n"
        + "⏳ <b>Indicative horizon:</b> 2–8 weeks\n\n"
        + f"📌 Setup score: {setup.score}/6\n"
        + f"📈 Volume: {setup.volume_ratio:.2f}× 20-day average\n"
        + f"⚡ RSI(14): {setup.rsi:.1f}\n"
        + f"🧱 Breakout level: ₹{setup.breakout_level:.2f}\n"
        + f"⚖️ Risk to stop: {setup.risk_percent:.2f}%\n\n"
        + "Execution rule:\n"
        + "• Enter only inside the stated zone.\n"
        + "• Skip if price gaps above the zone.\n"
        + "• Respect the stop loss; do not average down.\n\n"
        + "⚠️ This is a rules-based market setup, not a guaranteed profit or personalised investment recommendation."
    )


def main() -> None:
    setup = find_best_setup()
    message = build_message(setup)
    send_telegram(message)
    logging.info("Stock scanner message sent successfully.")


if __name__ == "__main__":
    main()
