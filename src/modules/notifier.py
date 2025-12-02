import requests
import logging
import time
from src.config.settings import settings

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN.get_secret_value()
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)
        self.session = requests.Session() # Use a persistent session

    def send(self, message: str, retries=3):
        if not self.enabled:
            return
        
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": f"🤖 *QuantBot Alert*\n\n{message}",
            "parse_mode": "Markdown"
        }
        
        for attempt in range(retries):
            try:
                response = self.session.post(url, json=payload, timeout=10)
                if response.status_code == 200:
                    return
                else:
                    logger.warning(f"Telegram Error {response.status_code}: {response.text}")
            except requests.exceptions.RequestException as e:
                logger.warning(f"Telegram Timeout (Attempt {attempt+1}/{retries}): {e}")
                time.sleep(2) # Wait before retry
        
        logger.error("Failed to send Telegram message after retries.")