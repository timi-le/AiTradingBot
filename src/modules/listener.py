import threading
import time
import requests
import logging
import datetime
from src.config.settings import settings

logger = logging.getLogger(__name__)

class TelegramListener:
    START_HEADER = "Xgate Control Center 🚀"  # Only emoji allowed here

    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.token = settings.TELEGRAM_BOT_TOKEN.get_secret_value()
        self.session = requests.Session()
        self.offset = 0
        self.running = False

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._poll_updates)
        thread.daemon = True
        thread.start()

    def _poll_updates(self):
        logger.info("Xgate Listener Activated.")
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        
        while self.running:
            try:
                resp = self.session.get(url, params={"offset": self.offset, "timeout": 30}, timeout=35)
                data = resp.json()
                
                if data.get("ok"):
                    for u in data["result"]:
                        self.offset = u["update_id"] + 1
                        self._handle_message(u.get("message", {}))
                        
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Telegram Listener Error: {e}")
                time.sleep(5)

    def _send(self, text):
        self.bot.notifier.send(text)

    def _handle_message(self, message):
        text = message.get("text", "").lower().strip()
        chat_id = str(message.get("chat", {}).get("id"))
        if chat_id != settings.TELEGRAM_CHAT_ID:
            return

        # -------------------------
        # COMMAND ROUTER
        # -------------------------

        if text in ("/start", "/help"):
            self._send(
                f"*{self.START_HEADER}*\n\n"
                "Available Commands:\n"
                "\n*System Information*"
                "\n/status - Bot health status"
                "\n/balance - Account balance and equity"
                "\n/positions - Open positions"
                "\n/regime - Current market regime analysis"
                "\n"
                "\n*Controls*"
                "\n/test - Broker execution test"
                "\n/pause - Pause trade entries"
                "\n/resume - Resume trade entries"
                "\n/analyze - Force immediate scan"
                "\n/logs - Retrieve recent log entries"
            )

        elif text == "/test":
            self._send("Running execution validation...")
            symbol = settings.symbol_list[0]
            ok = self.bot.broker.verify_execution_capability(symbol)
            self._send("Execution Test Passed." if ok else "Execution Test Failed. Check MT5 permissions.")

        elif text == "/status":
            now = datetime.datetime.now(datetime.timezone.utc).hour
            active = "Market Active" if 8 <= now < 22 else "Market Inactive"

            state = "Running" if not self.bot.paused else "Paused"

            self._send(
                f"*System Status*\n"
                f"State: {state}\n"
                f"Market Window: {active}\n"
                f"Symbols Monitored: {settings.SYMBOLS}"
            )

        elif text == "/balance":
            i = self.bot.broker.get_account_info()
            self._send(
                f"*Account Information*\n"
                f"Equity: {i.get('equity',0):.2f}\n"
                f"Balance: {i.get('balance',0):.2f}"
            )

        elif text == "/regime":
            mem = self.bot.memory or {}
            if not mem:
                self._send("No market memory available yet.")
                return
            
            msg = "*Market Regime Analysis*\n"
            for sym, d in mem.items():
                msg += f"\n{sym}\nPlan: {d.get('plan')}\n"
            self._send(msg)

        elif text == "/logs":
            logs = self.bot.get_recent_logs()
            self._send(f"*System Logs*\n```\n{logs}\n```")

        elif text == "/pause":
            self.bot.paused = True
            self._send("System paused.")

        elif text == "/resume":
            self.bot.paused = False
            self._send("System resumed.")

        elif text == "/analyze":
            self._send("Executing immediate scan request.")
            threading.Thread(target=self.bot.run_cycle).start()
