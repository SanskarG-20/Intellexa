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
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS (comma-separated origins). Example:
    # CORS_ALLOW_ORIGINS=https://intellexa-lac.vercel.app,https://your-frontend.app
    CORS_ALLOW_ORIGINS: str = ""
    CORS_ALLOW_ORIGIN_REGEX: str = r"https?://(localhost|127\.0\.0\.1)(:\d+)?$|https://([a-zA-Z0-9-]+\.)*vercel\.app$"

    # Gemini Settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    FORCE_REFRAME_DEBUG: bool = False

    # Together AI Settings (for embeddings)
    TOGETHER_API_KEY: str = ""
    TOGETHER_EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"

    # Hugging Face Settings
    HF_TOKEN: str = ""
    HF_MODEL: str = "meta-llama/Llama-3.1-8B-Instruct"

    # Supabase Settings
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""  # Anon key (for client-side)
    SUPABASE_SERVICE_ROLE_KEY: str = ""  # Service role key (for backend - bypasses RLS)
    
    # Supabase Storage Settings (for Memory System)
    SUPABASE_STORAGE_BUCKET: str = "user-uploads"
    
    # Memory System Settings
    MAX_FILE_SIZE_MB: int = 50
    EMBEDDING_DIMENSION: int = 768  # Gemini embedding dimension
    CHUNK_MAX_TOKENS: int = 500
    CHUNK_OVERLAP_TOKENS: int = 50
    EMBEDDING_VALIDATE_ON_STARTUP: bool = False
    EMBEDDING_FORCE_HASH_FALLBACK: bool = False

    # Search API Settings (optional — enables SerpAPI over DuckDuckGo fallback)
    SERPAPI_API_KEY: str = ""

    # Code Workspace Settings
    CODE_ASSIST_MAX_PROMPT_CHARS: int = 4000
    CODE_ASSIST_MAX_CODE_CHARS: int = 120000
    CODE_ASSIST_CACHE_TTL_SECONDS: int = 120
    CODE_ASSIST_CACHE_MAX_ITEMS: int = 500

    # Project Refactor Engine Settings
    PROJECT_REFACTOR_CACHE_TTL_SECONDS: int = 180
    PROJECT_REFACTOR_CACHE_MAX_ITEMS: int = 200
    PROJECT_REFACTOR_MAX_PROMPT_CHARS: int = 220000
    PROJECT_REFACTOR_MAX_FILES_IN_PROMPT: int = 60
    PROJECT_REFACTOR_MAX_FILE_CHARS_IN_PROMPT: int = 20000

    # Sandboxed Code Execution Settings
    CODE_EXECUTION_ENABLED: bool = True
    CODE_EXECUTION_USE_DOCKER: bool = False
    CODE_EXECUTION_DOCKER_IMAGE: str = "python:3.11-alpine"
    CODE_EXECUTION_TIMEOUT_MS: int = 3000
    CODE_EXECUTION_MAX_OUTPUT_CHARS: int = 8000
    CODE_EXECUTION_MAX_CODE_CHARS: int = 20000
    CODE_EXECUTION_CPU_LIMIT: str = "0.5"
    CODE_EXECUTION_MEMORY_LIMIT_MB: int = 256

    # Project Context Engine Settings
    PROJECT_CONTEXT_MAX_FILES: int = 4000
    PROJECT_CONTEXT_MAX_FILE_SIZE_KB: int = 256
    PROJECT_CONTEXT_BATCH_SIZE: int = 40
    PROJECT_CONTEXT_CACHE_TTL_SECONDS: int = 180
    PROJECT_CONTEXT_INCLUDE_EMBEDDINGS_BY_DEFAULT: bool = False

    # Dependency Graph Settings
    DEPENDENCY_GRAPH_CACHE_TTL_SECONDS: int = 180
    DEPENDENCY_GRAPH_MAX_NODES: int = 8000
    DEPENDENCY_GRAPH_MAX_EDGES: int = 20000
    DEPENDENCY_GRAPH_INCLUDE_EXTERNAL_NODES: bool = True

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

    @field_validator("PORT", mode="before")
    @classmethod
    def parse_port(cls, value):
        if value is None:
            return 8000

        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return 8000

        if parsed <= 0:
            return 8000

        return parsed

    def get_cors_origins(self) -> list[str]:
        defaults = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ]

        configured = [
            origin.strip()
            for origin in str(self.CORS_ALLOW_ORIGINS or "").split(",")
            if origin.strip()
        ]

        # Preserve order while removing duplicates.
        unique = []
        seen = set()
        for origin in [*defaults, *configured]:
            if origin not in seen:
                unique.append(origin)
                seen.add(origin)

        return unique

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    def get_max_file_size_bytes(self) -> int:
        """Return max file size in bytes."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


settings = Settings()
