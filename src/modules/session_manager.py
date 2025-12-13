import time
from datetime import datetime, timezone

class SessionManager:
    def __init__(self):
        self.current_session = "CLOSED"
        self.strategic_bias = "NEUTRAL" # The "Anchor"
        self.key_levels = {"support": 0.0, "resistance": 0.0}
        self.last_strategy_update = 0
        
    def update_session_status(self):
        """Determines if we are in London/NY active hours."""
        hour = datetime.now(timezone.utc).hour
        # 07:00 UTC (London Pre-market) to 21:00 UTC (NY Afternoon)
        if 7 <= hour < 21:
            if self.current_session == "CLOSED":
                # Session just started -> Reset Bias to force a fresh Strategic Analysis
                self.strategic_bias = "NEUTRAL" 
            self.current_session = "OPEN"
        else:
            self.current_session = "CLOSED"
            self.strategic_bias = "NEUTRAL"

    def update_strategic_view(self, daily_trend, h4_trend, key_structure):
        """
        Updates the 'Strategist' view. 
        Only allows bias flip if H4 and Daily BOTH align strongly.
        Prevents M15 noise from changing the daily plan.
        """
        # Lock in bias if both align
        if daily_trend == h4_trend and daily_trend != "NEUTRAL":
            self.strategic_bias = daily_trend
            self.key_levels = key_structure
        # If they disagree, we default to NEUTRAL (Stand aside) 
        # unless we already have a bias, in which case we hold it until broken.
        elif self.strategic_bias != "NEUTRAL":
             # Keep old bias unless structure completely breaks
             pass 

    def get_context(self):
        """Returns the 'Strategist' orders for the 'Tactician'."""
        return {
            "session_status": self.current_session,
            "locked_bias": self.strategic_bias,
            "key_levels": self.key_levels,
            "instruction": f"ONLY look for {self.strategic_bias} setups. IGNORE counter-trend signals."
        }