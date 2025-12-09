import pandas as pd
import pandas_ta as ta
import numpy as np

class MarketAnalyzer:
    def _calculate_volatility_scaling(self, symbol, current_atr):
        """
        Implements Version 6.0 Volatility Scaling Formula.
        Risk scales UP when volatility is low, and DOWN when volatility is high.
        """
        base_risk = 0.50
        
        # Reference ATRs from XML
        ref_atr = 0.0080 if "GBP" in symbol else 4.50 # Default to XAUUSD logic if not GBP
        
        if current_atr <= 0: return base_risk
        
        # Formula: risk = Base * clamp(Ref / Current, 0.5, 2.0)
        scaling_factor = ref_atr / current_atr
        scaling_factor = max(0.5, min(scaling_factor, 2.0))
        
        return round(base_risk * scaling_factor, 2)

    def _get_forensics(self, df):
        """Calculates Wicks, Volume Spikes, and Sweeps."""
        last = df.iloc[-1]
        
        # 1. Indicators needed for Forensics
        atr = ta.atr(df['high'], df['low'], df['close'], length=14).iloc[-1]
        avg_vol = df['tick_volume'].rolling(50).mean().iloc[-1]
        
        # 2. Wick Calculations
        total_range = last['high'] - last['low']
        upper_wick = last['high'] - max(last['close'], last['open'])
        lower_wick = min(last['close'], last['open']) - last['low']
        
        # 3. Liquidity Sweep Logic (XML Rule: Wick >= 1.5 * ATR)
        is_high_prob_sweep = False
        sweep_type = "NONE"
        
        # Bearish Sweep check
        if upper_wick >= (1.5 * atr) and last['close'] < last['open']: 
            sweep_type = "BEARISH_SWEEP"
        # Bullish Sweep check
        elif lower_wick >= (1.5 * atr) and last['close'] > last['open']:
            sweep_type = "BULLISH_SWEEP"
            
        # Volume Confirmation (XML Rule: Vol >= 2.0 * Avg)
        is_vol_spike = last['tick_volume'] >= (2.0 * avg_vol)
        
        if sweep_type != "NONE" and is_vol_spike:
            is_high_prob_sweep = True

        return {
            "atr": float(atr),
            "volume_spike": bool(is_vol_spike),
            "sweep_signal": sweep_type,
            "high_prob_setup": is_high_prob_sweep,
            "upper_wick_pct": round(upper_wick / total_range, 2) if total_range > 0 else 0,
            "lower_wick_pct": round(lower_wick / total_range, 2) if total_range > 0 else 0
        }

    def _process_tf(self, candles):
        df = pd.DataFrame(candles)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # Standard Indicators
        df['ema_50'] = ta.ema(df['close'], length=50)
        df['ema_200'] = ta.ema(df['close'], length=200)
        adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
        df['adx'] = adx_df['ADX_14'] if not adx_df.empty else 0
        
        # Donchian Channels (20)
        df['donchian_high'] = df['high'].rolling(20).max()
        df['donchian_low'] = df['low'].rolling(20).min()
        
        forensics = self._get_forensics(df)
        
        last = df.iloc[-1]
        
        # Trend Status
        trend = "NEUTRAL"
        if last['close'] > last['ema_50'] > last['ema_200']: trend = "BULLISH"
        elif last['close'] < last['ema_50'] < last['ema_200']: trend = "BEARISH"
        
        # Donchian Status
        in_range = (last['high'] < last['donchian_high']) and (last['low'] > last['donchian_low'])

        return {
            "trend": trend,
            "adx": round(float(last['adx']), 2),
            "in_donchian_range": bool(in_range),
            "forensics": forensics,
            "close": float(last['close'])
        }

    def calculate_regime_metrics(self, data_bundle: dict, symbol: str):
        # We process M5 (Scalp), H1 (Breakout), H4 (Bias)
        h4 = self._process_tf(data_bundle['H4'])
        h1 = self._process_tf(data_bundle['H1'])
        m5 = self._process_tf(data_bundle['M5'])
        
        # 1. Determine Regime
        regime = "TRANSITION"
        if h4['adx'] >= 25: regime = "TRENDING"
        elif h4['adx'] < 20 and h4['in_donchian_range']: regime = "RANGING"
        
        # 2. Calculate Dynamic Risk (Volatility Scaling)
        # We use H1 ATR for the broad volatility Context
        current_atr = h1['forensics']['atr']
        dynamic_risk_pct = self._calculate_volatility_scaling(symbol, current_atr)
        
        return {
            "market_context": {
                "regime": regime,
                "h4_trend": h4['trend'],
                "h1_trend": h1['trend'],
                "m5_trend": m5['trend'],
                "volatility_risk_scale": f"{dynamic_risk_pct}% (Base 0.5%)"
            },
            "scalp_signals_m5": {
                "sweep": m5['forensics']['sweep_signal'],
                "volume_spike": m5['forensics']['volume_spike'],
                "is_high_prob": m5['forensics']['high_prob_setup']
            },
            "breakout_signals_h1": {
                "sweep": h1['forensics']['sweep_signal'],
                "volume_spike": h1['forensics']['volume_spike']
            },
            "risk_data": {
                "dynamic_risk_pct": dynamic_risk_pct
            }
        }