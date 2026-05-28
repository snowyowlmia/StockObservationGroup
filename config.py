import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.txt")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# yfinance fetch settings
DATA_PERIOD = "6mo"
DATA_INTERVAL = "1d"

# Indicator parameters
EMA_PERIODS = [10, 20, 50, 100, 200]
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BB_PERIOD = 20
VOLUME_AVG_PERIOD = 20
FIB_LOOKBACK = 60  # days for swing high/low

# Scoring weights
W_TREND = 0.4
W_ENTRY = 0.6
