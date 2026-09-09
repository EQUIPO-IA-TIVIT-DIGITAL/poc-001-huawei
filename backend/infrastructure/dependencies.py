"""
Container de Inyección de Dependencias - TIVIT Video
Local-first: Postgres + MinIO/filesystem + vLLM + Whisper.

Feature flags en config/app_config.py: STORAGE_BACKEND, DB_BACKEND, AI_PROVIDER.
Este módulo centraliza la creación y acceso a repositorios y servicios.

Uso:
    from infrastructure.dependencies import get_database_adapter, get_storage_adapter

    # En cualquier blueprint o módulo:
    database = get_database_adapter()
    storage = get_storage_adapter()
"""

from typing import Optional, Protocol, Any
from flask import current_app


# ========== PROTOCOLOS (INTERFACES) ==========


class VideoRepositoryProtocol(Protocol):
    """Interfaz para repositorio de videos."""

    def save_video(self, video: Any) -> bool: ...
    def get_video(self, id: str) -> Optional[Any]: ...
    def get_all_videos(self, limit: int) -> list: ...
    def get_videos_by_socio(self, socio_id: str) -> list: ...
    def delete_video(self, id: str) -> bool: ...


class UserRepositoryProtocol(Protocol):
    """Interfaz para repositorio de usuarios."""

    def obtener_por_id(self, id: str) -> Optional[Any]: ...
    def autenticar(self, username: str, password: str) -> Optional[Any]: ...
    def existe_username(self, username: str) -> bool: ...
    def guardar(self, usuario: Any) -> Any: ...


class StorageAdapterProtocol(Protocol):
    """Interfaz para adaptador de almacenamiento."""

    def upload_video(self, local_path: str, storage_path: str) -> Optional[str]: ...
    def is_available(self) -> bool: ...
    def get_signed_url(
        self, storage_path: str, expiration_minutes: int
    ) -> Optional[str]: ...


class DatabaseAdapterProtocol(Protocol):
    """Interfaz para adaptador de base de datos."""

    def save_video(self, video: Any) -> bool: ...
    def is_available(self) -> bool: ...


# ========== FUNCIONES DE ACCESO A DEPENDENCIAS LOCALES ==========


def get_app_config():
    """Obtiene la configuración local (AppConfig)."""
    try:
        return current_app.extensions["app_config"]
    except (RuntimeError, KeyError):
        from config.app_config import AppConfig
        return AppConfig()


def get_storage_adapter() -> Optional[StorageAdapterProtocol]:
    """Obtiene el adaptador de almacenamiento (MinIO/filesystem según AppConfig)"""
    try:
        s = current_app.extensions.get("storage_adapter")
        if s is not None:
            return s
        raise KeyError
    except (RuntimeError, KeyError):
        from config.app_config import AppConfig
        backend = getattr(AppConfig, "STORAGE_BACKEND", "filesystem")
        if backend == "minio":
            from infrastructure.adapters.minio_storage_adapter import MinioStorageAdapter
            return MinioStorageAdapter(AppConfig)
        from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
        return FilesystemStorageAdapter()


def get_database_adapter() -> Optional[DatabaseAdapterProtocol]:
    """Obtiene el adaptador de BD (Postgres/SQLite local)"""
    try:
        db = current_app.extensions.get("db_adapter")
        if db is not None:
            return db
        raise KeyError
    except (RuntimeError, KeyError):
        from infrastructure.db.session import engine
        class _LocalDB:
            def is_available(self):  # type: ignore
                try:
                    from sqlalchemy import text
                    with engine.connect() as c:
                        c.execute(text("SELECT 1"))
                    return True
                except Exception:
                    return False
            def save_video(self, video):  # type: ignore
                try:
                    from infrastructure.repositories.sqlalchemy_repositories import SQLAlchemyVideoRepository
                    return bool(SQLAlchemyVideoRepository().guardar(video))
                except Exception:
                    return False
        return _LocalDB()  # type: ignore


def get_user_repository() -> UserRepositoryProtocol:
    """
    Obtiene el repositorio de usuarios (Postgres/SQLite local).
    """
    try:
        return current_app.extensions["usuario_repository"]
    except (RuntimeError, KeyError):
        from infrastructure.repositories.sqlalchemy_repositories import SQLAlchemyUserRepository
        return SQLAlchemyUserRepository()


def get_video_repository() -> VideoRepositoryProtocol:
    """
    Obtiene el repositorio de videos (Postgres/SQLite local).
    """
    try:
        return current_app.extensions["video_repository"]
    except (RuntimeError, KeyError):
        from infrastructure.repositories.sqlalchemy_repositories import SQLAlchemyVideoRepository
        return SQLAlchemyVideoRepository()


