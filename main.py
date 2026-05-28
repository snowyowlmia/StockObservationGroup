#!/usr/bin/env python3
"""
Lulu AI Stock Card Bot
----------------------
Fetches data for every symbol in watchlist.txt, computes technical indicators,
pulls recent news, generates AI analysis cards via Claude, sorts by urgency,
then sends to Telegram and saves to output/.

Usage:
  python main.py                    # auto-detect session from current time (ET)
  python main.py --session open     # force morning session
  python main.py --session mid      # force midday session
  python main.py --session close    # force pre-close session
  python main.py --dry-run          # print to stdout only, no Telegram
"""
import argparse
import logging
import os
import sys
from datetime import datetime
from typing import Optional
from pathlib import Path

import pytz

# Make src importable whether running from repo root or via GitHub Actions
sys.path.insert(0, os.path.dirname(__file__))

from config import WATCHLIST_FILE, OUTPUT_DIR
from src.data_fetcher import fetch_ohlcv, fetch_info
from src.indicators import compute_indicators, fibonacci_levels, pivot_points, extract_latest
from src.news_fetcher import get_news, format_news_for_prompt
from src.scorer import rank_stocks
from src.card_generator import generate_card, build_daily_header
from src.telegram_sender import send_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

SESSION_LABELS = {
    "open": "09:45 ET 开盘分析",
    "mid": "13:00 ET 盘中分析",
    "close": "15:45 ET 收盘前分析",
}

ET = pytz.timezone("America/New_York")


def detect_session() -> str:
    now_et = datetime.now(ET)
    hour = now_et.hour
    if hour < 12:
        return "open"
    elif hour < 14:
        return "mid"
    else:
        return "close"


def load_watchlist() -> list[str]:
    path = Path(WATCHLIST_FILE)
    if not path.exists():
        logger.error(f"watchlist.txt not found at {WATCHLIST_FILE}")
        sys.exit(1)
    symbols = [line.strip().upper() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    if not symbols:
        logger.error("watchlist.txt is empty")
        sys.exit(1)
    logger.info(f"Watchlist: {symbols}")
    return symbols


def process_symbol(symbol: str) -> Optional[dict]:
    """Full pipeline for one symbol. Returns data dict or None on failure."""
    logger.info(f"Processing {symbol}...")

    df = fetch_ohlcv(symbol)
    if df is None:
        return None

    df = compute_indicators(df)
    ind = extract_latest(df)
    fib = fibonacci_levels(df)
    pivots = pivot_points(df)
    news_items = get_news(symbol, max_items=5)
    news_text = format_news_for_prompt(news_items)
    info = fetch_info(symbol)

    return {
        "symbol": symbol,
        "indicators": ind,
        "fib": fib,
        "pivots": pivots,
        "news_text": news_text,
        "info": info,
    }


def build_full_message(ranked: list[dict], session: str) -> str:
    header = build_daily_header(SESSION_LABELS[session])
    parts = [header]

    for i, stock in enumerate(ranked, 1):
        emoji = stock["urgency_emoji"]
        tag = stock["action_tag"]
        symbol = stock["symbol"]
        price = stock["indicators"].get("price", "?")
        chg = stock["indicators"].get("chg_1d_pct", 0)
        chg_str = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"

        # Section separator with rank
        divider = f"\n{emoji} #{i}  {tag}  ▸  {symbol} ${price} ({chg_str})\n{'─' * 42}"
        parts.append(divider)
        parts.append(stock["card"])

    parts.append(f"\n{'═' * 42}")
    parts.append(f"共分析 {len(ranked)} 支股票  |  by Lulu AI Stock Bot")
    return "\n".join(parts)


def save_output(message: str, session: str) -> None:
    now = datetime.now()
    day_dir = Path(OUTPUT_DIR) / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    fname = day_dir / f"cards_{session}.txt"
    fname.write_text(message, encoding="utf-8")
    logger.info(f"Saved to {fname}")


def main():
    parser = argparse.ArgumentParser(description="Lulu AI Stock Card Bot")
    parser.add_argument("--session", choices=["open", "mid", "close"], default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout, skip Telegram")
    args = parser.parse_args()

    session = args.session or detect_session()
    logger.info(f"Session: {SESSION_LABELS[session]}")

    symbols = load_watchlist()

    # Fetch and process all symbols
    stock_data = []
    for sym in symbols:
        result = process_symbol(sym)
        if result:
            stock_data.append(result)
        else:
            logger.warning(f"Skipping {sym} (no data)")

    if not stock_data:
        logger.error("No valid stock data retrieved. Aborting.")
        sys.exit(1)

    # Score and sort by urgency
    ranked = rank_stocks(stock_data)

    # Generate AI cards (sorted order)
    logger.info("Generating AI cards via Claude...")
    for stock in ranked:
        stock["card"] = generate_card(stock)
        logger.info(f"  ✓ {stock['symbol']}")

    # Assemble full message
    message = build_full_message(ranked, session)

    # Save to file
    save_output(message, session)

    # Send or print
    if args.dry_run:
        print("\n" + "=" * 60)
        print(message)
        print("=" * 60)
        print("\n[dry-run] Telegram not sent.")
    else:
        success = send_message(message)
        if success:
            logger.info("Telegram message sent successfully.")
        else:
            logger.error("Telegram send failed.")
            sys.exit(1)


if __name__ == "__main__":
    main()
