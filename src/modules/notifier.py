import requests
import logging
import time
from src.config.settings import settings

logger = logging.getLogger(__name__)

class TelegramNotifier:
    HEADER = "Xgate Notification"  # Professional header

    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN.get_secret_value()
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)
        self.session = requests.Session()

    def send(self, message: str, retries=3):
        if not self.enabled:
            return
        
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": f"*{self.HEADER}*\n\n{message}",
            "parse_mode": "Markdown"
        }
        
        for attempt in range(retries):
            try:
                resp = self.session.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    return
                logger.warning(f"Telegram Error {resp.status_code}: {resp.text}")
            except requests.exceptions.RequestException as e:
                logger.warning(f"Telegram Timeout ({attempt+1}/{retries}): {e}")
                time.sleep(2)
        
        logger.error("Failed to send Telegram message after retries.")
