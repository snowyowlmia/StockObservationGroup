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


def _fib_bands(series: pd.Series, period: int):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std(ddof=0)
    return {
        "mid": mid,
        "u1": mid + 1.618 * std,
        "u2": mid + 2.618 * std,
        "u3": mid + 4.236 * std,
        "l1": mid - 1.618 * std,
        "l2": mid - 2.618 * std,
        "l3": mid - 4.236 * std,
    }


def _kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3):
    low_list = df["Low"].rolling(n).min()
    high_list = df["High"].rolling(n).max()
    rsv = (df["Close"] - low_list) / (high_list - low_list) * 100
    rsv = rsv.fillna(50)

    k = []
    d = []
    curr_k = 50.0
    curr_d = 50.0
    for val in rsv.values:
        curr_k = (2.0 / m1) * val + ((m1 - 1.0) / m1) * curr_k
        curr_d = (1.0 / m2) * curr_k + ((m2 - 1.0) / m2) * curr_d
        k.append(curr_k)
        d.append(curr_d)

    k_ser = pd.Series(k, index=df.index)
    d_ser = pd.Series(d, index=df.index)
    j_ser = 3.0 * k_ser - 2.0 * d_ser
    return k_ser, d_ser, j_ser


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

    # Fibonacci Bollinger Bands
    f_bands = _fib_bands(close, BB_PERIOD)
    df["FibBand_Mid"] = f_bands["mid"]
    df["FibBand_U1"] = f_bands["u1"]
    df["FibBand_U2"] = f_bands["u2"]
    df["FibBand_U3"] = f_bands["u3"]
    df["FibBand_L1"] = f_bands["l1"]
    df["FibBand_L2"] = f_bands["l2"]
    df["FibBand_L3"] = f_bands["l3"]

    # KDJ
    k_ser, d_ser, j_ser = _kdj(df)
    df["KDJ_K"] = k_ser
    df["KDJ_D"] = d_ser
    df["KDJ_J"] = j_ser

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
        "fib_band_mid": g("FibBand_Mid"),
        "fib_band_u1": g("FibBand_U1"),
        "fib_band_u2": g("FibBand_U2"),
        "fib_band_u3": g("FibBand_U3"),
        "fib_band_l1": g("FibBand_L1"),
        "fib_band_l2": g("FibBand_L2"),
        "fib_band_l3": g("FibBand_L3"),
        "kdj_k": g("KDJ_K"),
        "kdj_d": g("KDJ_D"),
        "kdj_j": g("KDJ_J"),
        "vol_avg20": int(row.get("Vol_Avg20", 0) or 0),
        "vol_ratio": round(float(row.get("Vol_Ratio", 1.0) or 1.0), 2),
    }
