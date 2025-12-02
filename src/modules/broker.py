import MetaTrader5 as mt5
import logging
from datetime import datetime
from src.config.settings import settings

logger = logging.getLogger(__name__)

class MT5Broker:
    def __init__(self):
        self.connected = False

    def connect(self) -> bool:
        if not mt5.initialize():
            return False
        if not mt5.login(settings.MT5_LOGIN, settings.MT5_PASSWORD.get_secret_value(), settings.MT5_SERVER):
            return False
        self.connected = True
        return True

    def verify_execution_capability(self, symbol: str) -> bool:
        """Places a Buy Limit far below price to test permissions, then deletes it."""
        if not self.connected and not self.connect(): return False
        
        tick = mt5.symbol_info_tick(symbol)
        if not tick: return False
        
        # 1. Place Safe Pending Order (10% below price)
        safe_price = tick.ask * 0.90
        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": 0.01,
            "type": mt5.ORDER_TYPE_BUY_LIMIT,
            "price": safe_price,
            "magic": 999999, 
            "comment": "System Test",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Test Trade Failed: {result.comment if result else 'None'}")
            return False
            
        logger.info(f"Test Order Placed: {result.order}")
        
        # 2. Delete Immediately
        delete_req = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": result.order,
            "magic": 999999,
        }
        mt5.order_send(delete_req)
        return True

    def get_multi_timeframe_data(self, symbol: str):
        if not self.connected and not self.connect(): return None
        timeframes = {"D1": mt5.TIMEFRAME_D1, "H4": mt5.TIMEFRAME_H4, "H1": mt5.TIMEFRAME_H1, "M15": mt5.TIMEFRAME_M15}
        data = {}
        for name, tf in timeframes.items():
            candles = mt5.copy_rates_from_pos(symbol, tf, 0, 300)
            if candles is None: return None
            data[name] = candles
        return data

    def get_live_metrics(self, symbol: str):
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if not tick or not info: return {}
        
        pip_size = info.point * 10 if info.digits in [3, 5] else info.point
        spread_pips = (tick.ask - tick.bid) / pip_size
        
        return {
            "spread_pips": round(spread_pips, 2),
            "ask": tick.ask,
            "bid": tick.bid,
            "point": info.point
        }

    def get_account_info(self):
        info = mt5.account_info()
        return {"balance": info.balance, "equity": info.equity, "margin_free": info.margin_free} if info else {}

    def get_open_positions(self, symbol: str = None):
        if not self.connected and not self.connect(): return []
        return (mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()) or []

    def get_recent_deals(self, start_timestamp):
        if not self.connected and not self.connect(): return []
        start_dt = datetime.fromtimestamp(start_timestamp)
        deals = mt5.history_deals_get(start_dt, datetime.now())
        if deals is None: return []
        return [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]

    def calculate_lot_size(self, symbol, risk_pct, sl_price, entry_price):
        account = mt5.account_info()
        symbol_info = mt5.symbol_info(symbol)
        if not account or not symbol_info: return 0.01
        
        risk_amount = account.balance * (risk_pct / 100)
        sl_dist = abs(entry_price - sl_price)
        if sl_dist == 0: return 0.01
        
        tick_val = symbol_info.trade_tick_value
        tick_size = symbol_info.trade_tick_size
        raw_lot = risk_amount / (sl_dist / tick_size * tick_val)
        
        step = symbol_info.volume_step
        return max(symbol_info.volume_min, min(round(raw_lot / step) * step, symbol_info.volume_max))

    def modify_position(self, ticket, sl=None, tp=None):
        req = {"action": mt5.TRADE_ACTION_SLTP, "position": ticket, "sl": float(sl) if sl else 0.0, "tp": float(tp) if tp else 0.0, "magic": 234000}
        mt5.order_send(req)

    def close_partial(self, ticket, volume_to_close):
        pos = mt5.positions_get(ticket=ticket)
        if not pos: return
        pos = pos[0]
        type_close = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(pos.symbol).bid if type_close == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(pos.symbol).ask
        
        req = {
            "action": mt5.TRADE_ACTION_DEAL, 
            "position": ticket, 
            "symbol": pos.symbol, 
            "volume": volume_to_close, 
            "type": type_close, 
            "price": price, 
            "magic": 234000
        }
        mt5.order_send(req)

    def execute_trade(self, action, symbol, sl, tp, risk_pct):
        if not self.connected and not self.connect(): return
        tick = mt5.symbol_info_tick(symbol)
        if not tick: return
        
        price = tick.ask if action == "BUY" else tick.bid
        volume = self.calculate_lot_size(symbol, risk_pct, sl, price)
        logger.info(f"Calculated Volume: {volume} lots (Risk: {risk_pct}%)")
        
        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "magic": 234000,
            "comment": "AI-Quant-Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Order Executed: {res.order}")
        else:
            logger.error(f"Order Failed: {res.comment if res else 'None'}")