def get_video_processor():
    """
    Obtiene el procesador de videos pre-configurado con todas las dependencias GCP.

    Returns:
        Instancia de ProcesarVideoUseCase con dependencias inyectadas
    """
    try:
        return current_app.extensions.get("video_processor")
    except RuntimeError:
        return None


def get_ai_service():
    """Obtiene el servicio de IA (Gateway local 32B / ApiLLM)"""
    try:
        svc = current_app.extensions.get("ai_service")
        if svc is not None:
            return svc
        raise RuntimeError
    except RuntimeError:
        try:
            from config.app_config import AppConfig
            if getattr(AppConfig, "AI_PROVIDER", "hybrid") != "disabled":
                from infrastructure.adapters.ai_gateway import get_ai_gateway
                return get_ai_gateway()
        except Exception:
            pass
        from infrastructure.adapters.ai_service import AIService
        return AIService()


def get_ai_adapter():
    """Obtiene el adaptador de IA local."""
    try:
        ga = current_app.extensions.get("ai_adapter")
        if ga is not None:
            return ga
        raise RuntimeError
    except RuntimeError:
        from infrastructure.adapters.ai_gateway import get_ai_gateway
        return get_ai_gateway()


def get_task_queue():
    """Obtiene el adaptador de cola de tareas (RQ)"""
    try:
        return current_app.extensions.get("task_queue")
    except RuntimeError:
        return None


def verificar_conexion_local() -> dict:
    """
    Verifica la conexión con todos los servicios locales (stack propio).
    """
    storage = get_storage_adapter()
    db = get_database_adapter()
    task_queue = get_task_queue()
    # IA gateway
    try:
        ai = get_ai_service()
        ai_available = ai.is_available() if hasattr(ai, "is_available") else getattr(ai, "disponible", False)
    except Exception:
        ai_available = False
    return {
        "storage": {
            "available": storage.is_available() if storage and hasattr(storage, "is_available") else False,
            "service": "MinIO / Filesystem",
        },
        "database": {
            "available": db.is_available() if db and hasattr(db, "is_available") else False,
            "service": "PostgreSQL / SQLite",
        },
        "task_queue": {
            "available": bool(task_queue),
            "service": "Redis + RQ",
        },
        "ai_gateway": {
            "available": bool(ai_available),
            "service": "AI Gateway 32B (vLLM/ApiLLM)",
        },
    }


# ========== INICIALIZACIÓN DE DEPENDENCIAS (LOCAL-FIRST) ==========


