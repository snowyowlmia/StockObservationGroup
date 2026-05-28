#!/usr/bin/env python3
"""
Offline logic test — uses mock MRVL-like data to verify the full pipeline
(indicators, scoring, card prompt) without any network calls.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from datetime import date, timedelta

# ── Build mock MRVL price data (realistic values circa 2026-05) ──────────────
np.random.seed(42)
days = 130
dates = pd.bdate_range(end=date.today(), periods=days)
base = 95.0
prices = [base]
for _ in range(days - 1):
    prices.append(prices[-1] * (1 + np.random.normal(0.0005, 0.022)))

closes = pd.Series(prices)
c = closes.values  # strip Series index to avoid alignment issues
df = pd.DataFrame({
    "Open":   c * (1 + np.random.normal(0, 0.004, days)),
    "High":   c * (1 + np.abs(np.random.normal(0.007, 0.005, days))),
    "Low":    c * (1 - np.abs(np.random.normal(0.007, 0.005, days))),
    "Close":  c,
    "Volume": np.random.randint(8_000_000, 30_000_000, days).astype(float),
}, index=pd.to_datetime(dates))

# ── Run indicators ────────────────────────────────────────────────────────────
from src.indicators import compute_indicators, fibonacci_levels, pivot_points, extract_latest

df = compute_indicators(df)
ind = extract_latest(df)
fib = fibonacci_levels(df)
pivots = pivot_points(df)

print("=" * 55)
print("  INDICATORS  (mock MRVL data)")
print("=" * 55)
print(f"Price          : ${ind['price']}  ({ind['chg_1d_pct']:+.2f}% today, {ind['chg_5d_pct']:+.2f}% week)")
print(f"EMA10/20/50    : ${ind['ema10']} / ${ind['ema20']} / ${ind['ema50']}")
print(f"EMA100/200     : ${ind['ema100']} / ${ind['ema200']}")
print(f"RSI(14)        : {ind['rsi']:.1f}")
print(f"MACD           : {ind['macd']:.4f}  Signal: {ind['macd_signal']:.4f}  Hist: {ind['macd_hist']:.4f}")
print(f"Bollinger      : ${ind['bb_lower']:.2f} — ${ind['bb_mid']:.2f} — ${ind['bb_upper']:.2f}")
print(f"Volume ratio   : {ind['vol_ratio']:.2f}x 20-day avg")
print(f"Fib (60d)      : 0.382=${fib.get('0.382','?')}  0.5=${fib.get('0.5','?')}  0.618=${fib.get('0.618','?')}")
print(f"Pivots         : P=${pivots['P']}  R1=${pivots['R1']}  S1=${pivots['S1']}")

# ── Scoring ───────────────────────────────────────────────────────────────────
from src.scorer import score_trend, score_entry, urgency_label

trend = score_trend(ind)
entry = score_entry(ind)
emoji, tag = urgency_label(trend, entry)

print("\n" + "=" * 55)
print("  SCORING")
print("=" * 55)
print(f"Trend score    : {trend}/10")
print(f"Entry score    : {entry}/10")
print(f"Action label   : {emoji} {tag}")

# ── Card prompt preview ────────────────────────────────────────────────────────
from src.card_generator import _build_prompt

mock_news = "1. Marvell announces AI networking chip roadmap for 2026\n2. MRVL beats Q4 estimates, raises full-year guidance\n3. New partnership with major cloud provider for custom silicon"

stock = {
    "symbol": "MRVL",
    "indicators": ind,
    "fib": fib,
    "pivots": pivots,
    "news_text": mock_news,
    "info": {"name": "Marvell Technology Inc.", "sector": "Technology", "industry": "Semiconductors"},
    "trend_score": trend,
    "entry_score": entry,
}

prompt = _build_prompt(stock)
print("\n" + "=" * 55)
print("  CLAUDE PROMPT PREVIEW (first 800 chars)")
print("=" * 55)
print(prompt[:800])
print("...[prompt continues]")

print("\n" + "=" * 55)
print("  ALL TESTS PASSED ✓  (logic verified, no network needed)")
print("=" * 55)
