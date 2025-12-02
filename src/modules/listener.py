import threading
import time
import requests
import logging
import datetime
from src.config.settings import settings

logger = logging.getLogger(__name__)

class TelegramListener:
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
        logger.info("Telegram Control Center Active...")
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
            except:
                time.sleep(5)

    def _handle_message(self, message):
        text = message.get("text", "").lower().strip()
        chat_id = str(message.get("chat", {}).get("id"))
        if chat_id != settings.TELEGRAM_CHAT_ID: return

        if text == "/start" or text == "/help":
            msg = (
                "🕹️ **QUANTBOT V5 COMMANDER**\n\n"
                "📊 **Info**\n"
                "/status - Health & Market Hours\n"
                "/balance - Equity & Margin\n"
                "/positions - Open Trades\n"
                "/regime - Current AI Market View\n\n"
                "⚙️ **Control**\n"
                "/test - 🧪 Test Broker Execution\n"
                "/pause - Suspend Entries\n"
                "/resume - Resume Entries\n"
                "/analyze - Force Scan\n"
                "/logs - View System Logs"
            )
            self.bot.notifier.send(msg)

        elif text == "/test":
            self.bot.notifier.send("🧪 **Running Execution Test...**\nAttempting to place and delete a pending order.")
            # We use the first symbol in the list for the test
            test_symbol = settings.symbol_list[0]
            success = self.bot.broker.verify_execution_capability(test_symbol)
            if success:
                self.bot.notifier.send("✅ **TEST PASSED**\nBroker accepted trade.\nBot has permissions.")
            else:
                self.bot.notifier.send("❌ **TEST FAILED**\nCheck logs. Is 'Algo Trading' Green?")

        elif text == "/status":
            hour = datetime.datetime.now(datetime.timezone.utc).hour
            session_status = "🟢 OPEN (London/NY)" if 8 <= hour < 22 else "💤 CLOSED (Asian)"
            state = "▶️ RUNNING" if not self.bot.paused else "⏸️ PAUSED"
            self.bot.notifier.send(f"✅ **System Status**\nState: {state}\nMarket Window: {session_status}\nMonitoring: {settings.SYMBOLS}")

        elif text == "/balance":
            i = self.bot.broker.get_account_info()
            self.bot.notifier.send(f"💰 **Capital**\nEquity: ${i.get('equity',0):.2f}\nBalance: ${i.get('balance',0):.2f}")

        elif text == "/regime":
            if not self.bot.memory:
                self.bot.notifier.send("🧠 No memory yet. Wait for next cycle.")
            else:
                msg = " **AI Market Memory**\n"
                for sym, data in self.bot.memory.items():
                    msg += f"\n**{sym}**\nPlan: {data.get('plan')}\n"
                self.bot.notifier.send(msg)

        elif text == "/logs":
            self.bot.notifier.send(f"📜 **Logs**\n```\n{self.bot.get_recent_logs()}\n```")

        elif text == "/pause":
            self.bot.paused = True
            self.bot.notifier.send("⏸️ Bot Paused.")

        elif text == "/resume":
            self.bot.paused = False
            self.bot.notifier.send("▶️ Bot Resumed.")
            
        elif text == "/analyze":
            self.bot.notifier.send("🔍 Scanning...")
            threading.Thread(target=self.bot.run_cycle).start()