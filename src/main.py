import time
import signal
import sys
import logging
import threading
import collections
from datetime import datetime, timezone
from src.config.settings import settings
from src.modules.broker import MT5Broker
from src.modules.brain import GeminiBrain
from src.modules.market_data import AlphaModel
from src.modules.session_manager import SessionManager
from src.modules.notifier import TelegramNotifier
from src.modules.listener import TelegramListener
import MetaTrader5 as mt5

# --- LOGGING SETUP WITH MEMORY ---
log_buffer = collections.deque(maxlen=50)

class ListHandler(logging.Handler):
    """Custom handler to capture logs for Telegram"""
    def __init__(self, buffer):
        super().__init__()
        self.buffer = buffer

    def emit(self, record):
        msg = self.format(record)
        self.buffer.append(msg)

handler = ListHandler(log_buffer)
handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        handler
    ]
)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        self.running = True
        self.paused = False
        
        self.broker = MT5Broker()
        self.brain = GeminiBrain()
        self.alpha = AlphaModel()
        self.session = SessionManager()
        self.notifier = TelegramNotifier()
        self.listener = TelegramListener(self) 
        
        self.memory = {}
        self.start_time = time.time()
        self.cycles_run = 0
        self.error_count = 0

    def get_recent_logs(self, n=15):
        if not log_buffer: return "No logs yet."
        return "\n".join(list(log_buffer)[-n:])

    def get_performance_metrics(self):
        return {
            "uptime": int(time.time() - self.start_time),
            "cycles": self.cycles_run,
            "errors": self.error_count,
            "trades_managed": len(self.broker.get_open_positions()) if self.broker.connected else 0
        }

    def is_trading_hours(self):
        current_hour = datetime.now(timezone.utc).hour
        # 07:00 UTC (08:00 WAT) to 22:00 UTC
        if 7 <= current_hour < 22:
            return True
        return False

    def manage_positions(self):
        open_trades = self.broker.get_open_positions()
        for trade in open_trades:
            symbol = trade.symbol
            ticket = trade.ticket
            entry = trade.price_open
            curr = mt5.symbol_info_tick(symbol).bid if trade.type == 0 else mt5.symbol_info_tick(symbol).ask
            
            # PnL Calc
            profit_points = curr - entry if trade.type == 0 else entry - curr
            sl_dist = abs(entry - trade.sl) if trade.sl > 0 else 0
            
            if sl_dist > 0:
                r = profit_points / sl_dist
                is_at_be = (trade.sl >= entry) if trade.type == 0 else (trade.sl <= entry)
                
                # Rule: BE at 1.2R
                if r >= 1.2 and not is_at_be:
                     self.broker.modify_position(ticket, sl=entry, tp=trade.tp)
                     self.notifier.send(f"🛡️ {symbol} -> Breakeven (R={r:.2f})")

                # Rule: Partial at 1.0R
                if r >= 1.0 and "Partial" not in trade.comment:
                    vol = round(trade.volume * 0.4, 2)
                    if vol >= 0.01:
                        self.broker.close_partial(ticket, vol)
                        self.notifier.send(f"💵 {symbol} Partial Taken")

    def run_cycle(self):
        self.cycles_run += 1
        
        self.session.update_session_status()
        context = self.session.get_context()

        if context['session_status'] == "CLOSED":
            if self.cycles_run % 12 == 0: 
                logger.info("💤 Market Closed. Session Manager Asleep.")
            return

        if self.paused: return

        try:
            self.manage_positions()
        except Exception as e:
            logger.error(f"Manager Error: {e}")

        for symbol in settings.symbol_list:
            logger.info(f"Analyzing {symbol}...")
            
            try:
                data = self.broker.get_multi_timeframe_data(symbol)
                if not data: continue
                
                live = self.broker.get_live_metrics(symbol)
                spread = live.get('spread_pips', 100)
                
                # --- FLEXIBLE SPREAD LOGIC ---
                # Gold/Commodities get 5.0 pips. Forex gets 3.0 pips.
                if "XAU" in symbol or "GOLD" in symbol:
                    max_spread = 5.0
                else:
                    max_spread = 3.0
                
                if spread > max_spread:
                    logger.info(f"Skipping {symbol}: Spread {spread} > Limit {max_spread}")
                    continue
                # -----------------------------

                alpha_packet = self.alpha.get_market_state(data)
                
                if alpha_packet['final_alpha_score'] < 0.45:
                    logger.info(f"{symbol}: Low Alpha ({alpha_packet['final_alpha_score']}). Skipping.")
                    continue

                acct = self.broker.get_account_info()
                raw_trades = self.broker.get_open_positions(symbol)
                acct['open_trades_details'] = [{"ticket": t.ticket, "profit": t.profit, "type": t.type} for t in raw_trades]
                
                mem = self.memory.get(symbol, {})
                decision = self.brain.analyze_market(alpha_packet, acct, previous_context=context)
                self.memory[symbol] = {"plan": decision.get('plan'), "reasoning": decision.get('reasoning')}
                
                if decision['action'] in ["BUY", "SELL"]:
                    if decision['action'] == "BUY" and context['locked_bias'] == "BEARISH":
                        logger.warning(f"BLOCKED: AI tried BUY against BEARISH bias.")
                        continue
                    if decision['action'] == "SELL" and context['locked_bias'] == "BULLISH":
                        logger.warning(f"BLOCKED: AI tried SELL against BULLISH bias.")
                        continue

                    msg = f"🚀 **{symbol} CALL**\nAction: {decision['action']}\nScore: {alpha_packet['final_alpha_score']}\nReason: {decision.get('reasoning')}"
                    self.notifier.send(msg)
                    self.broker.execute_trade(decision['action'], symbol, decision['stop_loss'], decision['take_profit'], decision.get('risk_percentage', 0.5))
                else:
                    logger.info(f"{symbol} HOLD: {decision.get('reasoning')}")

            except Exception as e:
                if "429" in str(e):
                    logger.warning("⚠️ API Quota. Cooling 60s...")
                    time.sleep(60)
                else:
                    logger.error(f"Analysis Error: {e}")

    def start(self):
        if not self.broker.connect():
            self.notifier.send("🚨 Broker Connect Fail")
            sys.exit(1)
        
        self.notifier.send(f"✅ **QuantBot V6.3 Live**\nMode: Probabilistic Alpha\nPairs: {settings.SYMBOLS}")
        self.listener.start()
        
        while self.running:
            try:
                self.run_cycle()
                logger.info("Sleeping for 15 minutes...")
                time.sleep(900) 
            except Exception as e:
                logger.error(f"Loop Error: {e}")
                self.error_count += 1
                time.sleep(60)

    def shutdown(self, signum, frame):
        self.notifier.send("🛑 Bot Shutdown")
        self.running = False
        sys.exit(0)

if __name__ == "__main__":
    bot = TradingBot()
    signal.signal(signal.SIGTERM, bot.shutdown)
    signal.signal(signal.SIGINT, bot.shutdown)
    bot.start()