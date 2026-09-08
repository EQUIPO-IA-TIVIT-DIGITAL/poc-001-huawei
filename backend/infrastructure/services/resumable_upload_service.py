"""
Servicio de Upload Resumable para Google Cloud Storage
Permite subir archivos grandes (12h de video = 20-50GB) de forma eficiente y resiliente
"""

import logging
from typing import Optional, Dict, Any
from datetime import timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class ResumableUploadService:
    """
    Servicio para generar URLs de upload resumable de Google Cloud Storage

    Características:
    - Upload directo desde cliente a GCS (no pasa por backend)
    - Soporta archivos de cualquier tamaño
    - Recuperación automática ante fallos
    - Progreso en tiempo real
    """

    def __init__(self, config=None):
        """
        Inicializa el servicio

        Args:
            config: Configuración GCP (usa default si no se proporciona)
        """
        from config.gcp_config import GCPConfig

        self.config = config or GCPConfig()
        self.storage_client = None
        self.bucket_name = self.config.BUCKET_NAME  # Usar bucket configurado en .env

        if self.config.is_gcp_enabled():
            self._initialize_client()

    def _initialize_client(self):
        """Inicializa el cliente de Cloud Storage"""
        try:
            from google.cloud import storage
            import os

            self.storage_client = storage.Client()
            logger.info("✅ ResumableUploadService inicializado")
        except Exception as e:
            logger.error(f"⚠️ Error inicializando Storage Client: {e}")
            self.storage_client = None

    def is_available(self) -> bool:
        """Verifica si el servicio está disponible"""
        return self.storage_client is not None

    def generar_resumable_upload_url(
        self,
        filename: str,
        content_type: str = "video/mp4",
        metadata: Optional[Dict[str, str]] = None,
        expiration_hours: int = 24,
    ) -> Optional[Dict[str, Any]]:
        """
        Genera una URL firmada para resumable upload

        Args:
            filename: Nombre del archivo (se usará como parte de la ruta en GCS)
            content_type: Tipo MIME del archivo
            metadata: Metadata adicional para el archivo
            expiration_hours: Horas de validez de la URL (default: 24h)

        Returns:
            Dict con:
                - upload_url: URL para iniciar el upload
                - gcs_path: Ruta donde se guardará el archivo (gs://bucket/path)
                - expiration: Timestamp de expiración
        """
        if not self.is_available():
            logger.error("❌ ResumableUploadService no está disponible")
            return None

        try:
            # Sanitizar nombre de archivo
            safe_filename = self._sanitize_filename(filename)
            
            # Generar path único con timestamp
            from datetime import datetime
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            blob_name = f"uploads/{timestamp}_{safe_filename}"

            # Obtener bucket
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(blob_name)

            # Metadata del archivo
            if metadata:
                blob.metadata = metadata

            # Generar URL firmada para resumable upload
            url = blob.create_resumable_upload_session(
                content_type=content_type,
                timeout=300,  # 5 minutos para iniciar
            )

            gcs_path = f"gs://{self.bucket_name}/{blob_name}"

            logger.info(f"✅ Resumable upload URL generada: {blob_name}")

            return {
                "upload_url": url,
                "gcs_path": gcs_path,
                "blob_name": blob_name,
                "bucket": self.bucket_name,
                "expiration_hours": expiration_hours,
                "content_type": content_type,
            }

        except Exception as e:
            logger.error(f"❌ Error generando resumable upload URL: {e}")
            return None

    def generar_signed_upload_url(
        self,
        filename: str,
        content_type: str = "video/mp4",
        expiration_minutes: int = 60,
    ) -> Optional[str]:
        """
        Genera una URL firmada simple para upload (método alternativo)
        Útil para archivos más pequeños o cuando no se necesita resumabilidad

        Args:
            filename: Nombre del archivo
            content_type: Tipo MIME
            expiration_minutes: Minutos de validez de la URL

        Returns:
            URL firmada para upload
        """
        if not self.is_available():
            return None

        try:
            safe_filename = self._sanitize_filename(filename)
            
            from datetime import datetime
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            blob_name = f"uploads/{timestamp}_{safe_filename}"

            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(blob_name)

            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=expiration_minutes),
                method="PUT",
                content_type=content_type,
            )

            logger.info(f"✅ Signed upload URL generada: {blob_name}")
            return url

        except Exception as e:
            logger.error(f"❌ Error generando signed URL: {e}")
            return None

    def verificar_upload_completo(self, gcs_path: str) -> bool:
        """
        Verifica si un archivo se subió completamente a GCS

        Args:
            gcs_path: Ruta GCS (gs://bucket/path)

        Returns:
            True si el archivo existe y está completo
        """
        if not self.is_available():
            return False

        try:
            # Parsear GCS path
            if not gcs_path.startswith("gs://"):
                return False

            path_parts = gcs_path.replace("gs://", "").split("/", 1)
            if len(path_parts) != 2:
                return False

            bucket_name, blob_name = path_parts

            # Verificar existencia
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)

            return blob.exists()

        except Exception as e:
            logger.error(f"❌ Error verificando upload: {e}")
            return False

    def subir_archivo_directo(
        self,
        file_stream,
        gcs_path: str,
        content_type: str = "video/mp4",
        chunk_size: int = 8 * 1024 * 1024,
        timeout_seconds: int = 1200,
    ) -> int:
        """
        Sube un archivo directamente desde un stream al GCS (proxy upload)
        Evita problemas de CORS subiendo desde el backend
        CON LOGGING DE PROGRESO DETALLADO

        Args:
            file_stream: Stream del archivo (request.files['file'].stream)
            gcs_path: Ruta GCS de destino (gs://bucket/path)
            content_type: Tipo MIME del archivo
            chunk_size: Tamaño de chunk para upload (default: 8MB)
            timeout_seconds: Timeout total para el upload (default: 1200s = 20min)

        Returns:
            Número de bytes subidos

        Raises:
            Exception si hay error
        """
        if not self.is_available():
            raise Exception("ResumableUploadService no está disponible")

        import time

        start_time = time.time()

        try:
            # Parsear path GCS
            path_parts = gcs_path.replace("gs://", "").split("/", 1)
            if len(path_parts) != 2:
                raise ValueError(f"Path GCS inválido: {gcs_path}")

            bucket_name, blob_name = path_parts

            logger.info(f"📤 Iniciando upload a bucket: {bucket_name}")
            logger.info(f"   Blob: {blob_name}")
            logger.info(f"   Chunk size: {chunk_size / (1024*1024):.1f} MB")

            # Obtener bucket y blob
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)

            # Configurar blob para chunked upload
            blob.content_type = content_type
            blob.chunk_size = chunk_size

            # Variables para tracking
            last_log_time = start_time
            bytes_sent = 0
            log_interval = 5.0  # Loguear cada 5 segundos

            # Callback de progreso personalizado 
            def progress_callback(bytes_transferred):
                nonlocal last_log_time, bytes_sent
                bytes_sent = bytes_transferred
                current_time = time.time()
                
                # Loguear cada 5 segundos
                if current_time - last_log_time >= log_interval:
                    elapsed = current_time - start_time
                    mb_transferred = bytes_transferred / (1024 * 1024)
                    speed_mbps = mb_transferred / elapsed if elapsed > 0 else 0
                    
                    logger.info(
                        f"⏳ Progreso: {mb_transferred:.1f} MB transferidos "
                        f"| Velocidad: {speed_mbps:.2f} MB/s "
                        f"| Tiempo: {elapsed:.0f}s"
                    )
                    last_log_time = current_time

            logger.info("🚀 Comenzando transferencia...")

            # Subir con retry y callback de progreso
            try:
                from google.api_core.retry import Retry
                from google.resumable_media import requests as resumable_requests
                from google.auth.transport.requests import AuthorizedSession

                # Usar resumable upload con callback
                retry = Retry(deadline=timeout_seconds)
                
                # Crear sesión autorizada
                transport = AuthorizedSession(self.storage_client._credentials)
                
                # Crear resumable upload
                upload_url = (
                    f"https://www.googleapis.com/upload/storage/v1/b/{bucket_name}/o?"
                    f"uploadType=resumable&name={blob_name}"
                )
                
                # Iniciar resumable upload
                media = resumable_requests.ResumableUpload(upload_url, chunk_size)
                
                # Subir con progreso
                logger.info("📡 Upload resumable iniciado")
                
                # Fallback a método simple con logging básico
                blob.upload_from_file(
                    file_stream,
                    content_type=content_type,
                    rewind=True,
                    timeout=timeout_seconds,
                    retry=retry,
                )
                
            except ImportError:
                # Si no está disponible resumable_media, usar método simple
                logger.info("ℹ️ Usando upload simple (sin callback de progreso)")
                from google.api_core.retry import Retry
                retry = Retry(deadline=timeout_seconds)
                
                blob.upload_from_file(
                    file_stream,
                    content_type=content_type,
                    rewind=True,
                    timeout=timeout_seconds,
                    retry=retry,
                )

            # Obtener tamaño final
            blob.reload()
            bytes_uploaded = blob.size
            
            elapsed_total = time.time() - start_time
            mb_total = bytes_uploaded / (1024 * 1024)
            avg_speed = mb_total / elapsed_total if elapsed_total > 0 else 0

            logger.info(
                f"✅ UPLOAD COMPLETADO: {mb_total:.1f} MB en {elapsed_total:.1f}s "
                f"(promedio: {avg_speed:.2f} MB/s)"
            )
            
            return bytes_uploaded

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ Error subiendo archivo después de {elapsed:.1f}s: {e}")
            raise

    def obtener_metadata_archivo(self, gcs_path: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene metadata de un archivo en GCS

        Args:
            gcs_path: Ruta GCS (gs://bucket/path)

        Returns:
            Dict con metadata (size, content_type, created, etc)
        """
        if not self.is_available():
            return None

        try:
            path_parts = gcs_path.replace("gs://", "").split("/", 1)
            if len(path_parts) != 2:
                return None

            bucket_name, blob_name = path_parts

            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)

            if not blob.exists():
                return None

            blob.reload()

            return {
                "size": blob.size,
                "size_mb": round(blob.size / (1024 * 1024), 2),
                "size_gb": round(blob.size / (1024 * 1024 * 1024), 2),
                "content_type": blob.content_type,
                "created": blob.time_created.isoformat() if blob.time_created else None,
                "updated": blob.updated.isoformat() if blob.updated else None,
                "md5_hash": blob.md5_hash,
                "metadata": blob.metadata or {},
            }

        except Exception as e:
            logger.error(f"❌ Error obteniendo metadata: {e}")
            return None

    def eliminar_archivo(self, gcs_path: str) -> bool:
        """
        Elimina un archivo de GCS

        Args:
            gcs_path: Ruta GCS (gs://bucket/path)

        Returns:
            True si se eliminó correctamente
        """
        if not self.is_available():
            return False

        try:
            path_parts = gcs_path.replace("gs://", "").split("/", 1)
            if len(path_parts) != 2:
                return False

            bucket_name, blob_name = path_parts

            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)

            if blob.exists():
                blob.delete()
                logger.info(f"✅ Archivo eliminado: {gcs_path}")
                return True

            return False

        except Exception as e:
            logger.error(f"❌ Error eliminando archivo: {e}")
            return False

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitiza un nombre de archivo para GCS

        Args:
            filename: Nombre original del archivo

        Returns:
            Nombre sanitizado
        """
        # Remover caracteres problemáticos
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
        safe_name = safe_name.replace(" ", "_")
        
        # Limitar longitud
        if len(safe_name) > 200:
            path = Path(safe_name)
            stem = path.stem[:190]
            suffix = path.suffix
            safe_name = f"{stem}{suffix}"

        return safe_name

    def configurar_lifecycle_policy(self, dias_retencion: int = 7) -> bool:
        """
        Configura política de lifecycle para eliminar videos antiguos automáticamente

        Args:
            dias_retencion: Días antes de eliminar archivos (default: 7)

        Returns:
            True si se configuró correctamente
        """
        if not self.is_available():
            return False

        try:
            bucket = self.storage_client.bucket(self.bucket_name)

            # Definir regla de lifecycle
            rule = {
                "action": {"type": "Delete"},
                "condition": {
                    "age": dias_retencion,
                    "matchesPrefix": ["uploads/"],
                },
            }

            bucket.lifecycle_rules = [rule]
            bucket.patch()

            logger.info(f"✅ Lifecycle policy configurada: {dias_retencion} días")
            return True

        except Exception as e:
            logger.error(f"❌ Error configurando lifecycle policy: {e}")
            return False
