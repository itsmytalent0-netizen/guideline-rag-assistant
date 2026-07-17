"""Central configuration. Everything comes from environment variables (.env supported)."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Pharma Guidelines RAG"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Postgres (Supabase) in production; sqlite fallback for local dev
    database_url: str = "sqlite+aiosqlite:///./pharma_rag.db"

    # Registration policy
    allow_registration: bool = True
    invite_code: str = ""  # if set, users must supply it to register

    # Vector store (Zilliz Cloud serverless / Milvus)
    zilliz_uri: str = ""
    zilliz_token: str = ""
    collection_name: str = "pharma_chunks"

    # Embeddings
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    query_instruction: str = "Represent this sentence for searching relevant passages: "
    # torch | onnx | auto  (auto: torch if installed, else onnx — light servers use onnx)
    embedding_backend: str = "auto"
    embedding_onnx_file: str = "onnx/model.onnx"  # or onnx/model_quantized.onnx (smaller)

    # LLM provider API keys (all free tiers, no card)
    groq_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    cerebras_api_key: str = ""
    nvidia_api_key: str = ""
    github_token: str = ""
    mistral_api_key: str = ""

    # Router priority (comma separated provider names)
    llm_priority: str = "groq,gemini,openrouter,mistral,nvidia,github,cerebras"

    # Web search
    tavily_api_key: str = ""

    # Google Drive service account JSON (raw JSON string or base64 of it)
    google_service_account_json: str = ""

    # Retrieval tuning
    retrieval_top_k: int = 8
    retrieval_score_threshold: float = 0.35
    max_context_chars: int = 14000

    # Caching
    semantic_cache_threshold: float = 0.95
    cache_max_entries: int = 2000

    # Per-user chat rate limit
    user_rpm_limit: int = 6


@lru_cache
def get_settings() -> Settings:
    return Settings()
