"""
Dependencias para Workers (RQ) - TIVIT Video
Inicializa repositorios y servicios sin depender del contexto de Flask u HTTP.
Stack 100% local: Postgres/SQLite + MinIO/Filesystem + vLLM 32B + Whisper.
"""

import logging
from config.app_config import AppConfig
from infrastructure.repositories.sqlalchemy_repositories import SQLAlchemyUserRepository, SQLAlchemyVideoRepository
from infrastructure.adapters.minio_storage_adapter import MinioStorageAdapter
from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
from infrastructure.adapters.ai_gateway import get_ai_gateway
from infrastructure.adapters.whisper_adapter import WhisperAdapter
from infrastructure.services.video_frame_extractor import VideoFrameExtractor
from use_cases.video_processor import ProcesarVideoUseCase

logger = logging.getLogger(__name__)

class WorkerContainer:
    """Contenedor de dependencias singleton para el worker (stack local)."""
    _instance = None

    def __init__(self):
        logger.info("Inicializando contenedor de dependencias del Worker (local-first)...")
        self.app_config = AppConfig()

        # Storage: MinIO o Filesystem según AppConfig
        try:
            backend = getattr(AppConfig, "STORAGE_BACKEND", "filesystem")
            if backend == "minio":
                self.storage_adapter = MinioStorageAdapter(self.app_config)
            else:
                self.storage_adapter = FilesystemStorageAdapter()
        except Exception as e:
            logger.error(f"Error inicializando storage en worker: {e}")
            self.storage_adapter = None

        # Repositorios SQLAlchemy (Postgres/SQLite)
        try:
            self.video_repository = SQLAlchemyVideoRepository()
            self.user_repository = SQLAlchemyUserRepository()
        except Exception as e:
            logger.error(f"Error inicializando repositorios SQLAlchemy en worker: {e}")
            self.video_repository = None
            self.user_repository = None

        # Database availability shim for the video processor.
        try:
            from infrastructure.db.session import engine
            from sqlalchemy import text
            with engine.connect() as c:
                c.execute(text("SELECT 1"))

            class _LocalDB:
                def is_available(self):
                    return True
                def save_video(self, video):
                    if self.video_repo:
                        try:
                            return bool(self.video_repo.guardar(video))
                        except Exception:
                            return False
                    return False

            db_shim = _LocalDB()
            db_shim.video_repo = self.video_repository
            self.database_adapter = db_shim
        except Exception as e:
            logger.error(f"Error inicializando BD en worker: {e}")
            self.database_adapter = None

        # IA: Gateway local 32B (vLLM) / ApiLLM
        try:
            self.ai_service = get_ai_gateway()
            self.ai_adapter = self.ai_service
        except Exception as e:
            logger.error(f"Error inicializando AI Gateway en worker: {e}")
            self.ai_service = None
            self.ai_adapter = None

        # Speech: Whisper local
        try:
            self.speech_adapter = WhisperAdapter()
        except Exception as e:
            logger.error(f"Error inicializando Whisper en worker: {e}")
            self.speech_adapter = None

        try:
            self.frame_extractor = VideoFrameExtractor()
        except Exception as e:
            logger.error(f"Error inicializando Frame Extractor en worker: {e}")
            self.frame_extractor = None

        self.video_processor = ProcesarVideoUseCase(
            storage_adapter=self.storage_adapter,
            firestore_adapter=self.database_adapter,
            gemini_adapter=self.ai_adapter,
            speech_adapter=self.speech_adapter,
            frame_extractor=self.frame_extractor,
            video_intelligence_adapter=None,
        )
        logger.info("✅ Dependencias de Worker inicializadas correctamente (local-first).")

def get_worker_container() -> WorkerContainer:
    """Obtiene la instancia única del contenedor de dependencias para el worker"""
    if WorkerContainer._instance is None:
        WorkerContainer._instance = WorkerContainer()
    return WorkerContainer._instance
