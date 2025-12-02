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
from src.modules.market_data import MarketAnalyzer
from src.modules.notifier import TelegramNotifier
from src.modules.listener import TelegramListener
import MetaTrader5 as mt5

# Logging Setup
log_buffer = collections.deque(maxlen=50)
class ListHandler(logging.Handler):
    def __init__(self, log_buffer):
        super().__init__()
        self.log_buffer = log_buffer
    def emit(self, record):
        self.log_buffer.append(self.format(record))

handler = ListHandler(log_buffer)
handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout), handler])
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        self.running = True
        self.paused = False
        self.broker = MT5Broker()
        self.brain = GeminiBrain()
        self.analyzer = MarketAnalyzer()
        self.notifier = TelegramNotifier()
        self.listener = TelegramListener(self)
        self.memory = {}
        
        # Tracking
        self.start_time = time.time()
        self.last_history_check = time.time() # Start tracking from NOW
        self.cycles_run = 0
        self.error_count = 0

    def get_recent_logs(self, n=15):
        return "\n".join(list(log_buffer)[-n:])

    def get_performance_metrics(self):
        return {
            "start_time": self.start_time,
            "cycles": self.cycles_run,
            "errors": self.error_count,
            "trades_managed": len(self.broker.get_open_positions()) if self.broker.connected else 0
        }

    def check_trade_outcomes(self):
        """Checks for trades closed since the last cycle (TP/SL hits)."""
        deals = self.broker.get_recent_deals(self.last_history_check)
        
        if deals:
            for deal in deals:
                symbol = deal.symbol
                profit = deal.profit
                comment = deal.comment
                
                # Determine outcome
                icon = "💰" if profit > 0 else "🛑"
                outcome = "WIN" if profit > 0 else "LOSS"
                
                # Filter out partial closes initiated by bot to avoid duplicate spam
                if "Partial" not in comment:
                    msg = (
                        f"{icon} **TRADE CLOSED: {symbol}**\n"
                        f"Result: {outcome}\n"
                        f"PnL: ${profit:.2f}\n"
                        f"Comment: {comment}"
                    )
                    self.notifier.send(msg)
                    logger.info(f"Trade Closed: {symbol} | ${profit:.2f}")

        # Update checkpoint so we don't notify twice
        self.last_history_check = time.time()

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
                # Rule 1: BE at 1.2R
                is_at_be = (trade.sl >= entry) if trade.type == 0 else (trade.sl <= entry)
                if r >= 1.2 and not is_at_be:
                     self.broker.modify_position(ticket, sl=entry, tp=trade.tp)
                     self.notifier.send(f"🛡️ {symbol} -> Breakeven (R={r:.2f})")

                # Rule 2: Partial at 1.0R
                if r >= 1.0 and "Partial" not in trade.comment:
                    vol = round(trade.volume * 0.4, 2)
                    if vol >= 0.01:
                        self.broker.close_partial(ticket, vol)
                        self.notifier.send(f"💵 {symbol} Partial Taken (R={r:.2f})")

    def run_cycle(self):
        self.cycles_run += 1
        
        # 1. Check for TP/SL hits from previous cycle
        try:
            self.check_trade_outcomes()
        except Exception as e:
            logger.error(f"History Check Error: {e}")

        # 2. Manage Active Trades
        try:
            self.manage_positions()
        except Exception as e:
            logger.error(f"Manager Error: {e}")

        if self.paused: return

        # 3. Scan for New Trades
        for symbol in settings.symbol_list:
            logger.info(f"Scanning {symbol}...")
            
            data = self.broker.get_multi_timeframe_data(symbol)
            if not data: continue
            
            live = self.broker.get_live_metrics(symbol)
            
            if live.get('spread_pips', 100) > 4.0:
                logger.info(f"Skipping {symbol}: High Spread")
                continue

            market_metrics = self.analyzer.calculate_regime_metrics(data, live)
            acct = self.broker.get_account_info()
            acct['open_trades'] = len(self.broker.get_open_positions(symbol))
            
            mem = self.memory.get(symbol, {})
            decision = self.brain.analyze_market(market_metrics, acct, previous_context=mem)
            self.memory[symbol] = {"plan": decision.get('plan'), "reasoning": decision.get('reasoning')}
            
            if decision['action'] in ["BUY", "SELL"]:
                msg = f"🚀 **{symbol} ENTRY**\nAction: {decision['action']}\nReason: {decision.get('reasoning')}"
                self.notifier.send(msg)
                self.broker.execute_trade(decision['action'], symbol, decision['stop_loss'], decision['take_profit'], decision['risk_percentage'])
            else:
                logger.info(f"{symbol} HOLD")

    def start(self):
        if not self.broker.connect():
            self.notifier.send("🚨 Broker Connect Fail")
            sys.exit(1)
        self.notifier.send(f"✅ **QuantBot V5 Live**\nTracking: {settings.SYMBOLS}")
        self.listener.start()
        
        while self.running:
            try:
                self.run_cycle()
                time.sleep(300)
            except Exception as e:
                logger.error(f"Loop Error: {e}")
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