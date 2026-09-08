"""
Container de Inyección de Dependencias - TIVIT Video
Local-first: Soporta GCP legacy y stack local (Postgres+MinIO+vLLM 32B).

Feature flags en config/app_config.py: STORAGE_BACKEND, DB_BACKEND, AI_PROVIDER.
Este módulo centraliza la creación y acceso a repositorios y servicios.

Uso:
    from infrastructure.dependencies import get_firestore_adapter, get_storage_adapter

    # En cualquier blueprint o módulo:
    firestore = get_firestore_adapter()
    storage = get_storage_adapter()
"""

from typing import Optional, Protocol, Any
from flask import current_app


# ========== PROTOCOLOS (INTERFACES) ==========


class VideoRepositoryProtocol(Protocol):
    """Interfaz para repositorio de videos (Firestore)"""

    def save_video(self, video: Any) -> bool: ...
    def get_video(self, id: str) -> Optional[Any]: ...
    def get_all_videos(self, limit: int) -> list: ...
    def get_videos_by_socio(self, socio_id: str) -> list: ...
    def delete_video(self, id: str) -> bool: ...


class UserRepositoryProtocol(Protocol):
    """Interfaz para repositorio de usuarios (Firestore)"""

    def obtener_por_id(self, id: str) -> Optional[Any]: ...
    def autenticar(self, username: str, password: str) -> Optional[Any]: ...
    def existe_username(self, username: str) -> bool: ...
    def guardar(self, usuario: Any) -> Any: ...


class StorageAdapterProtocol(Protocol):
    """Interfaz para adaptador de almacenamiento (Cloud Storage)"""

    def upload_video(self, local_path: str, gcs_path: str) -> Optional[str]: ...
    def is_available(self) -> bool: ...
    def get_signed_url(
        self, gcs_path: str, expiration_minutes: int
    ) -> Optional[str]: ...


class DatabaseAdapterProtocol(Protocol):
    """Interfaz para adaptador de base de datos (Firestore)"""

    def save_video(self, video: Any) -> bool: ...
    def is_available(self) -> bool: ...


# ========== FUNCIONES DE ACCESO A DEPENDENCIAS GCP ==========


def get_gcp_config():
    """Obtiene la configuración (GCP legacy o AppConfig local)"""
    try:
        return current_app.extensions["gcp_config"]
    except (RuntimeError, KeyError):
        try:
            from config.app_config import AppConfig
            return AppConfig()
        except ImportError:
            from config.gcp_config import GCPConfig
            return GCPConfig()


def get_storage_adapter() -> Optional[StorageAdapterProtocol]:
    """Obtiene el adaptador de almacenamiento (MinIO/filesystem/GCS según AppConfig)"""
    try:
        # local-first: gcp_storage key aún usada como alias genérico
        s = current_app.extensions.get("gcp_storage") or current_app.extensions.get("storage_adapter")
        if s is not None:
            return s
        raise KeyError
    except (RuntimeError, KeyError):
        try:
            from config.app_config import AppConfig
            backend = getattr(AppConfig, "STORAGE_BACKEND", "filesystem")
            if backend == "minio":
                from infrastructure.adapters.minio_storage_adapter import MinioStorageAdapter
                return MinioStorageAdapter(AppConfig)
            elif backend == "filesystem":
                from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
                return FilesystemStorageAdapter()
        except Exception:
            pass
        from infrastructure.adapters.gcp_storage import CloudStorageAdapter
        return CloudStorageAdapter(get_gcp_config())


def get_firestore_adapter() -> Optional[DatabaseAdapterProtocol]:
    """Obtiene el adaptador de BD (Firestore legacy o Postgres local)"""
    try:
        db = current_app.extensions.get("gcp_firestore") or current_app.extensions.get("db_adapter")
        if db is not None:
            return db
        raise KeyError
    except (RuntimeError, KeyError):
        try:
            from config.app_config import AppConfig
            if getattr(AppConfig, "DB_BACKEND", "") in ("postgres", "sqlite"):
                from infrastructure.db.session import engine
                # lightweight adapter shim for verificar_conexion
                class _LocalDB:
                    def is_available(self):  # type: ignore
                        try:
                            from sqlalchemy import text
                            with engine.connect() as c:
                                c.execute(text("SELECT 1"))
                            return True
                        except Exception:
                            return False
                return _LocalDB()  # type: ignore
        except Exception:
            pass
        from infrastructure.adapters.gcp_firestore import FirestoreAdapter
        return FirestoreAdapter(get_gcp_config())


