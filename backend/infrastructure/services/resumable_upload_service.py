"""
Servicio de Upload Resumable para almacenamiento local
Permite subir archivos grandes (12h de video = 20-50GB) de forma eficiente y resiliente
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class ResumableUploadService:
    """
    Servicio para generar URLs de upload de archivos grandes
    """

    def __init__(self, config=None):
        self._storage = None
        self._is_minio = False
        self._init_storage()

    def _init_storage(self):
        try:
            from config.app_config import AppConfig
            backend = getattr(AppConfig, "STORAGE_BACKEND", "filesystem")
            if backend == "minio":
                from infrastructure.adapters.minio_storage_adapter import MinioStorageAdapter
                self._storage = MinioStorageAdapter(AppConfig)
                self._is_minio = True
            else:
                from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
                self._storage = FilesystemStorageAdapter()
            logger.info("ResumableUploadService inicializado")
        except Exception as e:
            logger.error(f"Error inicializando Storage: {e}")

    def is_available(self) -> bool:
        return self._storage is not None and self._storage.is_available()

    def generar_resumable_upload_url(
        self,
        filename: str,
        content_type: str = "video/mp4",
        metadata: Optional[Dict[str, str]] = None,
        expiration_hours: int = 24,
    ) -> Optional[Dict[str, Any]]:
        if not self.is_available():
            logger.error("ResumableUploadService no está disponible")
            return None

        try:
            safe_filename = self._sanitize_filename(filename)
            from datetime import datetime
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            blob_name = f"uploads/{timestamp}_{safe_filename}"
            bucket_name = getattr(self._storage, "bucket", "cu002-videos")

            if self._is_minio:
                c = self._storage._get_client()
                url = c.generate_presigned_url(
                    ClientMethod="put_object",
                    Params={"Bucket": bucket_name, "Key": blob_name, "ContentType": content_type},
                    ExpiresIn=3600,
                )
            else:
                url = ""

            logger.info(f"Upload URL generada: {blob_name}")

            return {
                "upload_url": url,
                "storage_path": f"s3://{bucket_name}/{blob_name}",
                "blob_name": blob_name,
                "storage_bucket": bucket_name,
                "expiration_hours": expiration_hours,
                "content_type": content_type,
            }

        except Exception as e:
            logger.error(f"Error generando upload URL: {e}")
            return None

    def generar_signed_upload_url(
        self,
        filename: str,
        content_type: str = "video/mp4",
        expiration_minutes: int = 60,
    ) -> Optional[str]:
        if not self.is_available():
            return None

        try:
            safe_filename = self._sanitize_filename(filename)
            from datetime import datetime
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            blob_name = f"uploads/{timestamp}_{safe_filename}"

            if self._is_minio:
                return self._storage.generate_signed_url(blob_name, expiration_minutes)
            else:
                return f"/socio/media/{Path(safe_filename).stem}"

        except Exception as e:
            logger.error(f"Error generando signed URL: {e}")
            return None

    def verificar_upload_completo(self, storage_path: str) -> bool:
        if not self.is_available():
            return False

        try:
            blob_name = self._parse_blob_name(storage_path)
            if not blob_name:
                return False

            if self._is_minio:
                try:
                    self._storage._get_client().head_object(
                        Bucket=self._storage.bucket, Key=blob_name
                    )
                    return True
                except Exception:
                    return False
            else:
                return (Path(self._storage.base_dir) / blob_name).exists()

        except Exception as e:
            logger.error(f"Error verificando upload: {e}")
            return False

    def subir_archivo_directo(
        self,
        file_stream,
        storage_path: str,
        content_type: str = "video/mp4",
        chunk_size: int = 8 * 1024 * 1024,
        timeout_seconds: int = 1200,
    ) -> int:
        if not self.is_available():
            raise Exception("ResumableUploadService no está disponible")

        import time
        import tempfile
        import os

        start_time = time.time()

        try:
            blob_name = self._parse_blob_name(storage_path)
            if not blob_name:
                raise ValueError(f"Path inválido: {storage_path}")

            logger.info(f"Iniciando upload directo: {blob_name}")

            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_path = tmp.name
                while True:
                    data = file_stream.read(chunk_size)
                    if not data:
                        break
                    tmp.write(data)

            file_size = os.path.getsize(tmp_path)

            if self._is_minio:
                c = self._storage._get_client()
                c.upload_file(
                    tmp_path, self._storage.bucket, blob_name,
                    ExtraArgs={"ContentType": content_type},
                )
            else:
                import shutil as _shutil
                dest = Path(self._storage.base_dir) / blob_name
                dest.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(tmp_path, str(dest))

            elapsed_total = time.time() - start_time
            mb_total = file_size / (1024 * 1024)
            avg_speed = mb_total / elapsed_total if elapsed_total > 0 else 0

            logger.info(
                f"UPLOAD COMPLETADO: {mb_total:.1f} MB en {elapsed_total:.1f}s "
                f"(promedio: {avg_speed:.2f} MB/s)"
            )

            try:
                os.unlink(tmp_path)
            except Exception:
                pass

            return file_size

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Error subiendo archivo después de {elapsed:.1f}s: {e}")
            raise

    def obtener_metadata_archivo(self, storage_path: str) -> Optional[Dict[str, Any]]:
        if not self.is_available():
            return None

        try:
            blob_name = self._parse_blob_name(storage_path)
            if not blob_name:
                return None

            if self._is_minio:
                try:
                    r = self._storage._get_client().head_object(
                        Bucket=self._storage.bucket, Key=blob_name
                    )
                    return {
                        "size": r.get("ContentLength"),
                        "size_mb": round(r.get("ContentLength", 0) / (1024 * 1024), 2),
                        "size_gb": round(r.get("ContentLength", 0) / (1024 * 1024 * 1024), 2),
                        "content_type": r.get("ContentType"),
                        "metadata": r.get("Metadata", {}),
                    }
                except Exception:
                    return None
            else:
                p = Path(self._storage.base_dir) / blob_name
                if not p.exists():
                    return None
                size = p.stat().st_size
                return {
                    "size": size,
                    "size_mb": round(size / (1024 * 1024), 2),
                    "size_gb": round(size / (1024 * 1024 * 1024), 2),
                    "metadata": {},
                }

        except Exception as e:
            logger.error(f"Error obteniendo metadata: {e}")
            return None

    def eliminar_archivo(self, storage_path: str) -> bool:
        if not self.is_available():
            return False

        try:
            blob_name = self._parse_blob_name(storage_path)
            if not blob_name:
                return False

            return self._storage.delete_file(blob_name)

        except Exception as e:
            logger.error(f"Error eliminando archivo: {e}")
            return False

    def _sanitize_filename(self, filename: str) -> str:
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
        safe_name = safe_name.replace(" ", "_")
        if len(safe_name) > 200:
            path = Path(safe_name)
            stem = path.stem[:190]
            suffix = path.suffix
            safe_name = f"{stem}{suffix}"
        return safe_name

    def _parse_blob_name(self, storage_path: str) -> Optional[str]:
        if not storage_path:
            return None
        if "://" in storage_path:
            parts = storage_path.split("://", 1)[1]
            if "/" in parts:
                return parts.split("/", 1)[1]
        return storage_path

    def configurar_lifecycle_policy(self, dias_retencion: int = 7) -> bool:
        logger.info("Lifecycle policy no aplicable para almacenamiento local")
        return False
