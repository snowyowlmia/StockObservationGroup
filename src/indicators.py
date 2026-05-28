"""Calculate all technical indicators using pure pandas/numpy — no TA library dependency."""
import numpy as np
import pandas as pd
import logging
from config import EMA_PERIODS, RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL, BB_PERIOD, VOLUME_AVG_PERIOD, FIB_LOOKBACK

logger = logging.getLogger(__name__)


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(series: pd.Series, fast: int, slow: int, signal: int):
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _bbands(series: pd.Series, period: int, std_dev: float = 2.0):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std(ddof=0)
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return lower, mid, upper


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Append all technical indicator columns to df, return df."""
    close = df["Close"]

    for p in EMA_PERIODS:
        df[f"EMA_{p}"] = _ema(close, p)

    df["RSI_14"] = _rsi(close, RSI_PERIOD)

    macd, macd_sig, macd_hist = _macd(close, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    df["MACD"] = macd
    df["MACD_Signal"] = macd_sig
    df["MACD_Hist"] = macd_hist

    df["BB_Lower"], df["BB_Mid"], df["BB_Upper"] = _bbands(close, BB_PERIOD)

    df["Vol_Avg20"] = df["Volume"].rolling(VOLUME_AVG_PERIOD).mean()
    df["Vol_Ratio"] = df["Volume"] / df["Vol_Avg20"]

    return df


def fibonacci_levels(df: pd.DataFrame) -> dict:
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
    row = df.iloc[-1]
    prev_row = df.iloc[-2] if len(df) >= 2 else row

    def g(col):
        v = row.get(col, float("nan"))
        if isinstance(v, float) and np.isnan(v):
            return None
        return round(float(v), 4)

    def gp(col):
        v = prev_row.get(col, float("nan"))
        if isinstance(v, float) and np.isnan(v):
            return None
        return round(float(v), 4)

    price_5d_ago = df["Close"].iloc[-6] if len(df) >= 6 else df["Close"].iloc[0]
    chg_5d = (row["Close"] - price_5d_ago) / price_5d_ago * 100
    chg_1d = (row["Close"] - prev_row["Close"]) / prev_row["Close"] * 100

    emas = {f"ema{p}": round(float(row.get(f"EMA_{p}", float("nan"))), 2)
            if not np.isnan(float(row.get(f"EMA_{p}", float("nan")))) else None
            for p in EMA_PERIODS}

    return {
        "price": round(float(row["Close"]), 2),
        "open": round(float(row["Open"]), 2),
        "high": round(float(row["High"]), 2),
        "low": round(float(row["Low"]), 2),
        "volume": int(row["Volume"]),
        "chg_1d_pct": round(chg_1d, 2),
        "chg_5d_pct": round(chg_5d, 2),
        **emas,
        "rsi": g("RSI_14"),
        "macd": g("MACD"),
        "macd_hist": g("MACD_Hist"),
        "macd_signal": g("MACD_Signal"),
        "prev_macd_hist": gp("MACD_Hist"),
        "bb_lower": g("BB_Lower"),
        "bb_mid": g("BB_Mid"),
        "bb_upper": g("BB_Upper"),
        "vol_avg20": int(row.get("Vol_Avg20", 0) or 0),
        "vol_ratio": round(float(row.get("Vol_Ratio", 1.0) or 1.0), 2),
    }
