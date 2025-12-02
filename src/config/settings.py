from pydantic_settings import BaseSettings
from pydantic import Field, SecretStr
from typing import Literal, List

class Settings(BaseSettings):
    # System
    ENVIRONMENT: Literal["development", "production"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Strategy Params
    # CHANGED: Supports comma-separated list (e.g., "XAUUSD, GBPUSD")
    SYMBOLS: str = "XAUUSD" 
    TIMEFRAME: str = "H4"
    MAX_RISK_PER_TRADE: float = Field(0.01, ge=0.001, le=0.05)

    # API Keys & Secrets
    GEMINI_API_KEY: SecretStr
    MT5_LOGIN: int
    MT5_PASSWORD: SecretStr
    MT5_SERVER: str

    # NEW: Telegram Notification Keys (Optional but recommended)
    # We default to empty string so the bot doesn't crash if you haven't set them yet
    TELEGRAM_BOT_TOKEN: SecretStr = SecretStr("")
    TELEGRAM_CHAT_ID: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # This tells Pydantic to ignore extra keys in .env (like system variables)
        extra = "ignore" 

    # Helper to convert "XAUUSD, GBPUSD" string into a Python List
    @property
    def symbol_list(self) -> List[str]:
        return [s.strip() for s in self.SYMBOLS.split(",")]

settings = Settings()