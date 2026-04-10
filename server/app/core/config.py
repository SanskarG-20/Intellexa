from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """
    App configuration loaded from environment variables and .env.
    """

    APP_NAME: str = "Intellexa Core Chat"
    DEBUG: bool = True

    # Gemini Settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Hugging Face Settings
    HF_TOKEN: str = ""
    HF_MODEL: str = "meta-llama/Llama-3.1-8B-Instruct"

    # Supabase Settings
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # Search API Settings (optional — enables SerpAPI over DuckDuckGo fallback)
    SERPAPI_API_KEY: str = ""

    # Global User ID (Mock)
    MOCK_USER_ID: str = "demo_user"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_flag(cls, value):
        """
        Accept common shell values so DEBUG=release does not crash startup.
        """
        if isinstance(value, bool):
            return value

        if value is None:
            return True

        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug", "dev", "development"}:
            return True
        if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
            return False

        return False

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
