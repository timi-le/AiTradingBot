import time
import signal
import sys
import logging
import json
from src.config.settings import settings
from src.modules.broker import MT5Broker
from src.modules.brain import GeminiBrain
from src.modules.market_data import AlphaModel
from src.modules.session_manager import SessionManager
from src.modules.notifier import TelegramNotifier
from src.modules.listener import TelegramListener

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
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
        self.start_time = time.time()

    def run_cycle(self):
        self.session.update_session_status()
        context = self.session.get_context()
        
        if context['session_status'] == "CLOSED":
            logger.info("💤 Market Closed. Session Manager Asleep.")
            return

        if self.paused: return

        for symbol in settings.symbol_list:
            logger.info(f"Analyzing {symbol}...")
            
            try:
                data = self.broker.get_multi_timeframe_data(symbol)
                if not data: continue
                
                # Check Spread
                live = self.broker.get_live_metrics(symbol)
                spread_limit = 4.5 if "XAU" in symbol else 2.5
                if live.get('spread_pips', 100) > spread_limit:
                    logger.info(f"Skipping {symbol}: Spread High")
                    continue

                # 1. Get Probabilistic Alpha (The Fuzzy Logic)
                alpha_packet = self.alpha.get_market_state(data)
                logger.info(f"Alpha Score: {alpha_packet['final_alpha_score']} ({alpha_packet['status']})")
                
                # 2. Gatekeeper: Only bother AI if Alpha is significant
                if alpha_packet['final_alpha_score'] < 0.45:
                    logger.info(f"{symbol} Low Alpha ({alpha_packet['final_alpha_score']}). Skipping AI.")
                    continue

                # 3. Account Data
                acct = self.broker.get_account_info()
                raw_trades = self.broker.get_open_positions(symbol)
                acct['open_trades_details'] = [{"ticket": t.ticket, "profit": t.profit} for t in raw_trades]

                # 4. AI Decision
                decision = self.brain.analyze_market(alpha_packet, acct, previous_context=context)
                
                # 5. Execute
                if decision['action'] in ["BUY", "SELL"]:
                    # Bias Check
                    if decision['action'] == "BUY" and context['locked_bias'] == "BEARISH":
                        logger.warning(f"BLOCKED: AI tried to BUY against BEARISH session bias.")
                        continue
                    if decision['action'] == "SELL" and context['locked_bias'] == "BULLISH":
                        logger.warning(f"BLOCKED: AI tried to SELL against BULLISH session bias.")
                        continue
                    
                    self.broker.execute_trade(decision['action'], symbol, decision['stop_loss'], decision['take_profit'], decision.get('risk_percentage', 0.5))
                    self.notifier.send(f"🚀 {symbol} {decision['action']} | Alpha: {alpha_packet['final_alpha_score']}")

            except Exception as e:
                logger.error(f"Cycle Error: {e}")
                time.sleep(5)

    def start(self):
        if not self.broker.connect():
            sys.exit(1)
        self.notifier.send("✅ **QuantBot V6.0 Live**\nEngine: Probabilistic Alpha")
        self.listener.start()
        while self.running:
            self.run_cycle()
            time.sleep(900) # 15 Mins

    def shutdown(self, signum, frame):
        self.running = False
        sys.exit(0)

if __name__ == "__main__":
    import signal
    bot = TradingBot()
    signal.signal(signal.SIGTERM, bot.shutdown)
    signal.signal(signal.SIGINT, bot.shutdown)
    bot.start()