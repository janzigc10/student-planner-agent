from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./student_planner.db"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    llm_api_key: str = "sk-placeholder"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.3
    agent_runtime: str = "legacy"
    rag_corpus_dir: str = "data/rag"
    rag_embedding_provider: str = "dashscope"
    rag_embedding_model: str = "text-embedding-v4"
    rag_embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    rag_embedding_api_key: str = ""
    rag_embedding_batch_size: int = 10
    rag_vector_store_provider: str = "chroma"
    rag_vector_store_dir: str = "data/rag/chroma"
    vision_llm_api_key: str = ""
    vision_llm_base_url: str = ""
    vision_llm_model: str = "qwen-vl-plus"
    session_timeout_minutes: int = 120
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_claims_email: str = "mailto:admin@studentplanner.local"

    model_config = SettingsConfigDict(
        env_prefix="SP_",
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
