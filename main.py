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
from src.scorer import rank_stocks, categorize_stocks
from src.card_generator import generate_card, generate_card_with_vision, build_daily_header, generate_cio_summary
from src.chart_renderer import capture_screenshot
from src.telegram_sender import send_message, send_photo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

SESSION_LABELS = {
    "open": "10:00 ET 开盘异动扫描",
    "mid": "13:00 ET 盘中趋势确认",
    "close": "15:45 ET 尾盘绝杀抢筹",
    "post": "20:00 ET 盘后复盘总结",
}

ET = pytz.timezone("America/New_York")


def detect_session() -> str:
    now_et = datetime.now(ET)
    hour = now_et.hour
    if hour < 11:
        return "open"
    elif hour < 14:
        return "mid"
    elif hour < 17:
        return "close"
    else:
        return "post"


def load_watchlist() -> list[dict]:
    path = Path(WATCHLIST_FILE)
    if not path.exists():
        logger.error(f"watchlist.txt not found at {WATCHLIST_FILE}")
        sys.exit(1)
    
    symbols = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            parts = line.split(",")
            sym = parts[0].strip().upper()
            tag = parts[1].strip() if len(parts) > 1 else ""
            symbols.append({"symbol": sym, "tag": tag})
            
    if not symbols:
        logger.error("watchlist.txt is empty")
        sys.exit(1)
    logger.info(f"Watchlist: {[s['symbol'] for s in symbols]}")
    return symbols


def process_symbol(item: dict) -> Optional[dict]:
    """Full pipeline for one symbol. Returns data dict or None on failure."""
    symbol = item["symbol"]
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
        "category_tag": item["tag"],
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


def build_summary_message(ranked: list[dict], session_label: str) -> str:
    header = build_daily_header(session_label)
    
    # 1. Categorize stocks
    groups = categorize_stocks(ranked)
    
    # 2. Generate CIO Briefing
    cio_text = generate_cio_summary(groups, session_label)
    
    lines = [header, "🏆 首席投资官 (CIO) 决策", cio_text, "\n⚡ 量化异动雷达"]
    
    # Helper to render a group
    def render_group(group_list, empty_msg):
        if not group_list:
            return f"  {empty_msg}"
        out = []
        for s in group_list:
            price = s['indicators'].get('price', '?')
            out.append(f"  ▸ {s['symbol']} (${price}) - 买点: {s.get('entry_score', 0)}")
        return "\n".join(out)
        
    lines.append("📈 动能爆发 (金叉+放量):")
    lines.append(render_group(groups["macd_golden"], "暂无符合条件的标的"))
    lines.append("\n🎯 黄金坑 (超卖/强支撑):")
    lines.append(render_group(groups["golden_dip"], "暂无符合条件的标的"))
    lines.append("\n⚠️ 财报警告 (3天内):")
    lines.append(render_group(groups["earnings_warning"], "暂无符合条件的标的"))

    lines.append("\n" + "─" * 20)
    lines.append("📋 全名单速览 (折叠/备查)")

    for i, stock in enumerate(ranked, 1):
        symbol = stock["symbol"]
        price = stock["indicators"].get("price", "?")
        chg = stock["indicators"].get("chg_1d_pct", 0)
        chg_str = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
        
        category = stock.get("category_tag", "")
        cat_str = f"[{category}]" if category else ""

        card_text = stock.get("card", "")
        one_liner = "暂无建议"
        for line in card_text.splitlines():
            if line.startswith("一句话："):
                one_liner = line.replace("一句话：", "").strip()
                break

        # 极简排版 (带 Emoji 和分数)
        emoji = stock.get("urgency_emoji", "")
        entry_score = stock.get("entry_score", 0)
        lines.append(f"{emoji} <code>{i:02d}. {cat_str:<6} {symbol:<5} | 买点:{entry_score:<3.1f} | {one_liner}</code>")

    return "\n".join(lines)


