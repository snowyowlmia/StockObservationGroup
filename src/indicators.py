"""Calculate all technical indicators and key price levels."""
import logging
import numpy as np
import pandas as pd
import pandas_ta as ta
from config import EMA_PERIODS, RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL, BB_PERIOD, VOLUME_AVG_PERIOD, FIB_LOOKBACK

logger = logging.getLogger(__name__)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Append all technical indicator columns to df in-place, return df."""
    for p in EMA_PERIODS:
        df.ta.ema(length=p, append=True)

    df.ta.rsi(length=RSI_PERIOD, append=True)
    df.ta.macd(fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL, append=True)
    df.ta.bbands(length=BB_PERIOD, std=2, append=True)

    df["Vol_Avg20"] = df["Volume"].rolling(VOLUME_AVG_PERIOD).mean()
    df["Vol_Ratio"] = df["Volume"] / df["Vol_Avg20"]

    return df


def fibonacci_levels(df: pd.DataFrame) -> dict:
    """
    Compute Fibonacci retracement levels from the most recent swing high/low
    within FIB_LOOKBACK trading days.
    """
    window = df.tail(FIB_LOOKBACK)
    swing_high = window["High"].max()
    swing_low = window["Low"].min()
    diff = swing_high - swing_low
    if diff == 0:
        return {}

    ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    levels = {str(r): round(swing_high - r * diff, 2) for r in ratios}
    levels["swing_high"] = round(swing_high, 2)
    levels["swing_low"] = round(swing_low, 2)
    return levels


def pivot_points(df: pd.DataFrame) -> dict:
    """Standard floor pivot points from the previous session."""
    if len(df) < 2:
        return {}
    prev = df.iloc[-2]
    H, L, C = prev["High"], prev["Low"], prev["Close"]
    P = (H + L + C) / 3
    return {
        "P": round(P, 2),
        "R1": round(2 * P - L, 2),
        "R2": round(P + (H - L), 2),
        "R3": round(H + 2 * (P - L), 2),
        "S1": round(2 * P - H, 2),
        "S2": round(P - (H - L), 2),
        "S3": round(L - 2 * (H - P), 2),
    }


def extract_latest(df: pd.DataFrame) -> dict:
    """Extract a flat dict of the latest row's indicator values."""
    row = df.iloc[-1]
    prev_row = df.iloc[-2] if len(df) >= 2 else row

    emas = {}
    for p in EMA_PERIODS:
        col = f"EMA_{p}"
        emas[f"ema{p}"] = round(row.get(col, float("nan")), 2)

    rsi_col = f"RSI_{RSI_PERIOD}"
    macd_col = f"MACD_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"
    macdh_col = f"MACDh_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"
    macds_col = f"MACDs_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"

    bbl_col = f"BBL_{BB_PERIOD}_2.0"
    bbm_col = f"BBM_{BB_PERIOD}_2.0"
    bbu_col = f"BBU_{BB_PERIOD}_2.0"

    def g(col):
        v = row.get(col, float("nan"))
        return round(v, 4) if not (isinstance(v, float) and np.isnan(v)) else None

    def gp(col):
        v = prev_row.get(col, float("nan"))
        return round(v, 4) if not (isinstance(v, float) and np.isnan(v)) else None

    # 5-day price change
    price_5d_ago = df["Close"].iloc[-6] if len(df) >= 6 else df["Close"].iloc[0]
    chg_5d = (row["Close"] - price_5d_ago) / price_5d_ago * 100

    # 1-day change
    chg_1d = (row["Close"] - prev_row["Close"]) / prev_row["Close"] * 100

    return {
        "price": round(row["Close"], 2),
        "open": round(row["Open"], 2),
        "high": round(row["High"], 2),
        "low": round(row["Low"], 2),
        "volume": int(row["Volume"]),
        "chg_1d_pct": round(chg_1d, 2),
        "chg_5d_pct": round(chg_5d, 2),
        **emas,
        "rsi": g(rsi_col),
        "macd": g(macd_col),
        "macd_hist": g(macdh_col),
        "macd_signal": g(macds_col),
        "prev_macd_hist": gp(macdh_col),
        "bb_lower": g(bbl_col),
        "bb_mid": g(bbm_col),
        "bb_upper": g(bbu_col),
        "vol_avg20": int(row.get("Vol_Avg20", 0) or 0),
        "vol_ratio": round(row.get("Vol_Ratio", 1.0) or 1.0, 2),
    }
