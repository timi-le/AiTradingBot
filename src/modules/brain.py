import google.generativeai as genai
import json
import logging
from src.config.settings import settings

logger = logging.getLogger(__name__)

class GeminiBrain:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY.get_secret_value())
        
        # FIX 1: Switched to 1.5-flash (Stable) to solve 429 Quota Error
        # This model has much higher limits (1,500/day vs 50/day)
        self.model_name = 'gemini-1.5-flash'
        
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config={"response_mime_type": "application/json"}
        )
        try:
            with open("strategy.xml", "r") as f:
                self.strategy_xml = f.read()
        except FileNotFoundError:
            self.strategy_xml = "Error: Logic file missing."

    def analyze_market(self, market_data: dict, account_data: dict, previous_context: dict = None) -> dict:
        
        open_trades_context = account_data.get('open_trades_details', [])
        
        prompt = f"""
        Act as the 'GeminiPropChallengeAssistant'.
        
        --- XML CONSTITUTION ---
        {self.strategy_xml}

        ## CURRENT MARKET EVIDENCE (JSON):
        {json.dumps(market_data, indent=2)}
        
        ## ACCOUNT & TRADES:
        {json.dumps(account_data, indent=2)}
        "Open Trades Details": {json.dumps(open_trades_context, default=str)}

        ## CRITICAL DIRECTION RULE:
        - If 'daily_bias' is BULLISH, you may ONLY 'BUY' or 'HOLD'. DO NOT SELL.
        - If 'daily_bias' is BEARISH, you may ONLY 'SELL' or 'HOLD'. DO NOT BUY.
        - IGNORE Overbought/Oversold indicators if they conflict with the Daily Bias. Trend is King.

        ## OUTPUT DECISION (JSON):
        {{
            "decision": {{
                "action": "BUY" | "SELL" | "HOLD",
                "management_action": "NONE" | "CLOSE_ALL_XAUUSD" | "CLOSE_ALL_GBPUSD",
                "risk_percentage": 0.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "plan": "Short plan",
                "reasoning": "Reasoning"
            }}
        }}
        """
        try:
            response = self.model.generate_content(prompt)
            return json.loads(response.text)['decision']
        except Exception as e:
            logger.error(f"Brain Error: {e}")
            return {"action": "HOLD", "management_action": "NONE", "reasoning": "AI Error"}