# ── Application Configuration ─────────────────────────────────────────────────
# Loads settings from environment variables / .env file via pydantic-settings.

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/project_assistant"
    )

    # ── JWT ───────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── CORS ──────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        """Return CORS origins as a list (split from comma-separated env var)."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # ── File Uploads ──────────────────────────────────────────────────────
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 25
    ALLOWED_UPLOAD_EXTENSIONS: str = ".pdf,.docx,.txt"

    @property
    def allowed_upload_extensions_set(self) -> set[str]:
        """Return allowed extensions as a set of lowercase strings."""
        return {
            ext.strip().lower()
            for ext in self.ALLOWED_UPLOAD_EXTENSIONS.split(",")
            if ext.strip()
        }

    # ── Vectorization & Embeddings ──────────────────────────────────────
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    SEARCH_TOP_K: int = 5
    INGESTION_TIMEOUT_SECONDS: int = 600  # 10 min — covers first-run model download

    # ── LLM / Extraction ───────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:14b"  # stronger function-calling than 7B
    OLLAMA_NUM_CTX: int = 12288  # agent needs room for tool schemas + results
    OLLAMA_NUM_PREDICT: int = 8192  # final structured output can be large
    EXTRACTION_CHUNKS_PER_DOC: int = 15  # max chunks per tool call
    EXTRACTION_POLICY_TOP_K: int = 10  # max policy chunks per search
    AGENT_MAX_ITERATIONS: int = 8  # max tool-calling rounds before forced stop


# Singleton instance — import this everywhere
settings = Settings()
