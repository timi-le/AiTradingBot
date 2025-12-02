import pandas as pd
import pandas_ta as ta
import numpy as np

class MarketAnalyzer:
    def _get_liquidity_evidence(self, df):
        """Extracts raw forensic evidence for the AI."""
        last = df.iloc[-1]
        
        # Structure (Last 20 bars)
        recent_high = df['high'].iloc[-22:-2].max()
        recent_low = df['low'].iloc[-22:-2].min()
        
        # Interaction
        pierce_high = max(0.0, last['high'] - recent_high)
        pierce_low = max(0.0, recent_low - last['low'])
        closed_inside_high = last['close'] < recent_high
        closed_inside_low = last['close'] > recent_low
        
        # Wicks
        total_range = last['high'] - last['low']
        upper_wick = last['high'] - max(last['close'], last['open'])
        lower_wick = min(last['close'], last['open']) - last['low']
        
        wr_upper = upper_wick / total_range if total_range > 0 else 0
        wr_lower = lower_wick / total_range if total_range > 0 else 0
        
        return {
            "structure": {"high": float(recent_high), "low": float(recent_low)},
            "interaction": {
                "pierced_high": float(pierce_high),
                "pierced_low": float(pierce_low),
                "fakeout_high": bool(pierce_high > 0 and closed_inside_high),
                "fakeout_low": bool(pierce_low > 0 and closed_inside_low)
            },
            "wicks": {"upper_ratio": round(wr_upper, 2), "lower_ratio": round(wr_lower, 2)}
        }

    def _process_single_tf(self, candles):
        df = pd.DataFrame(candles)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        df['ema_50'] = ta.ema(df['close'], length=50)
        df['ema_200'] = ta.ema(df['close'], length=200)
        adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
        df['adx'] = adx_df['ADX_14'] if not adx_df.empty else 0
        df['rsi'] = ta.rsi(df['close'], length=14)

        # Liquidity Check
        evidence = self._get_liquidity_evidence(df)
        
        last = df.iloc[-1]
        trend = "NEUTRAL"
        if last['close'] > last['ema_50'] > last['ema_200']: trend = "BULLISH"
        elif last['close'] < last['ema_50'] < last['ema_200']: trend = "BEARISH"

        return {
            "close": float(last['close']),
            "trend": trend,
            "evidence": evidence,
            "adx": round(float(last['adx']), 2),
            "rsi": round(float(last['rsi']), 2)
        }

    def calculate_regime_metrics(self, data_bundle: dict, live_metrics: dict):
        d1 = self._process_single_tf(data_bundle['D1'])
        h4 = self._process_single_tf(data_bundle['H4'])
        h1 = self._process_single_tf(data_bundle['H1']) # NEW: Added H1 Processing
        m15 = self._process_single_tf(data_bundle['M15']) 
        
        regime = "TRANSITION"
        if h4['adx'] > 25: regime = "TRENDING"
        elif h4['adx'] < 20: regime = "RANGING"

        return {
            "market_context": {
                "regime": regime,
                "daily_bias": d1['trend'],
                "h4_trend": h4['trend'],
                "h1_trend": h1['trend'], # Now sending H1 to AI
                "h4_adx": h4['adx']
            },
            "liquidity_forensics": {
                "m15_structure": m15['evidence']['structure'],
                "m15_interaction": m15['evidence']['interaction'],
                "m15_wicks": m15['evidence']['wicks']
            },
            "live_data": {
                "spread_pips": live_metrics.get('spread_pips', 0),
                "ask": live_metrics.get('ask'),
                "bid": live_metrics.get('bid')
            }
        }