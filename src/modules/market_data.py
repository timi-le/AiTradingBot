import pandas as pd
import pandas_ta as ta
import numpy as np

class MarketAnalyzer:
    def _detect_price_action(self, df):
        """Identifies recent candlestick patterns."""
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. Pinbar Detection (Wick vs Body)
        body_size = abs(last['close'] - last['open'])
        total_range = last['high'] - last['low']
        upper_wick = last['high'] - max(last['close'], last['open'])
        lower_wick = min(last['close'], last['open']) - last['low']
        
        pattern = "NONE"
        
        # Bullish Pinbar (Long lower wick)
        if total_range > 0 and (lower_wick / total_range) > 0.60:
            pattern = "BULLISH_PINBAR"
        # Bearish Pinbar (Long upper wick)
        elif total_range > 0 and (upper_wick / total_range) > 0.60:
            pattern = "BEARISH_PINBAR"
            
        # 2. Engulfing Detection
        # Bullish: Previous Red, Current Green & Huge
        if prev['close'] < prev['open'] and last['close'] > last['open']:
            if last['close'] > prev['open'] and last['open'] < prev['close']:
                pattern = "BULLISH_ENGULFING"
        # Bearish: Previous Green, Current Red & Huge
        if prev['close'] > prev['open'] and last['close'] < last['open']:
            if last['close'] < prev['open'] and last['open'] > prev['close']:
                pattern = "BEARISH_ENGULFING"
                
        return pattern

    def _get_structure_levels(self, df):
        """Finds recent Swing Highs and Lows (Fractals)."""
        # Simple local max/min over last 20 bars
        recent_high = df['high'].rolling(20).max().iloc[-1]
        recent_low = df['low'].rolling(20).min().iloc[-1]
        return recent_high, recent_low

    def _process_single_tf(self, candles):
        df = pd.DataFrame(candles)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # Indicators
        df['ema_50'] = ta.ema(df['close'], length=50)
        df['ema_200'] = ta.ema(df['close'], length=200)
        adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
        df['adx'] = adx_df['ADX_14'] if not adx_df.empty else 0
        df['rsi'] = ta.rsi(df['close'], length=14)

        # Price Action Analysis
        pattern = self._detect_price_action(df)
        res, sup = self._get_structure_levels(df)
        
        last = df.iloc[-1]
        trend = "NEUTRAL"
        if last['close'] > last['ema_50'] > last['ema_200']: trend = "BULLISH"
        elif last['close'] < last['ema_50'] < last['ema_200']: trend = "BEARISH"

        return {
            "close": float(last['close']),
            "trend": trend,
            "pattern": pattern,
            "support_level": float(sup),
            "resistance_level": float(res),
            "adx": round(float(last['adx']), 2),
            "rsi": round(float(last['rsi']), 2)
        }

    def calculate_regime_metrics(self, data_bundle: dict, live_metrics: dict):
        d1 = self._process_single_tf(data_bundle['D1'])
        h4 = self._process_single_tf(data_bundle['H4'])
        m15 = self._process_single_tf(data_bundle['M15']) # Scalping Timeframe
        
        # Regime Logic
        regime = "TRANSITION"
        if h4['adx'] > 25: regime = "TRENDING"
        elif h4['adx'] < 20: regime = "RANGING"

        return {
            "market_context": {
                "regime": regime,
                "daily_bias": d1['trend'],
                "h4_trend": h4['trend']
            },
            "price_action_signals": {
                "m15_pattern": m15['pattern'],
                "m15_structure": {
                    "support": m15['support_level'],
                    "resistance": m15['resistance_level']
                },
                "proximity_to_support": abs(m15['close'] - m15['support_level']),
                "proximity_to_resistance": abs(m15['close'] - m15['resistance_level'])
            },
            "live_data": {
                "spread_pips": live_metrics.get('spread_pips', 0),
                "ask": live_metrics.get('ask'),
                "bid": live_metrics.get('bid')
            }
        }