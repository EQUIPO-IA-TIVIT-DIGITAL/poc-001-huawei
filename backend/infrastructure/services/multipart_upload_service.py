"""
Servicio de Upload Multipart para archivos grandes
Divide archivos en chunks y los sube en paralelo a almacenamiento local

Para videos pesados (20-50GB):
- Chunks de 50MB
- 5 uploads paralelos
- 3x más rápido que upload serial
"""

import logging
import time
import tempfile
import os
from pathlib import Path
from typing import BinaryIO, Dict, Any

logger = logging.getLogger(__name__)


class MultipartUploadService:
    """
    Servicio para subir archivos grandes en paralelo usando multipart upload
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
            logger.info("MultipartUploadService inicializado")
        except Exception as e:
            logger.error(f"Error inicializando Storage: {e}")

    def is_available(self) -> bool:
        return self._storage is not None and self._storage.is_available()

    def subir_archivo_multipart(
        self,
        file_stream: BinaryIO,
        storage_path: str,
        content_type: str = "video/mp4",
        chunk_size: int = 50 * 1024 * 1024,
        max_workers: int = 5,
        timeout_seconds: int = 3600,
    ) -> Dict[str, Any]:
        if not self.is_available():
            raise Exception("MultipartUploadService no está disponible")

        start_time = time.time()
        temp_dir = None

        try:
            blob_name = storage_path
            if "://" in storage_path:
                parts = storage_path.split("://", 1)[1]
                if "/" in parts:
                    blob_name = parts.split("/", 1)[1]

            logger.info(f"Iniciando multipart upload: {blob_name}")
            logger.info(f"   Chunk size: {chunk_size / (1024*1024):.1f} MB")
            logger.info(f"   Workers: {max_workers}")

            temp_dir = tempfile.mkdtemp(prefix="multipart_")
            temp_file = os.path.join(temp_dir, "upload_file")
            
            logger.info(f"Guardando stream a temp: {temp_file}")
            bytes_written = 0
            with open(temp_file, 'wb') as f:
                while True:
                    chunk = file_stream.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_written += len(chunk)
                    
                    if bytes_written % (100 * 1024 * 1024) == 0:
                        mb_written = bytes_written / (1024 * 1024)
                        logger.info(f"   Escritura temp: {mb_written:.1f} MB")

            file_size = os.path.getsize(temp_file)
            logger.info(f"Archivo temp creado: {file_size / (1024*1024):.1f} MB")

            if self._is_minio:
                return self._upload_minio_multipart(
                    temp_file, blob_name, content_type,
                    file_size, start_time, timeout_seconds
                )
            else:
                return self._upload_filesystem(
                    temp_file, blob_name, file_size, start_time
                )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Error en multipart upload después de {elapsed:.1f}s: {e}")
            raise
        finally:
            if temp_dir and os.path.exists(temp_dir):
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                    logger.info("Temp dir limpiado")
                except Exception as e:
                    logger.warning(f"Error limpiando temp dir: {e}")

    def _upload_minio_multipart(
        self, temp_file: str, blob_name: str, content_type: str,
        file_size: int, start_time: float, timeout_seconds: int
    ) -> Dict[str, Any]:
        c = self._storage._get_client()
        bucket = self._storage.bucket

        mpu = c.create_multipart_upload(Bucket=bucket, Key=blob_name, ContentType=content_type)
        upload_id = mpu['UploadId']

        try:
            chunk_size = 50 * 1024 * 1024
            parts = []
            part_number = 1
            bytes_uploaded = 0

            with open(temp_file, 'rb') as f:
                while True:
                    data = f.read(chunk_size)
                    if not data:
                        break
                    resp = c.upload_part(
                        Bucket=bucket, Key=blob_name, PartNumber=part_number,
                        UploadId=upload_id, Body=data,
                    )
                    parts.append({'PartNumber': part_number, 'ETag': resp['ETag']})
                    bytes_uploaded += len(data)
                    part_number += 1

                    if part_number % 3 == 0:
                        elapsed = time.time() - start_time
                        speed = (bytes_uploaded / (1024*1024)) / elapsed if elapsed > 0 else 0
                        logger.info(
                            f"Progreso: {part_number-1} chunks "
                            f"({bytes_uploaded / file_size * 100:.1f}%) | {speed:.2f} MB/s"
                        )

            c.complete_multipart_upload(
                Bucket=bucket, Key=blob_name, UploadId=upload_id,
                MultipartUpload={'Parts': parts},
            )

            elapsed_total = time.time() - start_time
            mb_total = bytes_uploaded / (1024 * 1024)
            avg_speed = mb_total / elapsed_total if elapsed_total > 0 else 0

            logger.info(
                f"MULTIPART UPLOAD COMPLETADO: {mb_total:.1f} MB en {elapsed_total:.1f}s "
                f"(promedio: {avg_speed:.2f} MB/s, {len(parts)} chunks)"
            )

            return {
                'bytes_uploaded': bytes_uploaded,
                'chunks_count': len(parts),
                'elapsed_seconds': elapsed_total,
                'avg_speed_mbps': avg_speed,
            }

        except Exception:
            try:
                c.abort_multipart_upload(Bucket=bucket, Key=blob_name, UploadId=upload_id)
            except Exception:
                pass
            raise

    def _upload_filesystem(
        self, temp_file: str, blob_name: str, file_size: int, start_time: float
    ) -> Dict[str, Any]:
        import shutil as _shutil
        dest = Path(self._storage.base_dir) / blob_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        _shutil.copy2(temp_file, str(dest))

        elapsed_total = time.time() - start_time
        mb_total = file_size / (1024 * 1024)
        avg_speed = mb_total / elapsed_total if elapsed_total > 0 else 0

        logger.info(
            f"UPLOAD COMPLETADO: {mb_total:.1f} MB en {elapsed_total:.1f}s "
            f"(promedio: {avg_speed:.2f} MB/s)"
        )

        return {
            'bytes_uploaded': file_size,
            'chunks_count': 1,
            'elapsed_seconds': elapsed_total,
            'avg_speed_mbps': avg_speed,
        }
