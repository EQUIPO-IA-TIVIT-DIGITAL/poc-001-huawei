"""
Adaptadores de infraestructura - TIVIT Video
Stack 100% local: MinIO/filesystem (storage), PostgreSQL (db), Redis+RQ (cola).
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


# ============================================
# INTERFACES (Contratos)
# ============================================

class IStorageAdapter(ABC):
    """Interface para adaptador de almacenamiento"""

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
    """Interface para adaptador de análisis de video"""

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
    """Interface para adaptador de base de datos"""

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
    """Interface para adaptador de cola de tareas"""

    @abstractmethod
    def encolar_tarea(self, endpoint: str, payload: Dict[str, Any], delay_seconds: int = 0) -> Dict[str, Any]:
        """Encola una tarea para ejecución asíncrona"""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Retorna el estado del servicio"""
        pass


# Exportaciones públicas
__all__ = [
    'IStorageAdapter',
    'IVideoAnalyzerAdapter',
    'IDatabaseAdapter',
    'ITaskQueueAdapter',
]