def get_user_repository() -> UserRepositoryProtocol:
    """
    Obtiene el repositorio de usuarios (Postgres/SQLite local o Firestore legacy).
    """
    try:
        return current_app.extensions["usuario_repository"]
    except (RuntimeError, KeyError):
        try:
            from config.app_config import AppConfig
            if getattr(AppConfig, "DB_BACKEND", "") in ("postgres", "sqlite"):
                from infrastructure.repositories.sqlalchemy_repositories import SQLAlchemyUserRepository
                return SQLAlchemyUserRepository()
        except Exception:
            pass
        from infrastructure.repositories.user_repository import UsuarioRepositoryMemory
        return UsuarioRepositoryMemory()


def get_video_repository() -> VideoRepositoryProtocol:
    """
    Obtiene el repositorio de videos (Postgres/SQLite local o Firestore legacy).
    """
    try:
        return current_app.extensions["video_repository"]
    except (RuntimeError, KeyError):
        try:
            from config.app_config import AppConfig
            if getattr(AppConfig, "DB_BACKEND", "") in ("postgres", "sqlite"):
                from infrastructure.repositories.sqlalchemy_repositories import SQLAlchemyVideoRepository
                return SQLAlchemyVideoRepository()
        except Exception:
            pass
        from infrastructure.repositories.video_repository import VideoRepositoryFirestore
        return VideoRepositoryFirestore()


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
    """Obtiene el servicio de IA (Gateway local 32B o Gemini legacy)"""
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


def get_gemini_adapter():
    """Obtiene el adaptador de IA (alias compat: Gateway 32B)"""
    try:
        ga = current_app.extensions.get("gemini_adapter")
        if ga is not None:
            return ga
        raise RuntimeError
    except RuntimeError:
        try:
            from config.app_config import AppConfig
            if getattr(AppConfig, "AI_PROVIDER", "hybrid") != "disabled":
                from infrastructure.adapters.ai_gateway import get_ai_gateway
                return get_ai_gateway()
        except Exception:
            pass
        from infrastructure.adapters.gemini_adapter import GeminiAdapter
        return GeminiAdapter(get_gcp_config())


def get_cloud_tasks_adapter():
    """Obtiene el adaptador de Cloud Tasks"""
    try:
        return current_app.extensions.get("cloud_tasks")
    except RuntimeError:
        from infrastructure.adapters.cloud_tasks_adapter import CloudTasksAdapter

        return CloudTasksAdapter()


def get_video_intelligence_adapter():
    """Obtiene el adaptador de Video Intelligence API"""
    try:
        return current_app.extensions.get("video_intelligence")
    except RuntimeError:
        from infrastructure.adapters.gcp_video_intelligence import (
            VideoIntelligenceAdapter,
        )

        return VideoIntelligenceAdapter(get_gcp_config())


def verificar_conexion_gcp() -> dict:
    """
    Verifica la conexión con todos los servicios (GCP legacy o local).
    """
    storage = get_storage_adapter()
    firestore = get_firestore_adapter()
    video_intel = get_video_intelligence_adapter()
    cloud_tasks = get_cloud_tasks_adapter()
    # IA gateway
    try:
        ai = get_ai_service()
        ai_available = ai.is_available() if hasattr(ai, "is_available") else getattr(ai, "disponible", False)
    except Exception:
        ai_available = False
    return {
        "cloud_storage": {
            "available": storage.is_available() if storage and hasattr(storage, "is_available") else False,
            "service": "Cloud Storage / MinIO / Filesystem",
        },
        "firestore": {
            "available": firestore.is_available() if firestore and hasattr(firestore, "is_available") else False,
            "service": "Firestore / Postgres",
        },
        "video_intelligence": {
            "available": video_intel.is_available() if video_intel and hasattr(video_intel, "is_available") else False,
            "service": "Video Intelligence API",
        },
        "cloud_tasks": {
            "available": getattr(cloud_tasks, "disponible", False) if cloud_tasks else False,
            "service": "Cloud Tasks / RQ",
        },
        "ai_gateway": {
            "available": bool(ai_available),
            "service": "AI Gateway 32B (vLLM/ApiLLM)",
        },
    }


# ========== INICIALIZACIÓN DE DEPENDENCIAS GCP ==========


