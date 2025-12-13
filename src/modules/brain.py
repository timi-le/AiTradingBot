import google.generativeai as genai
import json
import logging
from src.config.settings import settings

logger = logging.getLogger(__name__)

class GeminiBrain:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY.get_secret_value())
        self.model_name = 'gemini-flash-latest'
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config={"response_mime_type": "application/json"}
        )
        try:
            with open("strategy.xml", "r") as f:
                self.strategy_xml = f.read()
        except:
            self.strategy_xml = "Error: Logic file missing."

    def analyze_market(self, alpha_packet: dict, account_data: dict, previous_context: dict = None) -> dict:
        
        session_instructions = "None"
        if previous_context:
            session_instructions = f"""
            *** SESSION MANAGER ORDERS ***
            - LOCKED BIAS: {previous_context.get('locked_bias')}
            - INSTRUCTION: {previous_context.get('instruction')}
            """

        prompt = f"""
        Act as a Quant Trader analyzing Probabilistic Alpha.
        
        {session_instructions}

        --- ALPHA DATA PACKET (FUZZY LOGIC) ---
        Total Alpha Score: {alpha_packet['final_alpha_score']} / 1.0
        Status: {alpha_packet['status']}
        
        METRIC BREAKDOWN:
        - Structure (35%): {alpha_packet['m5_metrics']['breakdown']['structure']} (Type: {alpha_packet['m5_metrics']['breakdown']['structure_type']})
        - Reversion (30%): {alpha_packet['m5_metrics']['breakdown']['reversion']}
        - Volatility (20%): {alpha_packet['m5_metrics']['breakdown']['volatility']}
        - Momentum (15%): {alpha_packet['m5_metrics']['breakdown']['momentum']}

        --- ACCOUNT ---
        {json.dumps(account_data, indent=2)}

        --- STRATEGY RULES ---
        {self.strategy_xml}

        DECISION LOGIC:
        1. High Structure Score (>0.8) on SUPPORT_LOW = Potential BUY (Sweep).
        2. High Structure Score (>0.8) on RESISTANCE_HIGH = Potential SELL (Sweep).
        3. High Reversion Score (>0.7) = Price extended, look for mean reversion.
        4. MUST OBEY SESSION BIAS.

        OUTPUT JSON:
        {{
            "decision": {{
                "action": "BUY" | "SELL" | "HOLD",
                "risk_percentage": 0.5,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "reasoning": "Alpha Score 0.85 driven by Structure Sweep..."
            }}
        }}
        """
        try:
            response = self.model.generate_content(prompt)
            return json.loads(response.text)['decision']
        except Exception as e:
            logger.error(f"Brain Error: {e}")
            return {"action": "HOLD", "reasoning": "AI Error"}