"""Fetch recent news. Tries Finnhub first, falls back to yfinance."""
import logging
import requests
from config import FINNHUB_API_KEY
from src.data_fetcher import fetch_yf_news

logger = logging.getLogger(__name__)

FINNHUB_URL = "https://finnhub.io/api/v1/company-news"


def _finnhub_news(symbol: str, max_items: int = 5) -> list[dict]:
    if not FINNHUB_API_KEY:
        return []
    try:
        from datetime import date, timedelta
        today = date.today().isoformat()
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        resp = requests.get(
            FINNHUB_URL,
            params={"symbol": symbol, "from": week_ago, "to": today, "token": FINNHUB_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json()[:max_items]
        return [{"title": i.get("headline", ""), "source": i.get("source", "")} for i in items if i.get("headline")]
    except Exception as e:
        logger.warning(f"Finnhub news failed for {symbol}: {e}")
        return []


def get_news(symbol: str, max_items: int = 5) -> list[dict]:
    """Return list of {'title': ..., 'source': ...} dicts."""
    news = _finnhub_news(symbol, max_items)
    if not news:
        news = fetch_yf_news(symbol, max_items)
    return news[:max_items]


def format_news_for_prompt(news: list[dict]) -> str:
    if not news:
        return "暂无近期新闻"
    lines = []
    for i, item in enumerate(news, 1):
        src = f" ({item['source']})" if item.get("source") else ""
        lines.append(f"{i}. {item['title']}{src}")
    return "\n".join(lines)
