"""
Pre-sort urgency scorer. Determines which stocks need the most attention TODAY.
This is a heuristic ranking — Claude does the full qualitative analysis.

Urgency = how actionable is this setup RIGHT NOW?
  High:  near key support after pullback / MACD crossover / RSI extreme
  Med:   consolidating / approaching level / healthy trend
  Low:   extended above all EMAs / no catalyst / downtrend
"""


def score_trend(ind: dict) -> float:
    """0-10: Long-term technical health. Higher = stronger bull trend."""
    price = ind.get("price", 0)
    score = 0.0
    weights = [(200, 3), (100, 2), (50, 2), (20, 1.5), (10, 1.5)]
    total_w = sum(w for _, w in weights)
    for period, w in weights:
        ema = ind.get(f"ema{period}")
        if ema and price > ema:
            score += w
    return round(score / total_w * 10, 1)


def score_entry(ind: dict) -> float:
    """
    0-10: Quality of current entry setup. Higher = better buy point right now.
    Best: oversold pullback to key EMA support + MACD turning up.
    Worst: overbought breakout, overextended, or broken downtrend.
    """
    score = 5.0

    rsi = ind.get("rsi") or 50
    macd_hist = ind.get("macd_hist") or 0
    prev_macd_hist = ind.get("prev_macd_hist") or 0
    price = ind.get("price", 0)
    ema10 = ind.get("ema10") or price
    ema20 = ind.get("ema20") or price
    ema50 = ind.get("ema50") or price
    vol_ratio = ind.get("vol_ratio", 1.0)

    # RSI scoring
    if rsi < 25:
        score += 2.5
    elif rsi < 35:
        score += 1.5
    elif rsi < 45:
        score += 0.8
    elif rsi > 80:
        score -= 2.5
    elif rsi > 70:
        score -= 1.5
    elif rsi > 60:
        score -= 0.5

    # MACD histogram turning point
    if macd_hist > 0 and prev_macd_hist <= 0:
        score += 2.0   # fresh bullish crossover
    elif macd_hist < 0 and prev_macd_hist >= 0:
        score += 1.0   # fresh bearish crossover (note: still interesting for shorts/warnings)
    elif macd_hist > 0 and macd_hist > prev_macd_hist:
        score += 0.5   # building bullish momentum
    elif macd_hist < 0 and macd_hist < prev_macd_hist:
        score -= 0.5   # building bearish momentum

    # Price testing EMA support (within 2%)
    for ema_val, bonus in [(ema10, 0.5), (ema20, 1.0), (ema50, 1.5)]:
        if ema_val and abs(price - ema_val) / ema_val < 0.02:
            score += bonus
            break

    # Volume confirmation on up moves
    if vol_ratio > 1.5 and ind.get("chg_1d_pct", 0) > 0:
        score += 0.5
    elif vol_ratio > 2.0:
        score += 0.5  # high volume regardless = attention

    return round(max(0.0, min(10.0, score)), 1)


def urgency_label(trend: float, entry: float) -> tuple[str, str]:
    """Return (emoji_label, action_tag) based on trend + entry scores."""
    overall = trend * 0.4 + entry * 0.6

    if entry >= 6.5 and trend >= 6:
        return "🔴", "今日关注买点"
    elif entry >= 5.5 and trend >= 5:
        return "🟡", "高度关注"
    elif trend >= 7 and entry >= 4:
        return "🟢", "等待回调"
    elif trend < 4 or entry < 2:
        return "⚪", "暂时回避"
    else:
        return "🟢", "等待观察"


def rank_stocks(stock_data: list[dict]) -> list[dict]:
    """
    Score and sort all stocks by urgency (most actionable first).
    Each item in stock_data must have keys: symbol, indicators (flat dict).
    Returns sorted list with added keys: trend_score, entry_score, urgency_emoji, action_tag.
    """
    results = []
    for item in stock_data:
        ind = item.get("indicators", {})
        trend = score_trend(ind)
        entry = score_entry(ind)
        emoji, tag = urgency_label(trend, entry)
        results.append({
            **item,
            "trend_score": trend,
            "entry_score": entry,
            "urgency_emoji": emoji,
            "action_tag": tag,
            "_sort_key": entry * 0.6 + trend * 0.4,
        })

    results.sort(key=lambda x: x["_sort_key"], reverse=True)
    return results
