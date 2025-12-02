import google.generativeai as genai
import json
import logging
from src.config.settings import settings

logger = logging.getLogger(__name__)

class GeminiBrain:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY.get_secret_value())
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

    # UPDATED: Now accepts 'previous_context'
    def analyze_market(self, market_data: dict, account_data: dict, previous_context: dict = None) -> dict:
        
        # We inject the "Memory" into the prompt
        memory_section = "No previous context (First run)."
        if previous_context:
            memory_section = f"""
            ## PREVIOUS ANALYSIS (5 Mins Ago):
            - Last Action: {previous_context.get('action')}
            - Last Reasoning: {previous_context.get('reasoning')}
            - Current Plan: {previous_context.get('plan', 'None')}
            
            INSTRUCTION: Maintain consistency. Do not flip-flop unless market structure has fundamentally broken.
            """

        prompt = f"""
        Act as the 'GeminiPropChallengeAssistant'.
        Follow this XML Strategy strictly:
        {self.strategy_xml}

        {memory_section}

        ## CURRENT MARKET DATA:
        {json.dumps(market_data, indent=2)}

        ## ACCOUNT STATUS:
        {json.dumps(account_data, indent=2)}

        ## TASK:
        Analyze Regime, Check Vetoes, and Decide.
        
        ## OUTPUT (JSON ONLY):
        {{
            "decision": {{
                "action": "BUY" | "SELL" | "HOLD",
                "risk_percentage": 0.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "plan": "Short description of what you are waiting for (e.g. 'Waiting for retest of 2650')",
                "reasoning": "string"
            }}
        }}
        """
        try:
            response = self.model.generate_content(prompt)
            return json.loads(response.text)['decision']
        except Exception as e:
            logger.error(f"Brain Error: {e}")
            return {"action": "HOLD", "reasoning": "AI Error"}