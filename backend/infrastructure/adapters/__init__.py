"""
Adaptadores para servicios de Google Cloud Platform
Sistema GCP-only: Sin fallbacks locales
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


# ============================================
# INTERFACES (Contratos)
# ============================================

class IStorageAdapter(ABC):
    """Interface para adaptador de almacenamiento (Cloud Storage)"""
    
    @abstractmethod
    def subir_archivo(self, archivo_local: str, destino: str) -> str:
        """Sube un archivo al almacenamiento"""
        pass
    
    @abstractmethod
    def descargar_archivo(self, origen: str, archivo_local: str) -> bool:
        """Descarga un archivo del almacenamiento"""
        pass
    
    @abstractmethod
    def eliminar_archivo(self, ruta: str) -> bool:
        """Elimina un archivo del almacenamiento"""
        pass
    
    @abstractmethod
    def obtener_url_firmada(self, ruta: str, expiracion_minutos: int = 60) -> str:
        """Genera una URL firmada temporal"""
        pass


class IVideoAnalyzerAdapter(ABC):
    """Interface para adaptador de análisis de video (Video Intelligence)"""
    
    @abstractmethod
    def analizar_contenido(self, video_uri: str) -> Dict[str, Any]:
        """Analiza el contenido de un video"""
        pass
    
    @abstractmethod
    def detectar_logos(self, video_uri: str) -> List[Dict[str, Any]]:
        """Detecta logos en el video"""
        pass
    
    @abstractmethod
    def detectar_contenido_explicito(self, video_uri: str) -> Dict[str, Any]:
        """Detecta contenido explícito/adulto"""
        pass
    
    @abstractmethod
    def detectar_violencia(self, video_uri: str) -> Dict[str, Any]:
        """Detecta contenido violento"""
        pass


class IDatabaseAdapter(ABC):
    """Interface para adaptador de base de datos (Firestore)"""
    
    @abstractmethod
    def guardar(self, coleccion: str, documento_id: str, datos: Dict[str, Any]) -> bool:
        """Guarda un documento en la base de datos"""
        pass
    
    @abstractmethod
    def obtener(self, coleccion: str, documento_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene un documento por ID"""
        pass
    
    @abstractmethod
    def listar(self, coleccion: str, filtros: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Lista documentos de una colección"""
        pass
    
    @abstractmethod
    def eliminar(self, coleccion: str, documento_id: str) -> bool:
        """Elimina un documento"""
        pass


class ITaskQueueAdapter(ABC):
    """Interface para adaptador de cola de tareas (Cloud Tasks)"""
    
    @abstractmethod
    def encolar_tarea(self, endpoint: str, payload: Dict[str, Any], delay_seconds: int = 0) -> Dict[str, Any]:
        """Encola una tarea para ejecución asíncrona"""
        pass
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Retorna el estado del servicio"""
        pass


# ============================================
# IMPORTAR ADAPTADORES — lazy para no exigir google-cloud-* si offline
# ============================================

def _lazy_import_gcp():
    from .ai_service import AIService
    from .gcp_firestore import FirestoreAdapter
    from .gcp_storage import CloudStorageAdapter
    from .gcp_video_intelligence import VideoIntelligenceAdapter
    from .cloud_tasks_adapter import CloudTasksAdapter
    from .gemini_adapter import GeminiAdapter
    return AIService, FirestoreAdapter, CloudStorageAdapter, VideoIntelligenceAdapter, CloudTasksAdapter, GeminiAdapter

try:
    AIService, FirestoreAdapter, CloudStorageAdapter, VideoIntelligenceAdapter, CloudTasksAdapter, GeminiAdapter = _lazy_import_gcp()
except Exception:
    # offline local: gcp adapters opcionales
    AIService = FirestoreAdapter = CloudStorageAdapter = VideoIntelligenceAdapter = CloudTasksAdapter = GeminiAdapter = None  # type: ignore


# ============================================
# FACTORY PARA CREAR ADAPTADORES GCP
# ============================================

class AdapterFactory:
    """
    Factory para crear adaptadores GCP
    Todos los adaptadores requieren configuración GCP válida
    """
    
    @staticmethod
    def create_storage_adapter():
        from config.gcp_config import GCPConfig
        _, _, CloudStorageAdapter, *_ = _lazy_import_gcp()
        return CloudStorageAdapter(GCPConfig())

    @staticmethod
    def create_video_analyzer():
        from config.gcp_config import GCPConfig
        _, _, _, VideoIntelligenceAdapter, *_ = _lazy_import_gcp()
        return VideoIntelligenceAdapter(GCPConfig())

    @staticmethod
    def create_firestore_adapter():
        from config.gcp_config import GCPConfig
        _, FirestoreAdapter, *_ = _lazy_import_gcp()
        return FirestoreAdapter(GCPConfig())

    @staticmethod
    def create_task_queue_adapter():
        _, _, _, _, CloudTasksAdapter, _ = _lazy_import_gcp()
        return CloudTasksAdapter()

    @staticmethod
    def create_ai_service():
        AIService, *_ = _lazy_import_gcp()
        return AIService()


# Exportaciones públicas
__all__ = [
    # Interfaces
    'IStorageAdapter',
    'IVideoAnalyzerAdapter', 
    'IDatabaseAdapter',
    'ITaskQueueAdapter',
    # Factory
    'AdapterFactory',
    # Adaptadores GCP
    'AIService',
    'get_ai_service',
    'FirestoreAdapter',
    'get_firestore_adapter',
    'CloudStorageAdapter',
    'get_storage_adapter',
    'VideoIntelligenceAdapter',
    'CloudTasksAdapter',
    'get_cloud_tasks_adapter',
    'GeminiAdapter',
    'get_gemini_adapter',
]