def init_dependencies(app):
    """
    Inicializa todas las dependencias (local-first con fallback GCP legacy).

    Flags en config/app_config.py: STORAGE_BACKEND, DB_BACKEND, AI_PROVIDER.
    Esta función se llama desde create_app() en main.py.
    """
    import os
    import logging

    logger = logging.getLogger(__name__)

    # Config — local-first con compat GCP
    try:
        from config.app_config import AppConfig as _Config
        app_config = _Config()
        is_local = getattr(_Config, "DB_BACKEND", "sqlite") in ("postgres", "sqlite") or getattr(_Config, "STORAGE_BACKEND", "filesystem") in ("minio", "filesystem")
    except ImportError:
        from config.gcp_config import GCPConfig as _Config
        app_config = _Config()
        is_local = False

    # Compat: exponer como gcp_config para código legacy
    gcp_config = app_config

    # ---- Storage (MinIO / Filesystem / GCS legacy) ----
    gcp_storage = None
    storage_backend = getattr(app_config, "STORAGE_BACKEND", "filesystem") if is_local else "gcs_legacy"
    if storage_backend == "minio":
        try:
            from infrastructure.adapters.minio_storage_adapter import MinioStorageAdapter
            gcp_storage = MinioStorageAdapter(app_config)
        except Exception as e:
            logger.error(f"❌ MinIO init fallo, fallback filesystem: {e}")
            try:
                from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
                gcp_storage = FilesystemStorageAdapter()
            except Exception as e2:
                logger.error(f"❌ Filesystem fallback fallo: {e2}")
    elif storage_backend == "filesystem":
        try:
            from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
            gcp_storage = FilesystemStorageAdapter()
        except Exception as e:
            logger.error(f"❌ FilesystemStorage init fallo: {e}")
    else:
        try:
            from infrastructure.adapters.gcp_storage import CloudStorageAdapter
            gcp_storage = CloudStorageAdapter(gcp_config)
        except Exception as e:
            logger.error(f"❌ GCS init fallo: {e}")

    # ---- DB (Postgres/SQLite local o Firestore legacy) ----
    gcp_firestore = None
    db_backend = getattr(app_config, "DB_BACKEND", "sqlite") if is_local else "firestore_legacy"
    if db_backend in ("postgres", "sqlite"):
        # local: no Firestore, exponer shim is_available via SessionLocal
        try:
            from infrastructure.db.session import engine
            from sqlalchemy import text
            # ensure tables exist (idempotente, para clone sin alembic)
            try:
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
            gcp_firestore = _LocalDB()
        except Exception as e:
            logger.error(f"❌ Local DB shim fallo: {e}")
    else:
        try:
            from infrastructure.adapters.gcp_firestore import FirestoreAdapter
            gcp_firestore = FirestoreAdapter(gcp_config)
        except Exception as e:
            logger.error(f"❌ Firestore init fallo: {e}")

    # ---- Cloud Tasks (siempre local RQ shim) ----
    try:
        from infrastructure.adapters.cloud_tasks_adapter import CloudTasksAdapter
        cloud_tasks = CloudTasksAdapter()
    except Exception as e:
        logger.warning(f"CloudTasks shim fallo: {e}")
        cloud_tasks = None

    # ---- IA: Gateway 32B local / ApiLLM / disabled ----
    video_intelligence = None
    logger.info("ℹ️  Video Intelligence: DESHABILITADO (Gemini Vision v4.0 / vLLM 32B)")

    ai_provider = getattr(app_config, "AI_PROVIDER", "hybrid") if is_local else "api"
    gemini_adapter = None
    ai_service = None
    speech_adapter = None

    if ai_provider == "disabled":
        logger.info("ℹ️  AI_PROVIDER=disabled — IA deshabilitada")
    else:
        # Intenta Gateway 32B primero
        try:
            from infrastructure.adapters.ai_gateway import get_ai_gateway
            gw = get_ai_gateway()
            gemini_adapter = gw
            ai_service = gw
            logger.info(f"✅ AI Gateway 32B init provider={ai_provider} local={getattr(app_config,'AI_LOCAL_BASE_URL','-')}")
        except Exception as e:
            logger.warning(f"⚠️ AI Gateway fallo, intenta Gemini legacy: {e}")
            try:
                from infrastructure.adapters.gemini_adapter import GeminiAdapter
                gemini_adapter = GeminiAdapter()
                ai_service = gemini_adapter
            except Exception as e2:
                logger.error(f"⚠️ Gemini fallback fallo: {e2}")

        # Speech: Whisper local si local, senão GCP STT legacy
        if is_local and ai_provider != "disabled":
            try:
                from infrastructure.adapters.whisper_adapter import WhisperAdapter
                speech_adapter = WhisperAdapter()
            except Exception as e:
                logger.warning(f"⚠️ Whisper init fallo: {e}")
        else:
            try:
                from infrastructure.adapters.gcp_speech import GCPSpeechAdapter
                speech_adapter = GCPSpeechAdapter(gcp_config)
            except Exception as e:
                logger.warning(f"⚠️ GCP STT fallo: {e}")

    try:
        from infrastructure.services.video_frame_extractor import VideoFrameExtractor
        frame_extractor = VideoFrameExtractor()
    except Exception as e:
        logger.error(f"⚠️ Frame Extractor fallo: {e}")
        frame_extractor = None

    # ---- Repositorios (Postgres/SQLite local o Firestore legacy) ----
    if is_local and db_backend in ("postgres", "sqlite"):
        try:
            from infrastructure.repositories.sqlalchemy_repositories import SQLAlchemyUserRepository, SQLAlchemyVideoRepository
            usuario_repository = SQLAlchemyUserRepository()
            video_repository = SQLAlchemyVideoRepository()
            logger.info(f"✅ Repos SQLAlchemy ({db_backend}) activos")
        except Exception as e:
            logger.error(f"❌ SQLAlchemy repos fallo, fallback memory: {e}")
            from infrastructure.repositories.user_repository import UsuarioRepositoryMemory
            from infrastructure.repositories.video_repository import VideoRepositoryFirestore
            usuario_repository = UsuarioRepositoryMemory()
            video_repository = VideoRepositoryFirestore()
    else:
        from infrastructure.repositories.user_repository import UsuarioRepositoryMemory
        from infrastructure.repositories.video_repository import VideoRepositoryFirestore
        usuario_repository = UsuarioRepositoryMemory()
        video_repository = VideoRepositoryFirestore()

    # Caso de uso pre-configurado v4.0
    from use_cases.video_processor import ProcesarVideoUseCase
    video_processor = ProcesarVideoUseCase(
        storage_adapter=gcp_storage,
        firestore_adapter=gcp_firestore,
        gemini_adapter=gemini_adapter,
        speech_adapter=speech_adapter,
        frame_extractor=frame_extractor,
        video_intelligence_adapter=None,
    )

    # Registrar en app.extensions (compat keys)
    app.extensions["gcp_config"] = gcp_config
    app.extensions["app_config"] = app_config
    app.extensions["gcp_storage"] = gcp_storage
    app.extensions["storage_adapter"] = gcp_storage
    app.extensions["gcp_firestore"] = gcp_firestore
    app.extensions["db_adapter"] = gcp_firestore
    app.extensions["cloud_tasks"] = cloud_tasks
    app.extensions["video_intelligence"] = video_intelligence
    app.extensions["ai_service"] = ai_service
    app.extensions["gemini_adapter"] = gemini_adapter
    app.extensions["speech_adapter"] = speech_adapter
    app.extensions["frame_extractor"] = frame_extractor
    app.extensions["usuario_repository"] = usuario_repository
    app.extensions["video_repository"] = video_repository
    app.extensions["video_processor"] = video_processor

    # Log de estado
    import logging

    logger = logging.getLogger(__name__)
    logger.info("✅ Dependencias GCP inicializadas (Pipeline v4.0):")
    logger.info(
        f"   • Cloud Storage: {'✅' if gcp_storage and gcp_storage.is_available() else '❌'}"
    )
    logger.info(
        f"   • Firestore: {'✅' if gcp_firestore and gcp_firestore.is_available() else '❌'}"
    )
    logger.info(
        f"   • Cloud Tasks: {'✅' if cloud_tasks and cloud_tasks.disponible else '❌'}"
    )
    logger.info("   • Video Intelligence: ⏭️  ELIMINADO (Gemini Vision v4.0)")
    logger.info(
        f"   • Gemini Vision: {'✅' if gemini_adapter and gemini_adapter.is_available() else '❌ (Deshabilitado/Error)'}"
    )
    logger.info(
        f"   • Speech-to-Text: {'✅' if speech_adapter and speech_adapter.is_available() else '❌ (Deshabilitado/Error)'}"
    )
    logger.info(
        f"   • Frame Extractor: {'✅' if frame_extractor and frame_extractor.is_available() else '❌ (Deshabilitado/Error)'}"
    )

    return {
        "gcp_config": gcp_config,
        "gcp_storage": gcp_storage,
        "gcp_firestore": gcp_firestore,
        "cloud_tasks": cloud_tasks,
        "video_intelligence": video_intelligence,
        "ai_service": ai_service,
        "gemini_adapter": gemini_adapter,
        "speech_adapter": speech_adapter,
        "frame_extractor": frame_extractor,
        "usuario_repository": usuario_repository,
        "video_repository": video_repository,
        "video_processor": video_processor,
    }
