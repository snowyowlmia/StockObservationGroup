"""Send messages to Telegram, splitting long messages automatically."""
import logging
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
MAX_LENGTH = 4000  # Telegram limit is 4096; stay safely below


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send text to the configured Telegram chat. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — printing to stdout instead")
        print(text)
        return True

    chunks = _split(text)
    ok = True
    for chunk in chunks:
        try:
            resp = requests.post(
                TELEGRAM_API,
                json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk, "parse_mode": parse_mode},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            ok = False
    return ok


def send_photo(photo_path: str, caption: str, parse_mode: str = "HTML") -> bool:
    """Send a photo with caption to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — printing to stdout instead")
        print(f"[Photo: {photo_path}]")
        print(caption)
        return True

    # Caption limit is 1024 characters for Telegram photos
    if len(caption) > 1020:
        caption = caption[:1017] + "..."

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as photo_file:
            resp = requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": parse_mode},
                files={"photo": photo_file},
                timeout=30,
            )
            resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram send photo failed: {e}")
        # Fallback to text message
        return send_message(f"[图表发送失败]\n\n{caption}", parse_mode)


def _split(text: str) -> list[str]:
    """Split text into chunks that fit Telegram's size limit."""
    if len(text) <= MAX_LENGTH:
        return [text]

    chunks = []
    while text:
        if len(text) <= MAX_LENGTH:
            chunks.append(text)
            break
        split_at = text.rfind("\n\n", 0, MAX_LENGTH)
        if split_at == -1:
            split_at = text.rfind("\n", 0, MAX_LENGTH)
        if split_at == -1:
            split_at = MAX_LENGTH
        chunks.append(text[:split_at].rstrip())
        text = text[split_at:].lstrip()
    return chunks
