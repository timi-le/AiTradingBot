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
        logger.info("Telegram Command Center Active...")
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        
        while self.running:
            try:
                # Long polling for responsiveness
                resp = self.session.get(url, params={"offset": self.offset, "timeout": 30}, timeout=35)
                data = resp.json()
                
                if data.get("ok"):
                    for u in data["result"]:
                        self.offset = u["update_id"] + 1
                        self._handle_message(u.get("message", {}))
                
                time.sleep(0.5)

            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
                continue
            except Exception as e:
                logger.error(f"Listener Error: {e}")
                time.sleep(5)

    def _handle_message(self, message):
        text = message.get("text", "").lower().strip()
        chat_id = str(message.get("chat", {}).get("id"))
        
        # Security Check
        if chat_id != settings.TELEGRAM_CHAT_ID:
            return

        # --- COMMANDS ---

        if text == "/help" or text == "/start":
            msg = (
                "🕹️ **QUANT COMMANDER V6**\n\n"
                "🔍 **Insight**\n"
                "/status - Session Bias & Market Hours\n"
                "/alpha - Live Probabilistic Score\n"
                "/positions - Open Trades & PnL\n"
                "/balance - Equity Health\n\n"
                "⚙️ **Control**\n"
                "/pause - Suspend Trading\n"
                "/resume - Resume Trading\n"
                "/reset - 🔄 Reset Session Bias\n"
                "/test - 🧪 Connectivity Test\n"
                "/logs - View Recent Logs"
            )
            self.bot.notifier.send(msg)

        elif text == "/status":
            # Real-time Session Context
            ctx = self.bot.session.get_context()
            hour = datetime.datetime.now(datetime.timezone.utc).hour
            mkt_status = "🟢 OPEN" if 7 <= hour < 22 else "💤 CLOSED"
            
            msg = (
                f"✅ **System Status**\n"
                f"Market: {mkt_status}\n"
                f"Bot State: {'▶️ RUNNING' if not self.bot.paused else '⏸️ PAUSED'}\n"
                f"-------------------\n"
                f"🧠 **Session Manager**\n"
                f"Bias: {ctx.get('locked_bias', 'NEUTRAL')}\n"
                f"Mode: {ctx.get('session_status', 'WAITING')}"
            )
            self.bot.notifier.send(msg)

        elif text == "/alpha":
            # On-Demand Alpha Calculation (Runs the Math Engine instantly)
            self.bot.notifier.send("🧮 Calculating Live Alpha...")
            
            for symbol in settings.symbol_list:
                data = self.bot.broker.get_multi_timeframe_data(symbol)
                if not data:
                    self.bot.notifier.send(f"⚠️ {symbol}: No Data")
                    continue
                
                # Run the Alpha Model
                state = self.bot.alpha.get_market_state(data)
                
                # Format the output
                score = state['final_alpha_score']
                bd = state['m5_metrics']['breakdown']
                
                msg = (
                    f"📊 **{symbol} Alpha Scan**\n"
                    f"Score: **{score}/1.0** ({state['status']})\n"
                    f"-------------------\n"
                    f"🏗️ Structure: {bd['structure']} ({bd['structure_type']})\n"
                    f"↩️ Reversion: {bd['reversion']}\n"
                    f"🌊 Volatility: {bd['volatility']}\n"
                    f"🚀 Momentum: {bd['momentum']}"
                )
                self.bot.notifier.send(msg)

        elif text == "/reset":
            # Force reset the session manager
            self.bot.session.strategic_bias = "NEUTRAL"
            self.bot.session.key_levels = {"support": 0.0, "resistance": 0.0}
            self.bot.notifier.send("🔄 **Session Bias RESET**\nBot will re-evaluate macro trend on next cycle.")

        elif text == "/positions":
            trades = self.bot.broker.get_open_positions()
            if not trades:
                self.bot.notifier.send("🚫 No Open Trades")
            else:
                msg = "💼 **Portfolio**\n"
                total_pnl = 0.0
                for t in trades:
                    icon = "🟢" if t.profit >= 0 else "🔴"
                    msg += f"{icon} {t.symbol} {t.volume}lot | ${t.profit:.2f}\n"
                    total_pnl += t.profit
                msg += f"-------------------\nTotal PnL: ${total_pnl:.2f}"
                self.bot.notifier.send(msg)

        elif text == "/balance":
            info = self.bot.broker.get_account_info()
            self.bot.notifier.send(f"💰 **Account**\nEquity: ${info.get('equity', 0):.2f}\nBalance: ${info.get('balance', 0):.2f}")

        elif text == "/logs":
            logs = self.bot.get_recent_logs(n=8)
            self.bot.notifier.send(f"📜 **System Logs**\n```\n{logs}\n```")

        elif text == "/test":
            self.bot.notifier.send("🧪 Testing Broker Connection...")
            sym = settings.symbol_list[0]
            if self.bot.broker.verify_execution_capability(sym):
                self.bot.notifier.send("✅ Broker OK\n✅ Trading Permissions OK")
            else:
                self.bot.notifier.send("❌ Broker Connection FAILED")

        elif text == "/pause":
            self.bot.paused = True
            self.bot.notifier.send("⏸️ **System PAUSED**")

        elif text == "/resume":
            self.bot.paused = False
            self.bot.notifier.send("▶️ **System RESUMED**")