"""
AppConfig — Configuración unificada Local Offline (32B)

Prioridad: ENV (.env) > defaults. Carga .env al importar.
"""
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class AppConfig:
    """Configuración central local-first."""

    # ---- Entorno ----
    APP_ENV: str = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development"))
    IS_PRODUCTION: bool = os.getenv("FLASK_ENV") == "production"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    # ---- Feature flags (local-first) ----
    # storage: minio | filesystem
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "filesystem" if os.getenv("S3_ENDPOINT") is None and os.getenv("STORAGE_BACKEND") is None else os.getenv("STORAGE_BACKEND", "minio")).lower()
    # Normalizar: si no hay S3_ENDPOINT y no se pidió minio, usar filesystem
    if STORAGE_BACKEND not in ("minio", "filesystem"):
        STORAGE_BACKEND = "filesystem"

    # db: postgres | sqlite
    DB_BACKEND: str = os.getenv("DB_BACKEND", "postgres" if os.getenv("DATABASE_URL") else "sqlite").lower()
    if DB_BACKEND not in ("postgres", "sqlite"):
        DB_BACKEND = "postgres"

    # ai: hybrid | local | api | disabled
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "hybrid").lower()
    if AI_PROVIDER not in ("hybrid", "local", "api", "disabled"):
        AI_PROVIDER = "hybrid"

    # ---- Postgres ----
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./cu002.db")
    PGVECTOR_ENABLED: bool = os.getenv("PGVECTOR_ENABLED", "true").lower() == "true"

    # ---- S3 / MinIO ----
    S3_ENDPOINT: Optional[str] = os.getenv("S3_ENDPOINT")
    S3_BUCKET: str = os.getenv("S3_BUCKET", "cu002-videos")
    S3_ACCESS_KEY: Optional[str] = os.getenv("S3_ACCESS_KEY") or os.getenv("MINIO_ROOT_USER")
    S3_SECRET_KEY: Optional[str] = os.getenv("S3_SECRET_KEY") or os.getenv("MINIO_ROOT_PASSWORD")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")
    S3_USE_SSL: bool = os.getenv("S3_USE_SSL", "false").lower() == "true"

    # ---- Redis ----
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")

    # ---- IA 32B / OpenAI-compatible APIs ----
    AI_API_PROVIDER: str = os.getenv("AI_API_PROVIDER", "openrouter").lower()
    AI_API_BASE_URL: Optional[str] = os.getenv("AI_API_BASE_URL")
    AI_API_KEY: Optional[str] = os.getenv("AI_API_KEY")
    AI_API_MODEL: str = os.getenv("AI_API_MODEL", "qwen2.5-vl-32b")
    AI_API_TEXT_MODEL: str = os.getenv("AI_API_TEXT_MODEL", AI_API_MODEL)
    AI_API_VISION_MODEL: str = os.getenv("AI_API_VISION_MODEL", AI_API_MODEL)
    AI_API_EMBEDDING_MODEL: Optional[str] = os.getenv("AI_API_EMBEDDING_MODEL")

    OPENROUTER_SITE_URL: str = os.getenv("OPENROUTER_SITE_URL", "http://localhost:5173")
    OPENROUTER_APP_NAME: str = os.getenv("OPENROUTER_APP_NAME", "TIVIT CU002")

    AI_LOCAL_BASE_URL: str = os.getenv("AI_LOCAL_BASE_URL", "http://vllm-vision:8000/v1")
    AI_LOCAL_MODEL: str = os.getenv("AI_LOCAL_MODEL", "Qwen/Qwen2.5-VL-32B-Instruct-AWQ")
    AI_LOCAL_TEXT_BASE_URL: str = os.getenv("AI_LOCAL_TEXT_BASE_URL", "http://vllm-text:8002/v1")
    AI_LOCAL_TEXT_MODEL: str = os.getenv("AI_LOCAL_TEXT_MODEL", "Qwen/Qwen2.5-32B-Instruct-AWQ")
    AI_LOCAL_EMBEDDING_MODEL: str = os.getenv("AI_LOCAL_EMBEDDING_MODEL", "BAAI/bge-m3")

    WHISPER_BASE_URL: str = os.getenv("WHISPER_BASE_URL", "http://whisper:8001/v1")
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")

    VLLM_TENSOR_PARALLEL_SIZE: int = int(os.getenv("VLLM_TENSOR_PARALLEL_SIZE", "4"))
    VLLM_GPU_MEMORY_UTILIZATION: float = float(os.getenv("VLLM_GPU_MEMORY_UTILIZATION", "0.92"))
    VLLM_MAX_MODEL_LEN: int = int(os.getenv("VLLM_MAX_MODEL_LEN", "8192"))

    SIGNED_URL_EXPIRATION_MINUTES: int = int(os.getenv("SIGNED_URL_EXPIRATION_MINUTES", "60"))

    STORAGE_VIDEOS_FOLDER: str = "videos/"
    STORAGE_THUMBNAILS_FOLDER: str = "thumbnails/"

    @classmethod
    def validate_config(cls) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not cls.SECRET_KEY and cls.IS_PRODUCTION:
            errors.append("SECRET_KEY requerido en producción")
        if cls.STORAGE_BACKEND == "minio" and not cls.S3_ENDPOINT:
            errors.append("S3_ENDPOINT requerido con STORAGE_BACKEND=minio")
        if cls.STORAGE_BACKEND == "minio" and not cls.S3_ACCESS_KEY:
            errors.append("S3_ACCESS_KEY o MINIO_ROOT_USER requerido con STORAGE_BACKEND=minio")
        if cls.STORAGE_BACKEND == "minio" and not cls.S3_SECRET_KEY:
            errors.append("S3_SECRET_KEY o MINIO_ROOT_PASSWORD requerido con STORAGE_BACKEND=minio")
        if cls.AI_PROVIDER == "api" and not cls.AI_API_BASE_URL:
            errors.append("AI_API_BASE_URL requerido con AI_PROVIDER=api")
        if cls.AI_PROVIDER == "api" and not cls.AI_API_KEY:
            errors.append("AI_API_KEY requerido con AI_PROVIDER=api")
        if cls.DB_BACKEND == "postgres" and not cls.DATABASE_URL.startswith("postgresql"):
            # sqlite es fallback válido
            pass
        return len(errors) == 0, errors

    @classmethod
    def get_bucket_url(cls, filename: str, folder: str | None = None) -> str:
        if folder:
            return f"s3://{cls.S3_BUCKET}/{folder}/{filename}"
        return f"s3://{cls.S3_BUCKET}/{filename}"

    @classmethod
    def get_video_path(cls, video_id: str, extension: str = "mp4") -> str:
        return f"{cls.STORAGE_VIDEOS_FOLDER}{video_id}.{extension}"

    @classmethod
    def get_config_summary(cls) -> dict:
        is_valid, errors = cls.validate_config()
        return {
            "enabled": True,
            "valid": is_valid,
            "errors": errors,
            "app_env": cls.APP_ENV,
            "storage_backend": cls.STORAGE_BACKEND,
            "db_backend": cls.DB_BACKEND,
            "ai_provider": cls.AI_PROVIDER,
            "database_url": cls.DATABASE_URL.split("@")[-1] if "@" in cls.DATABASE_URL else cls.DATABASE_URL,
            "s3_endpoint": cls.S3_ENDPOINT,
            "s3_bucket": cls.S3_BUCKET,
            "ai_local_base_url": cls.AI_LOCAL_BASE_URL,
            "ai_local_model": cls.AI_LOCAL_MODEL,
            "ai_api_provider": cls.AI_API_PROVIDER,
            "ai_api_base_url": cls.AI_API_BASE_URL,
            "ai_api_text_model": cls.AI_API_TEXT_MODEL,
            "ai_api_vision_model": cls.AI_API_VISION_MODEL,
        }

config = AppConfig()
