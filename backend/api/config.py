"""
Harness API Configuration
"""
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "Harness"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # API
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "https://harness.vet"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://harness:harness@localhost:5432/harness"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 3600  # 1 hour

    # Authentication
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # AWS
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_ENVIRONMENT: str = "development"  # development, staging, production
    S3_BUCKET_NAME: str = "harness-veterinary-corpus"
    S3_MODELS_BUCKET: str = "harness-models"
    S3_PAPERS_BUCKET: str = "harness-veterinary-corpus" if AWS_ENVIRONMENT == "production" else f"harness-veterinary-corpus-{AWS_ENVIRONMENT}"

    # Weaviate
    WEAVIATE_URL: str = "http://localhost:8080"
    WEAVIATE_API_KEY: Optional[str] = None

    # Model Configuration
    EMBEDDING_MODEL: str = "text-embedding-3-small"  # OpenAI embeddings
    LLM_MODEL: str = "medgemma-27b-vet-it"
    INFERENCE_ENDPOINT: str = "http://localhost:8000"
    OPENAI_API_KEY: Optional[str] = None

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000

    # Monitoring
    PROMETHEUS_ENABLED: bool = True
    SENTRY_DSN: Optional[str] = None

    # Ask Service
    ASK_MAX_CHUNKS: int = 40
    ASK_RERANK_TOP_K: int = 10
    ASK_TIMEOUT_SECONDS: int = 30

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    
    # Airflow
    AIRFLOW_URL: str = "http://localhost:8080"
    
    # Paper Crawling
    NCBI_API_KEY: Optional[str] = None
    CROSSREF_EMAIL: Optional[str] = None
    
    # MinIO/S3 Storage
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minioadmin"
    MINIO_ENDPOINT: str = "http://localhost:9000"


settings = Settings()