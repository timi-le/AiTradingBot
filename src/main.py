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
        self.start_time = time.time()
        self.cycles_run = 0
        self.error_count = 0

    def get_recent_logs(self, n=15): return "\n".join(list(log_buffer)[-n:])
    def get_performance_metrics(self): return {"uptime": int(time.time()-self.start_time), "cycles": self.cycles_run}

    def is_trading_hours(self):
        current_hour = datetime.now(timezone.utc).hour
        # 07:00 UTC to 22:00 UTC
        if 7 <= current_hour < 22: return True
        return False

    def manage_positions(self):
        open_trades = self.broker.get_open_positions()
        for trade in open_trades:
            symbol = trade.symbol
            ticket = trade.ticket
            entry = trade.price_open
            curr = mt5.symbol_info_tick(symbol).bid if trade.type == 0 else mt5.symbol_info_tick(symbol).ask
            profit_points = curr - entry if trade.type == 0 else entry - curr
            sl_dist = abs(entry - trade.sl) if trade.sl > 0 else 0
            
            if sl_dist > 0:
                r = profit_points / sl_dist
                is_at_be = (trade.sl >= entry) if trade.type == 0 else (trade.sl <= entry)
                if r >= 1.2 and not is_at_be:
                     self.broker.modify_position(ticket, sl=entry, tp=trade.tp)
                     self.notifier.send(f"🛡️ {symbol} -> Breakeven (R={r:.2f})")
                if r >= 1.0 and "Partial" not in trade.comment:
                    vol = round(trade.volume * 0.4, 2)
                    if vol >= 0.01:
                        self.broker.close_partial(ticket, vol)
                        self.notifier.send(f"💵 {symbol} Partial Taken")

    def run_cycle(self):
        self.cycles_run += 1
        try:
            self.manage_positions()
        except Exception as e:
            logger.error(f"Manager Error: {e}")

        if not self.is_trading_hours():
            logger.info("💤 Asian Session - Monitoring Only")
            return

        if self.paused: return

        for symbol in settings.symbol_list:
            logger.info(f"Scanning {symbol}...")
            try:
                data = self.broker.get_multi_timeframe_data(symbol)
                if not data: continue
                
                live = self.broker.get_live_metrics(symbol)
                
                # Check Spread
                spread = live.get('spread_pips', 100)
                max_spread = 4.5 if "XAU" in symbol or "GOLD" in symbol else 2.5
                if spread > max_spread:
                    logger.info(f"Skipping {symbol}: Spread {spread} > {max_spread}")
                    continue

                # Pass Symbol to Analyzer for Volatility Scaling
                market_metrics = self.analyzer.calculate_regime_metrics(data, symbol)
                
                acct = self.broker.get_account_info()
                raw_trades = self.broker.get_open_positions(symbol)
                acct['open_trades_details'] = [{"ticket": t.ticket, "profit": t.profit, "type": t.type} for t in raw_trades]
                acct['open_trades_count'] = len(raw_trades)
                
                mem = self.memory.get(symbol, {})
                decision = self.brain.analyze_market(market_metrics, acct, previous_context=mem)
                self.memory[symbol] = {"plan": decision.get('plan'), "reasoning": decision.get('reasoning')}
                
                if decision['action'] in ["BUY", "SELL"]:
                    # Use the DYNAMIC risk percentage calculated by Math Engine
                    recommended_risk = market_metrics['risk_data']['dynamic_risk_pct']
                    
                    msg = f"🚀 **{symbol} CALL**\nAction: {decision['action']}\nRisk: {recommended_risk}% (Vol-Scaled)\nReason: {decision.get('reasoning')}"
                    self.notifier.send(msg)
                    self.broker.execute_trade(decision['action'], symbol, decision['stop_loss'], decision['take_profit'], recommended_risk)
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
        self.notifier.send(f"✅ **QuantBot V6.0 Live**\nVol-Scaled Risk Active")
        self.listener.start()
        
        while self.running:
            try:
                self.run_cycle()
                logger.info("Sleeping for 15 minutes...")
                time.sleep(900) 
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