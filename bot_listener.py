import time
import requests
import subprocess
import logging
import shlex
from config import TELEGRAM_BOT_TOKEN

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s")
logger = logging.getLogger("bot_listener")

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set in config.")
    exit(1)

API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def get_updates(offset=None):
    url = f"{API_URL}/getUpdates"
    params = {"timeout": 30, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset
    try:
        resp = requests.get(url, params=params, timeout=40)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error fetching updates: {e}")
        return None

def send_message(chat_id, text, reply_to_message_id=None):
    url = f"{API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Error sending message: {e}")

def main():
    logger.info("Bot listener started. Waiting for messages...")
    offset = None
    while True:
        updates = get_updates(offset)
        if updates and updates.get("ok"):
            for item in updates.get("result", []):
                update_id = item["update_id"]
                offset = update_id + 1
                
                message = item.get("message")
                if not message:
                    continue
                    
                text = message.get("text", "").strip()
                chat_id = message.get("chat"]["id"]
                msg_id = message.get("message_id")
                
                # Check for trigger commands
                symbol = None
                if text.startswith("/analyze "):
                    symbol = text.replace("/analyze ", "").strip().upper()
                elif "@" in text and " " in text:
                    # simplistic fallback for @bot VRT
                    parts = text.split()
                    for i, p in enumerate(parts):
                        if p.startswith("@") and i + 1 < len(parts):
                            symbol = parts[i+1].upper()
                            break
                            
                if symbol:
                    # Basic sanitization
                    symbol = "".join(c for c in symbol if c.isalnum() or c in "-.")
                    if symbol:
                        logger.info(f"Received request to analyze {symbol}")
                        send_message(chat_id, f"🤖 收到！正在为您调取 {symbol} 的走势截图与 Claude 4 深度分析，请稍候 1-2 分钟...", reply_to_message_id=msg_id)
                        
                        # Run the command asynchronously so we don't block the loop
                        # In a production app, we would use a task queue or ThreadPoolExecutor
                        cmd = f"python3 main.py --symbol {shlex.quote(symbol)} --screenshot --force-vision"
                        subprocess.Popen(cmd, shell=True)

        time.sleep(1)

if __name__ == "__main__":
    main()
