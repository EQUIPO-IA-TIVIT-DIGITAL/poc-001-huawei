"""
Dependencias para Workers (RQ) - TIVIT Video
Inicializa repositorios y servicios sin depender del contexto de Flask u HTTP.
"""

import logging
from config.gcp_config import GCPConfig
from infrastructure.repositories.video_repository import VideoRepositoryFirestore
from infrastructure.adapters.gcp_storage import CloudStorageAdapter
from infrastructure.adapters.gcp_firestore import FirestoreAdapter
from infrastructure.adapters.ai_service import AIService
from infrastructure.adapters.gemini_adapter import GeminiAdapter
from infrastructure.adapters.gcp_speech import GCPSpeechAdapter
from infrastructure.services.video_frame_extractor import VideoFrameExtractor
from use_cases.video_processor import ProcesarVideoUseCase

logger = logging.getLogger(__name__)

class WorkerContainer:
    """Contenedor de dependencias singleton para el worker"""
    _instance = None
    
    def __init__(self):
        logger.info("Inicializando contenedor de dependencias del Worker...")
        self.gcp_config = GCPConfig()
        
        try:
            self.storage_adapter = CloudStorageAdapter(self.gcp_config)
        except Exception as e:
            logger.error(f"Error inicializando Cloud Storage en worker: {e}")
            self.storage_adapter = None
            
        try:
            self.firestore_adapter = FirestoreAdapter(self.gcp_config)
        except Exception as e:
            logger.error(f"Error inicializando Firestore en worker: {e}")
            self.firestore_adapter = None
            
        self.ai_service = AIService()
        
        try:
            self.gemini_adapter = GeminiAdapter()
        except Exception as e:
            logger.error(f"Error inicializando Gemini en worker: {e}")
            self.gemini_adapter = None
            
        try:
            self.speech_adapter = GCPSpeechAdapter(self.gcp_config)
        except Exception as e:
            logger.error(f"Error inicializando Speech-to-Text en worker: {e}")
            self.speech_adapter = None
            
        try:
            self.frame_extractor = VideoFrameExtractor()
        except Exception as e:
            logger.error(f"Error inicializando Frame Extractor en worker: {e}")
            self.frame_extractor = None
            
        self.video_repository = VideoRepositoryFirestore()
        
        self.video_processor = ProcesarVideoUseCase(
            storage_adapter=self.storage_adapter,
            firestore_adapter=self.firestore_adapter,
            gemini_adapter=self.gemini_adapter,
            speech_adapter=self.speech_adapter,
            frame_extractor=self.frame_extractor,
            video_intelligence_adapter=None,  # DEPRECATED v4.0
        )
        logger.info("✅ Dependencias de Worker inicializadas correctamente.")

def get_worker_container() -> WorkerContainer:
    """Obtiene la instancia única del contenedor de dependencias para el worker"""
    if WorkerContainer._instance is None:
        WorkerContainer._instance = WorkerContainer()
    return WorkerContainer._instance
