#!/usr/bin/env python3
"""Quick single-stock test for MRVL — runs full pipeline and prints the card."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: Set ANTHROPIC_API_KEY in .env or environment before running this test.")
    sys.exit(1)

from src.data_fetcher import fetch_ohlcv, fetch_info
from src.indicators import compute_indicators, fibonacci_levels, pivot_points, extract_latest
from src.news_fetcher import get_news, format_news_for_prompt
from src.scorer import score_trend, score_entry, urgency_label
from src.card_generator import generate_card, build_daily_header

SYMBOL = "MRVL"

print(f"\n{'='*55}")
print(f"  LULU AI STOCK CARD BOT — TEST  ({SYMBOL})")
print(f"{'='*55}\n")

print("1/5  Fetching OHLCV data via yfinance...")
df = fetch_ohlcv(SYMBOL)
if df is None:
    print("ERROR: No data returned"); sys.exit(1)
print(f"     Got {len(df)} daily bars  ({df.index[0].date()} → {df.index[-1].date()})")

print("2/5  Computing indicators...")
df = compute_indicators(df)
ind = extract_latest(df)
fib = fibonacci_levels(df)
pivots = pivot_points(df)

print(f"     Price : ${ind['price']}  ({'+' if ind['chg_1d_pct']>=0 else ''}{ind['chg_1d_pct']}% today)")
print(f"     EMA20 : ${ind['ema20']}   EMA50: ${ind['ema50']}   EMA200: ${ind['ema200']}")
print(f"     RSI   : {ind['rsi']}")
print(f"     MACD  : {ind['macd']:.4f}  Signal: {ind['macd_signal']:.4f}  Hist: {ind['macd_hist']:.4f}")
print(f"     Volume: {ind['volume']:,}  ({ind['vol_ratio']:.1f}x avg)")
print(f"     Fib   : 0.382=${fib.get('0.382','?')}  0.5=${fib.get('0.5','?')}  0.618=${fib.get('0.618','?')}")
print(f"     Pivot : P=${pivots.get('P','?')}  S1=${pivots.get('S1','?')}  R1=${pivots.get('R1','?')}")

print("3/5  Fetching news...")
news_items = get_news(SYMBOL, max_items=5)
news_text = format_news_for_prompt(news_items)
print(f"     Found {len(news_items)} news items")
for n in news_items:
    print(f"     • {n['title'][:80]}")

print("4/5  Scoring...")
info = fetch_info(SYMBOL)
trend = score_trend(ind)
entry = score_entry(ind)
emoji, tag = urgency_label(trend, entry)
print(f"     Trend score : {trend}/10")
print(f"     Entry score : {entry}/10")
print(f"     Action tag  : {emoji} {tag}")

stock = {
    "symbol": SYMBOL,
    "indicators": ind,
    "fib": fib,
    "pivots": pivots,
    "news_text": news_text,
    "info": info,
    "trend_score": trend,
    "entry_score": entry,
    "urgency_emoji": emoji,
    "action_tag": tag,
}

print("5/5  Generating AI card via Claude claude-opus-4-8...")
card = generate_card(stock)

print(f"\n{'─'*55}")
print(f"{emoji} #{1}  {tag}")
print(f"{'─'*55}")
print(card)
print(f"{'═'*55}\n")