def init_dependencies(app):
    """
    Inicializa todas las dependencias (stack 100% local).

    Flags en config/app_config.py: STORAGE_BACKEND, DB_BACKEND, AI_PROVIDER.
    Esta función se llama desde create_app() en main.py.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Config — AppConfig local
    from config.app_config import AppConfig as _Config
    app_config = _Config()

    # ---- Storage (MinIO / Filesystem) ----
    storage_adapter = None
    storage_backend = getattr(app_config, "STORAGE_BACKEND", "filesystem")
    if storage_backend == "minio":
        try:
            from infrastructure.adapters.minio_storage_adapter import MinioStorageAdapter
            storage_adapter = MinioStorageAdapter(app_config)
        except Exception as e:
            logger.error(f"❌ MinIO init fallo, fallback filesystem: {e}")
            try:
                from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
                storage_adapter = FilesystemStorageAdapter()
            except Exception as e2:
                logger.error(f"❌ Filesystem fallback fallo: {e2}")
    else:
        try:
            from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
            storage_adapter = FilesystemStorageAdapter()
        except Exception as e:
            logger.error(f"❌ FilesystemStorage init fallo: {e}")

    # ---- DB (Postgres/SQLite local) ----
    database_adapter = None
    db_backend = getattr(app_config, "DB_BACKEND", "sqlite")
    try:
        from infrastructure.db.session import engine
        from sqlalchemy import text
        # ensure tables exist (idempotente, para clone sin alembic)
        try:
            if db_backend == "postgres":
                with engine.begin() as conn:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            from infrastructure.db.base import Base
            import infrastructure.db.models  # noqa
            Base.metadata.create_all(bind=engine)
        except Exception as e:
            logger.warning(f"create_all fallo (continuando): {e}")
        class _LocalDB:
            def is_available(self):
                try:
                    with engine.connect() as c:
                        c.execute(text("SELECT 1"))
                    return True
                except Exception:
                    return False
            def save_video(self, video):
                try:
                    from infrastructure.repositories.sqlalchemy_repositories import SQLAlchemyVideoRepository
                    return bool(SQLAlchemyVideoRepository().guardar(video))
                except Exception:
                    return False
        database_adapter = _LocalDB()  # type: ignore
    except Exception as e:
        logger.error(f"❌ Local DB shim fallo: {e}")

    # ---- Cola de tareas (RQ / Redis vía job_queue module) ----
    task_queue = None

    # ---- IA: Gateway 32B local / ApiLLM / disabled ----
    ai_provider = getattr(app_config, "AI_PROVIDER", "hybrid")
    ai_adapter = None
    ai_service = None
    speech_adapter = None

    if ai_provider != "disabled":
        try:
            from infrastructure.adapters.ai_gateway import get_ai_gateway
            gw = get_ai_gateway()
            ai_adapter = gw
            ai_service = gw
            logger.info(f"✅ AI Gateway 32B init provider={ai_provider} local={getattr(app_config,'AI_LOCAL_BASE_URL','-')}")
        except Exception as e:
            logger.warning(f"⚠️ AI Gateway fallo: {e}")

        # Speech: Whisper local
        try:
            from infrastructure.adapters.whisper_adapter import WhisperAdapter
            speech_adapter = WhisperAdapter()
        except Exception as e:
            logger.warning(f"⚠️ Whisper init fallo: {e}")

    try:
        from infrastructure.services.video_frame_extractor import VideoFrameExtractor
        frame_extractor = VideoFrameExtractor()
    except Exception as e:
        logger.error(f"⚠️ Frame Extractor fallo: {e}")
        frame_extractor = None

    # ---- Repositorios (Postgres/SQLite local) ----
    try:
        from infrastructure.repositories.sqlalchemy_repositories import SQLAlchemyUserRepository, SQLAlchemyVideoRepository
        usuario_repository = SQLAlchemyUserRepository()
        video_repository = SQLAlchemyVideoRepository()
        logger.info(f"✅ Repos SQLAlchemy ({db_backend}) activos")
    except Exception as e:
        logger.error(f"❌ SQLAlchemy repos fallo: {e}")
        usuario_repository = None
        video_repository = None

    # Caso de uso pre-configurado v4.0
    from use_cases.video_processor import ProcesarVideoUseCase
    video_processor = ProcesarVideoUseCase(
        storage_adapter=storage_adapter,
        firestore_adapter=database_adapter,
        gemini_adapter=ai_adapter,
        speech_adapter=speech_adapter,
        frame_extractor=frame_extractor,
        video_intelligence_adapter=None,
    )

    # Local extension names used by application code.
    app.extensions["app_config"] = app_config
    app.extensions["storage_adapter"] = storage_adapter
    app.extensions["db_adapter"] = database_adapter
    app.extensions["task_queue"] = task_queue
    app.extensions["ai_service"] = ai_service
    app.extensions["ai_adapter"] = ai_adapter
    app.extensions["speech_adapter"] = speech_adapter
    app.extensions["frame_extractor"] = frame_extractor
    app.extensions["usuario_repository"] = usuario_repository
    app.extensions["video_repository"] = video_repository
    app.extensions["video_processor"] = video_processor

    # Log de estado
    import logging

    logger = logging.getLogger(__name__)
    logger.info("✅ Dependencias inicializadas (stack local, Pipeline v4.0):")
    logger.info(
        f"   • Storage: {'✅' if storage_adapter and storage_adapter.is_available() else '❌'}"
    )
    logger.info(
        f"   • DB: {'✅' if database_adapter and database_adapter.is_available() else '❌'}"
    )
    logger.info(
        f"   • Task Queue: {'✅' if task_queue else '❌'}"
    )
    logger.info(
        f"   • AI Gateway: {'✅' if ai_adapter and ai_adapter.is_available() else '❌ (Deshabilitado/Error)'}"
    )
    logger.info(
        f"   • Speech-to-Text: {'✅' if speech_adapter and speech_adapter.is_available() else '❌ (Deshabilitado/Error)'}"
    )
    logger.info(
        f"   • Frame Extractor: {'✅' if frame_extractor and frame_extractor.is_available() else '❌ (Deshabilitado/Error)'}"
    )

    return {
        "app_config": app_config,
        "storage_adapter": storage_adapter,
        "db_adapter": database_adapter,
        "task_queue": task_queue,
        "ai_service": ai_service,
        "ai_adapter": ai_adapter,
        "speech_adapter": speech_adapter,
        "frame_extractor": frame_extractor,
        "usuario_repository": usuario_repository,
        "video_repository": video_repository,
        "video_processor": video_processor,
    }
