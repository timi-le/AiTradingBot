import pandas as pd
import pandas_ta as ta
import numpy as np

# --- FEATURE EXTRACTORS ---

class LiquidityScore:
    """
    Calculates proximity to structural levels (Swing Highs/Lows).
    Score peaks (1.0) when price sweeps a level.
    Decays as price moves away.
    """
    def __init__(self, lookback=20, proximity_threshold=0.5):
        self.lookback = lookback
        self.threshold = proximity_threshold # In ATR units

    def calculate(self, df, atr_series):
        # 1. Identify Structural Points (Rolling Max/Min)
        recent_low = df['low'].shift(1).rolling(self.lookback).min()
        recent_high = df['high'].shift(1).rolling(self.lookback).max()
        
        # 2. Calculate Distances (in ATR units)
        # Low: Negative distance = Sweep. Positive = Above.
        dist_low = (df['low'] - recent_low) / atr_series
        # High: Negative distance = Sweep (Price > High). Positive = Below.
        dist_high = (recent_high - df['high']) / atr_series
        
        # 3. Score Calculation (0.0 to 1.0)
        # We take the MAX score of either High or Low structure proximity
        score_low = np.where(dist_low <= 0, 1.0, 
                    np.where(dist_low <= self.threshold, 1.0 - (dist_low / self.threshold), 0.0))
                    
        score_high = np.where(dist_high <= 0, 1.0,
                     np.where(dist_high <= self.threshold, 1.0 - (dist_high / self.threshold), 0.0))
        
        # Return the max intensity and the type of structure interacting
        return np.maximum(score_low, score_high), np.where(score_low > score_high, "SUPPORT_LOW", "RESISTANCE_HIGH")

class FairValueScore:
    """
    Calculates Mean Reversion potential using Normalized Z-Score.
    High score = Price is stretched (Opportunity for reversal or snap-back).
    """
    def __init__(self, ema_period=50):
        self.ema_period = ema_period

    def calculate(self, close_series, atr_series):
        fair_value = ta.ema(close_series, length=self.ema_period)
        if fair_value is None: return np.zeros_like(close_series)
        
        # Z-Score: Distance from Mean in ATRs
        z_raw = (close_series - fair_value) / atr_series
        
        # Normalize: Cap extreme at 2.5 ATRs = 1.0 Score
        return np.clip(abs(z_raw) / 2.5, 0.0, 1.0)

class VolatilityScore:
    """
    Regime Filter.
    Score 1.0 = Healthy Volatility (Good for trading).
    Score < 1.0 = Low Volatility (Compression/Chop).
    """
    def __init__(self, avg_period=50):
        self.period = avg_period
        
    def calculate(self, atr_series):
        atr_avg = atr_series.rolling(self.period).mean()
        # Ratio: Current / Average
        ratio = atr_series / atr_avg
        # Cap at 1.0 (We just want to know if it's "Active Enough")
        return np.clip(ratio, 0.0, 1.0)

class MomentumScore:
    """
    Timing Filter.
    Checks Trend Slope and EMA Crossover.
    """
    def __init__(self, fast=9, slow=21):
        self.fast = fast
        self.slow = slow

    def calculate(self, close_series):
        fast_ema = ta.ema(close_series, length=self.fast)
        slow_ema = ta.ema(close_series, length=self.slow)
        
        if fast_ema is None or slow_ema is None: return np.zeros_like(close_series)
        
        # 1. Binary Crossover (0 or 1)
        # We assume Momentum is absolute intensity. 
        # For Alpha calculation, we want "Is there momentum?", Direction is handled by Trend Logic.
        # Here we calculate 'Alignment Strength'
        
        # Gap Strength (Normalized)
        gap = abs(fast_ema - slow_ema) / close_series
        strength = np.clip(gap * 1000, 0, 1.0) # Scale factor for forex
        
        # Base Score (Is Fast separated from Slow?)
        # We treat crossover as a state, strength as magnitude
        return strength # Simplified to just strength of trend for Alpha Summation

class AlphaStack:
    """
    The Aggregator. Combines features into a single Alpha Probability.
    """
    def __init__(self):
        self.weights = {
            "structure": 0.35,
            "reversion": 0.30,
            "volatility": 0.20,
            "momentum": 0.15
        }

    def get_total_alpha(self, s, r, v, m):
        alpha = (
            self.weights["structure"] * s +
            self.weights["reversion"] * r +
            self.weights["volatility"] * v +
            self.weights["momentum"] * m
        )
        return np.clip(alpha, 0.0, 1.0)

# --- MAIN MODEL ---

class AlphaModel:
    def __init__(self):
        self.liq = LiquidityScore()
        self.fv = FairValueScore()
        self.vol = VolatilityScore()
        self.mom = MomentumScore()
        self.stack = AlphaStack()

    def _process_tf(self, candles):
        df = pd.DataFrame(candles)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # Base Indicators
        atr = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['atr'] = atr
        
        # Feature Engineering
        s_score, s_type = self.liq.calculate(df, atr)
        r_score = self.fv.calculate(df['close'], atr)
        v_score = self.vol.calculate(atr)
        m_score = self.mom.calculate(df['close'])
        
        # Get Latest Values
        last_s = s_score[-1] if isinstance(s_score, np.ndarray) else s_score.iloc[-1]
        last_r = r_score.iloc[-1]
        last_v = v_score.iloc[-1]
        last_m = m_score.iloc[-1]
        struct_type = s_type[-1] if isinstance(s_type, np.ndarray) else s_type.iloc[-1]
        
        # Calculate Final Alpha
        total_alpha = self.stack.get_total_alpha(last_s, last_r, last_v, last_m)
        
        return {
            "alpha": round(float(total_alpha), 2),
            "breakdown": {
                "structure": round(float(last_s), 2),
                "reversion": round(float(last_r), 2),
                "volatility": round(float(last_v), 2),
                "momentum": round(float(last_m), 2),
                "structure_type": struct_type
            },
            "close": float(df['close'].iloc[-1]),
            "atr": float(atr.iloc[-1])
        }

    def get_market_state(self, data_bundle):
        # We focus on M5 for Execution Alpha, H1/H4 for Context
        m5_alpha = self._process_tf(data_bundle['M5'])
        h1_alpha = self._process_tf(data_bundle['H1'])
        
        # Determine Status Tag
        status = "WAIT"
        if m5_alpha['alpha'] > 0.60: status = "REVIEW_REQUIRED"
        if m5_alpha['alpha'] > 0.85: status = "HIGH_CONVICTION"

        return {
            "packet_type": "PROBABILISTIC_ALPHA",
            "timestamp": pd.Timestamp.now().isoformat(),
            "final_alpha_score": m5_alpha['alpha'],
            "status": status,
            "m5_metrics": m5_alpha,
            "h1_context": h1_alpha
        }