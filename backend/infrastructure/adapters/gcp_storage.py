"""
Adaptador de Cloud Storage para AccessFan
Maneja la subida, descarga y gestión de videos en Google Cloud Storage
"""
import os
from datetime import timedelta, datetime
from pathlib import Path
from typing import Optional, BinaryIO
from google.cloud import storage
from google.cloud.exceptions import NotFound, GoogleCloudError
from google.auth import default, compute_engine
from google.auth.transport import requests
import google.auth

import logging
from config.gcp_config import GCPConfig


logger = logging.getLogger(__name__)

class CloudStorageAdapter:
    """
    Adaptador para Google Cloud Storage
    
    Proporciona métodos para:
    - Subir videos y archivos
    - Generar URLs firmadas
    - Eliminar archivos
    - Gestionar metadatos
    """
    
    def __init__(self, config: GCPConfig = None):
        """
        Inicializa el adaptador de Cloud Storage
        
        Args:
            config: Configuración GCP (usa default si no se proporciona)
        """
        self.config = config or GCPConfig()
        self.client = None
        self.bucket = None
        
        # Inicializar cliente si GCP está habilitado
        if self.config.is_gcp_enabled():
            self._initialize_client()
    
    def _initialize_client(self):
        """Inicializa el cliente de Cloud Storage"""
        try:
            
            self.client = storage.Client(project=self.config.PROJECT_ID)
            self.bucket = self.client.bucket(self.config.BUCKET_NAME)
            
            logger.info(f"Cloud Storage inicializado: {self.config.BUCKET_NAME}")
        except Exception as e:
            logger.warning(f"Error inicializando Cloud Storage: {e}")
            self.client = None
            self.bucket = None
    
    def is_available(self) -> bool:
        """
        Verifica si Cloud Storage está disponible
        
        Returns:
            bool: True si está disponible
        """
        return self.client is not None and self.bucket is not None
    
    def upload_video(
        self, 
        file_path: str | Path, 
        video_id: str,
        content_type: str = 'video/mp4',
        metadata: dict = None
    ) -> Optional[str]:
        """
        Sube un video a Cloud Storage
        
        Args:
            file_path: Ruta local del archivo
            video_id: ID único del video
            content_type: Tipo MIME del video
            metadata: Metadatos adicionales
            
        Returns:
            str: URL pública del video o None si falla
        """
        if not self.is_available():
            logger.warning(" Cloud Storage no está disponible")
            return None
        
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"Archivo no encontrado: {file_path}")
            
            # Obtener extensión del archivo
            extension = file_path.suffix.lstrip('.')
            blob_name = self.config.get_video_path(video_id, extension)
            
            # Crear blob
            blob = self.bucket.blob(blob_name)
            
            # Configurar metadatos
            if metadata:
                blob.metadata = metadata
            
            # Subir archivo
            blob.upload_from_filename(
                str(file_path),
                content_type=content_type
            )
            
            logger.info(f"Video subido: {blob_name}")
            
            # Retornar URL pública (gs://)
            return f"gs://{self.config.BUCKET_NAME}/{blob_name}"
            
        except Exception as e:
            logger.error(f"Error subiendo video: {e}")
            return None
    
    def upload_from_stream(
        self,
        file_stream: BinaryIO,
        video_id: str,
        content_type: str = 'video/mp4',
        metadata: dict = None
    ) -> Optional[str]:
        """
        Sube un video desde un stream (útil para Flask uploads)
        
        Args:
            file_stream: Stream del archivo
            video_id: ID único del video
            content_type: Tipo MIME del video
            metadata: Metadatos adicionales
            
        Returns:
            str: URL pública del video o None si falla
        """
        if not self.is_available():
            return None
        
        try:
            # Inferir extensión del content_type
            extension = content_type.split('/')[-1]
            if extension == 'quicktime':
                extension = 'mov'
            
            blob_name = self.config.get_video_path(video_id, extension)
            blob = self.bucket.blob(blob_name)
            
            if metadata:
                blob.metadata = metadata
            
            # Subir desde stream
            file_stream.seek(0)  # Asegurar que estamos al inicio
            blob.upload_from_file(file_stream, content_type=content_type)
            
            logger.info(f"Video subido desde stream: {blob_name}")
            
            return f"gs://{self.config.BUCKET_NAME}/{blob_name}"
            
        except Exception as e:
            logger.error(f"Error subiendo desde stream: {e}")
            return None
    
    def upload_from_bytes(
        self,
        data: bytes,
        blob_path: str,
        content_type: str = 'image/jpeg',
        metadata: dict = None
    ) -> Optional[str]:
        """
        Sube datos binarios a Cloud Storage
        
        Args:
            data: Datos binarios a subir
            blob_path: Ruta completa del blob en GCS
            content_type: Tipo MIME del archivo
            metadata: Metadatos adicionales
            
        Returns:
            str: URL pública del archivo o None si falla
        """
        if not self.is_available():
            return None
        
        try:
            blob = self.bucket.blob(blob_path)
            
            if metadata:
                blob.metadata = metadata
            
            # Subir desde bytes
            blob.upload_from_string(data, content_type=content_type)
            
            logger.info(f"Archivo subido desde bytes: {blob_path}")
            
            # Retornar URI gs:// (usar generate_signed_url_from_gcs_uri para obtener URL pública)
            return f"gs://{self.config.BUCKET_NAME}/{blob_path}"
            
        except Exception as e:
            logger.error(f"Error subiendo desde bytes: {e}")
            return None
    
    def generate_signed_url_from_gcs_uri(
        self,
        gcs_uri: str,
        expiration_minutes: int = 60
    ) -> Optional[str]:
        """
        Genera una URL firmada a partir de una URI gs://
        
        Args:
            gcs_uri: URI gs://bucket/path/to/file
            expiration_minutes: Minutos de validez
            
        Returns:
            str: URL firmada o None si falla
        """
        if not self.is_available() or not gcs_uri:
            return None
        
        try:
            # Extraer blob_path de gs://bucket/path
            if gcs_uri.startswith("gs://"):
                parts = gcs_uri[5:].split("/", 1)
                blob_path = parts[1] if len(parts) > 1 else parts[0]
            else:
                blob_path = gcs_uri
            
            return self.generate_signed_url(blob_path, expiration_minutes=expiration_minutes)
        except Exception as e:
            logger.error(f"Error generando URL firmada desde URI: {e}")
            return None
    
    def generate_signed_url(
        self, 
        blob_name: str, 
        expiration_minutes: int = None
    ) -> Optional[str]:
        """
        Genera una URL firmada para acceso temporal
        Compatible con ADC (sin private key) usando IAM Credentials API
        
        Args:
            blob_name: Nombre del blob en GCS
            expiration_minutes: Minutos de validez (default: configuración)
            
        Returns:
            str: URL firmada o None si falla
        """
        if not self.is_available():
            return None
        
        try:
            blob = self.bucket.blob(blob_name)
            
            expiration = expiration_minutes or self.config.SIGNED_URL_EXPIRATION_MINUTES
            
            # Intentar generar signed URL normalmente
            try:
                url = blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(minutes=expiration),
                    method="GET"
                )
                return url
            except Exception as sign_error:
                # Si falla por falta de private key, usar IAM Credentials API
                if "private key" in str(sign_error).lower():
                    logger.info("Generando signed URL con IAM Credentials API (ADC sin private key)")
                    
                    # Obtener credenciales actuales
                    credentials, project = google.auth.default()
                    
                    # Obtener service account email
                    if hasattr(credentials, 'service_account_email'):
                        service_account_email = credentials.service_account_email
                    else:
                        # Para ADC, usar la default compute service account
                        service_account_email = f"{self.config.PROJECT_ID}@appspot.gserviceaccount.com"
                    
                    # Generar signed URL usando IAM
                    url = blob.generate_signed_url(
                        version="v4",
                        expiration=timedelta(minutes=expiration),
                        method="GET",
                        service_account_email=service_account_email,
                        access_token=credentials.token
                    )
                    
                    return url
                else:
                    raise sign_error
            
        except Exception as e:
            logger.error(f"Error generando URL firmada: {e}")
            return None
    
    def delete_video(self, video_id: str, extension: str = 'mp4') -> bool:
        """
        Elimina un video de Cloud Storage
        
        Args:
            video_id: ID del video
            extension: Extensión del archivo
            
        Returns:
            bool: True si se eliminó correctamente
        """
        if not self.is_available():
            return False
        
        try:
            blob_name = self.config.get_video_path(video_id, extension)
            blob = self.bucket.blob(blob_name)
            blob.delete()
            
            logger.info(f"Video eliminado: {blob_name}")
            return True
            
        except NotFound:
            logger.warning(f"Video no encontrado: {video_id}")
            return False
        except Exception as e:
            logger.error(f"Error eliminando video: {e}")
            return False
    
    def video_exists(self, video_id: str, extension: str = 'mp4') -> bool:
        """
        Verifica si un video existe en Cloud Storage
        
        Args:
            video_id: ID del video
            extension: Extensión del archivo
            
        Returns:
            bool: True si existe
        """
        if not self.is_available():
            return False
        
        try:
            blob_name = self.config.get_video_path(video_id, extension)
            blob = self.bucket.blob(blob_name)
            return blob.exists()
        except Exception as e:
            logger.error(f"Error verificando existencia: {e}")
            return False
    
    def get_video_metadata(self, video_id: str, extension: str = 'mp4') -> Optional[dict]:
        """
        Obtiene los metadatos de un video
        
        Args:
            video_id: ID del video
            extension: Extensión del archivo
            
        Returns:
            dict: Metadatos del video o None
        """
        if not self.is_available():
            return None
        
        try:
            blob_name = self.config.get_video_path(video_id, extension)
            blob = self.bucket.blob(blob_name)
            blob.reload()  # Cargar metadatos desde GCS
            
            return {
                'name': blob.name,
                'size': blob.size,
                'content_type': blob.content_type,
                'created': blob.time_created,
                'updated': blob.updated,
                'metadata': blob.metadata or {}
            }
        except Exception as e:
            logger.error(f"Error obteniendo metadatos: {e}")
            return None
    
    def list_videos(self, prefix: str = None) -> list[str]:
        """
        Lista todos los videos en el bucket
        
        Args:
            prefix: Prefijo para filtrar (opcional)
            
        Returns:
            list: Lista de nombres de archivos
        """
        if not self.is_available():
            return []
        
        try:
            blobs = self.client.list_blobs(
                self.config.BUCKET_NAME,
                prefix=prefix or self.config.BUCKET_VIDEOS_FOLDER
            )
            return [blob.name for blob in blobs]
        except Exception as e:
            logger.error(f"Error listando videos: {e}")
            return []
    
    def get_storage_stats(self) -> dict:
        """
        Obtiene estadísticas del bucket
        
        Returns:
            dict: Estadísticas de almacenamiento
        """
        if not self.is_available():
            return {'available': False}
        
        try:
            blobs = list(self.bucket.list_blobs())
            total_size = sum(blob.size for blob in blobs if blob.size)
            
            return {
                'available': True,
                'bucket_name': self.config.BUCKET_NAME,
                'total_files': len(blobs),
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2)
            }
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {'available': False, 'error': str(e)}
    
    def upload_file(
        self,
        local_path: str,
        blob_name: str,
        content_type: str = None,
        return_signed_url: bool = False
    ) -> Optional[str]:
        """
        Sube un archivo local a una ruta específica en GCS
        
        Args:
            local_path: Ruta local del archivo
            blob_name: Ruta destino en el bucket (ej: temp_clips/abc.mp4)
            content_type: Tipo MIME (auto-detectado si no se proporciona)
            return_signed_url: Si True, retorna URL firmada (para acceso directo)
            
        Returns:
            str: URI gs:// o URL firmada del archivo subido, o None si falla
        """
        if not self.is_available():
            logger.warning(" Cloud Storage no está disponible")
            return None
        
        try:
            from pathlib import Path
            file_path = Path(local_path)
            if not file_path.exists():
                raise FileNotFoundError(f"Archivo no encontrado: {local_path}")
            
            if not content_type:
                import mimetypes
                content_type, _ = mimetypes.guess_type(str(file_path))
                content_type = content_type or 'application/octet-stream'
            
            blob = self.bucket.blob(blob_name)
            blob.upload_from_filename(str(file_path), content_type=content_type)
            
            if return_signed_url:
                # Generar URL firmada válida por 1 hora
                from datetime import timedelta
                url = blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(hours=1),
                    method="GET"
                )
                logger.info(f"Archivo subido con URL firmada: {blob_name}")
                return url
            
            gcs_uri = f"gs://{self.config.BUCKET_NAME}/{blob_name}"
            logger.info(f"Archivo subido: {blob_name}")
            return gcs_uri
            
        except Exception as e:
            logger.error(f"Error subiendo archivo: {e}")
            return None
    
    def delete_file(self, blob_name: str) -> bool:
        """
        Elimina un archivo por su ruta en el bucket
        
        Args:
            blob_name: Ruta del archivo en el bucket
            
        Returns:
            bool: True si se eliminó correctamente
        """
        if not self.is_available():
            return False
        
        try:
            blob = self.bucket.blob(blob_name)
            blob.delete()
            return True
        except NotFound:
            return False
        except Exception as e:
            logger.error(f"Error eliminando archivo: {e}")
            return False

    def get_gcs_uri(self, gcs_path: str) -> str:
        """
        Convierte una ruta de Cloud Storage a URI completa gs://
        
        Args:
            gcs_path: Ruta en el bucket (ej: videos/abc123.mp4)
            
        Returns:
            str: URI completa (ej: gs://bucket-name/videos/abc123.mp4)
        """
        # Si ya es una URI gs://, retornarla
        if gcs_path.startswith('gs://'):
            return gcs_path
        
        # Construir URI completa
        return f"gs://{self.config.BUCKET_NAME}/{gcs_path}"
    
    def download_video(
        self,
        video_id: str,
        destination_path: str,
        extension: str = 'mp4'
    ) -> Optional[str]:
        """
        Descarga un video desde Cloud Storage al sistema local
        
        Args:
            video_id: ID del video
            destination_path: Ruta de destino local
            extension: Extensión del archivo
            
        Returns:
            str: Ruta local del archivo descargado o None si falla
        """
        if not self.is_available():
            return None
        
        try:
            blob_name = self.config.get_video_path(video_id, extension)
            blob = self.bucket.blob(blob_name)
            
            if not blob.exists():
                logger.warning(f"Video no encontrado en GCS: {blob_name}")
                return None
            
            # Descargar archivo
            blob.download_to_filename(destination_path)
            
            logger.info(f"Video descargado: {destination_path}")
            return destination_path
            
        except Exception as e:
            logger.error(f"Error descargando video: {e}")
            return None


# Alias para compatibilidad con código existente
GCPStorage = CloudStorageAdapter
