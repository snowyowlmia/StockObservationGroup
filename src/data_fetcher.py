"""Fetch OHLCV data and basic info via yfinance."""
import logging
from typing import Optional
import pandas as pd
import yfinance as yf
from config import DATA_PERIOD, DATA_INTERVAL

logger = logging.getLogger(__name__)


def fetch_ohlcv(symbol: str) -> Optional[pd.DataFrame]:
    """Return daily OHLCV DataFrame for symbol, or None on failure."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=DATA_PERIOD, interval=DATA_INTERVAL, auto_adjust=True)
        if df.empty or len(df) < 30:
            logger.warning(f"{symbol}: insufficient data ({len(df)} rows)")
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        return df
    except Exception as e:
        logger.error(f"{symbol}: fetch failed — {e}")
        return None


def fetch_info(symbol: str) -> dict:
    """Return a dict with sector/industry/company name from yfinance."""
    try:
        info = yf.Ticker(symbol).info
        return {
            "name": info.get("shortName", symbol),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "market_cap": info.get("marketCap", 0),
            "exchange": info.get("exchange", ""),
        }
    except Exception:
        return {"name": symbol, "sector": "", "industry": "", "market_cap": 0, "exchange": ""}


def fetch_yf_news(symbol: str, max_items: int = 5) -> list[dict]:
    """Return recent news headlines from yfinance (free, no key needed)."""
    try:
        news = yf.Ticker(symbol).news or []
        results = []
        for item in news[:max_items]:
            content = item.get("content", {})
            title = content.get("title") or item.get("title", "")
            if title:
                results.append({"title": title, "source": content.get("provider", {}).get("displayName", "")})
        return results
    except Exception:
        return []
