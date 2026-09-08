"""
AppConfig — Configuración unificada Local Offline (32B)
Reemplaza config/gcp_config.py (GCPConfig) con feature flags.

Prioridad: ENV (.env) > defaults. Carga .env al importar.
Mantiene compatibilidad con GCPConfig legacy via alias + shim.
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
    # storage: minio | filesystem | gcs_legacy
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "filesystem" if os.getenv("S3_ENDPOINT") is None and os.getenv("STORAGE_BACKEND") is None else os.getenv("STORAGE_BACKEND", "minio")).lower()
    # Normalizar: si no hay S3_ENDPOINT y no se pidió minio, usar filesystem
    if STORAGE_BACKEND not in ("minio", "filesystem", "gcs_legacy"):
        STORAGE_BACKEND = "filesystem"

    # db: postgres | sqlite | firestore_legacy
    DB_BACKEND: str = os.getenv("DB_BACKEND", "postgres" if os.getenv("DATABASE_URL") else "sqlite").lower()
    if DB_BACKEND not in ("postgres", "sqlite", "firestore_legacy"):
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
    S3_BUCKET: str = os.getenv("S3_BUCKET", os.getenv("GCP_BUCKET_NAME", "cu002-videos"))
    S3_ACCESS_KEY: Optional[str] = os.getenv("S3_ACCESS_KEY") or os.getenv("MINIO_ROOT_USER")
    S3_SECRET_KEY: Optional[str] = os.getenv("S3_SECRET_KEY") or os.getenv("MINIO_ROOT_PASSWORD")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")
    S3_USE_SSL: bool = os.getenv("S3_USE_SSL", "false").lower() == "true"

    # ---- Redis ----
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")

    # ---- IA 32B ----
    AI_API_BASE_URL: Optional[str] = os.getenv("AI_API_BASE_URL")
    AI_API_KEY: Optional[str] = os.getenv("AI_API_KEY")
    AI_API_MODEL: str = os.getenv("AI_API_MODEL", "qwen2.5-vl-32b")

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

    # ---- GCP legacy (solo para compat) ----
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "cu002-local")
    GCP_REGION: str = os.getenv("GCP_REGION", "us-central1")
    GCP_BUCKET_NAME: str = os.getenv("GCP_BUCKET_NAME", S3_BUCKET)
    SIGNED_URL_EXPIRATION_MINUTES: int = int(os.getenv("SIGNED_URL_EXPIRATION_MINUTES", "60"))

    # Lifecycle
    LIFECYCLE_NEARLINE_DAYS: int = int(os.getenv("GCP_LIFECYCLE_NEARLINE_DAYS", "30"))
    LIFECYCLE_COLDLINE_DAYS: int = int(os.getenv("GCP_LIFECYCLE_COLDLINE_DAYS", "90"))
    LIFECYCLE_DELETE_TEMP_DAYS: int = int(os.getenv("GCP_LIFECYCLE_DELETE_TEMP_DAYS", "7"))

    # Firestore collections (legacy alias)
    FIRESTORE_COLLECTION_VIDEOS: str = "videos"
    FIRESTORE_COLLECTION_USERS: str = "users"
    FIRESTORE_COLLECTION_LOGS: str = "logs"
    BUCKET_VIDEOS_FOLDER: str = "videos/"
    BUCKET_THUMBNAILS_FOLDER: str = "thumbnails/"

    @classmethod
    def validate_config(cls) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not cls.SECRET_KEY and cls.IS_PRODUCTION:
            errors.append("SECRET_KEY requerido en producción")
        if cls.STORAGE_BACKEND == "minio" and not cls.S3_ENDPOINT:
            errors.append("S3_ENDPOINT requerido con STORAGE_BACKEND=minio")
        if cls.DB_BACKEND == "postgres" and not cls.DATABASE_URL.startswith("postgresql"):
            # sqlite es fallback válido
            pass
        return len(errors) == 0, errors

    @classmethod
    def is_gcp_enabled(cls) -> bool:
        """Shim compat: true si DB/storage legacy GCP."""
        return cls.STORAGE_BACKEND == "gcs_legacy" or cls.DB_BACKEND == "firestore_legacy"

    @classmethod
    def is_local_enabled(cls) -> bool:
        return not cls.is_gcp_enabled()

    @classmethod
    def get_bucket_url(cls, filename: str, folder: str | None = None) -> str:
        if folder:
            return f"s3://{cls.S3_BUCKET}/{folder}/{filename}"
        return f"s3://{cls.S3_BUCKET}/{filename}"

    @classmethod
    def get_video_path(cls, video_id: str, extension: str = "mp4") -> str:
        return f"{cls.BUCKET_VIDEOS_FOLDER}{video_id}.{extension}"

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
            "ai_api_base_url": cls.AI_API_BASE_URL,
            "project_id": cls.GCP_PROJECT_ID,
            "region": cls.GCP_REGION,
        }

# Alias legacy: GCPConfig -> AppConfig para no romper imports existentes
GCPConfig = AppConfig
config = AppConfig()