def save_output(message: str, session: str) -> None:
    now = datetime.now()
    day_dir = Path(OUTPUT_DIR) / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    fname = day_dir / f"cards_{session}.txt"
    fname.write_text(message, encoding="utf-8")
    logger.info(f"Saved to {fname}")


def main():
    parser = argparse.ArgumentParser(description="Lulu AI Stock Card Bot")
    parser.add_argument("--session", choices=["open", "mid", "close", "post"], default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout, skip Telegram")
    parser.add_argument("--screenshot", action="store_true", help="Generate TradingView screenshots and run AI vision check")
    parser.add_argument("--symbol", type=str, help="Analyze only a specific symbol (e.g. VRT)")
    parser.add_argument("--force-vision", action="store_true", help="Force high-end Vision model even if not Top 5 (used with --symbol)")
    args = parser.parse_args()

    session = args.session or detect_session()
    logger.info(f"Session: {SESSION_LABELS[session]}")

    if args.symbol:
        symbols = [{"symbol": args.symbol.upper(), "tag": "单股查阅"}]
    else:
        symbols = load_watchlist()

    # Fetch and process all symbols
    stock_data = []
    for item in symbols:
        result = process_symbol(item)
        if result:
            stock_data.append(result)
        else:
            logger.warning(f"Skipping {item['symbol']} (no data)")

    if not stock_data:
        logger.error("No valid stock data retrieved. Aborting.")
        sys.exit(1)

    # Score and sort by urgency
    ranked = rank_stocks(stock_data)

    # Generate AI cards (sorted order)
    logger.info("Generating AI cards via Claude...")
    for i, stock in enumerate(ranked):
        # Force vision/high-end model if explicitly requested via args
        is_top_5 = i < 5 or args.force_vision
        use_cheap = not is_top_5
        
        if args.screenshot and is_top_5:
            shot_path = os.path.join(OUTPUT_DIR, "screenshots", f"{stock['symbol']}_{session}.png")
            exchange = stock.get("info", {}).get("exchange", "")
            ok = capture_screenshot(stock["symbol"], exchange, shot_path)
            if ok:
                stock["card"] = generate_card_with_vision(stock, shot_path, session=session)
                stock["shot_path"] = shot_path
            else:
                logger.warning(f"Screenshot failed for {stock['symbol']}, falling back to text-only card.")
                stock["card"] = generate_card(stock, use_cheap_model=use_cheap, session=session)
        else:
            stock["card"] = generate_card(stock, use_cheap_model=use_cheap, session=session)
        logger.info(f"  ✓ {stock['symbol']} (Top 5: {is_top_5})")

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
        if args.screenshot:
            # Send session header with summary overview
            summary_msg = build_summary_message(ranked, SESSION_LABELS[session])
            send_message(summary_msg)

            # Send each stock card as a photo with caption
            success = True
            for i, stock in enumerate(ranked, 1):
                if i > 5:
                    break  # Limit detailed cards to Top 5
                    
                emoji = stock.get("urgency_emoji", "")
                tag = stock.get("action_tag", "")
                symbol = stock["symbol"]
                price = stock["indicators"].get("price", "?")
                chg = stock["indicators"].get("chg_1d_pct", 0)
                chg_str = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"

                card_title = f"{emoji} #{i}  {tag}  ▸  {symbol} ${price} ({chg_str})\n"
                caption = card_title + stock["card"]

                shot_path = stock.get("shot_path")
                if shot_path and os.path.exists(shot_path):
                    ok = send_photo(shot_path, caption)
                else:
                    ok = send_message(caption)
                if not ok:
                    success = False

            # Send footer
            footer = f"\n{'═' * 42}\n共分析 {len(ranked)} 支股票  |  by Lulu AI Stock Bot"
            send_message(footer)

            if success:
                logger.info("Telegram photo messages sent successfully.")
            else:
                logger.error("Some Telegram photo messages failed to send.")
                sys.exit(1)
        else:
            success = send_message(message)
            if success:
                logger.info("Telegram message sent successfully.")
            else:
                logger.error("Telegram send failed.")
                sys.exit(1)


if __name__ == "__main__":
    main()
