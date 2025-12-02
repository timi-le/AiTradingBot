import google.generativeai as genai
import json
import logging
from src.config.settings import settings

logger = logging.getLogger(__name__)

class GeminiBrain:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY.get_secret_value())
        
        # Use the specific version that works for you
        self.model_name = 'gemini-2.5-flash'
        
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
        
        # Memory Injection
        memory_section = "No previous active plan."
        if previous_context:
            memory_section = f"""
            ## YOUR PREVIOUS MEMORY (5 Mins Ago):
            - Last Action: {previous_context.get('action')}
            - Your Plan: {previous_context.get('plan')}
            - Your Reasoning: {previous_context.get('reasoning')}
            
            INSTRUCTION: If your 'Plan' was to wait for a specific trigger, check the 'liquidity_forensics' below to see if it happened.
            """

        prompt = f"""
        Act as the 'GeminiPropChallengeAssistant'.
        Your Goal: Pass the Prop Firm Challenge by strictly following the XML Rules.

        --- XML CONSTITUTION ---
        {self.strategy_xml}

        {memory_section}

        ## CURRENT MARKET EVIDENCE (JSON):
        {json.dumps(market_data, indent=2)}
        
        ## ACCOUNT STATUS:
        {json.dumps(account_data, indent=2)}

        ## CRITICAL INSTRUCTIONS:
        1. **Look at 'liquidity_forensics'**: Did price pierce a level and reject? (Wick > 0.5)? If yes, this is a SWEEP.
        2. **Look at 'market_context'**: Is the Regime TRENDING or RANGING?
        3. **Look at 'live_data'**: Is spread high?
        4. **Risk Check**: Do not exceed MaxOpenRiskPct defined in XML.

        ## OUTPUT DECISION (JSON):
        {{
            "decision": {{
                "action": "BUY" | "SELL" | "HOLD",
                "risk_percentage": 0.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "plan": "What are you waiting for next?",
                "reasoning": "Explain using the forensic data (e.g. 'Bearish Sweep detected at H4 resistance')"
            }}
        }}
        """
        try:
            response = self.model.generate_content(prompt)
            return json.loads(response.text)['decision']
        except Exception as e:
            logger.error(f"Brain Error: {e}")
            return {"action": "HOLD", "reasoning": "AI Error"}