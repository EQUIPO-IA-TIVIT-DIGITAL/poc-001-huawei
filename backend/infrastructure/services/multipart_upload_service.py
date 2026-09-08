"""
Servicio de Upload Multipart para archivos grandes
Divide archivos en chunks y los sube en paralelo a GCS

Para videos pesados (20-50GB):
- Chunks de 50MB
- 5 uploads paralelos
- 3x más rápido que upload serial
"""

import logging
import time
import tempfile
import os
from typing import Optional, Dict, Any, BinaryIO, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)


class MultipartUploadService:
    """
    Servicio para subir archivos grandes en paralelo usando multipart upload
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
        self.bucket_name = self.config.BUCKET_NAME

        if self.config.is_gcp_enabled():
            self._initialize_client()

    def _initialize_client(self):
        """Inicializa el cliente de Cloud Storage"""
        try:
            from google.cloud import storage
            import os

            self.storage_client = storage.Client()
            logger.info("✅ MultipartUploadService inicializado")
        except Exception as e:
            logger.error(f"⚠️ Error inicializando Storage Client: {e}")
            self.storage_client = None

    def is_available(self) -> bool:
        """Verifica si el servicio está disponible"""
        return self.storage_client is not None

    def subir_archivo_multipart(
        self,
        file_stream: BinaryIO,
        gcs_path: str,
        content_type: str = "video/mp4",
        chunk_size: int = 50 * 1024 * 1024,  # 50MB por chunk
        max_workers: int = 5,  # 5 uploads paralelos
        timeout_seconds: int = 3600,
    ) -> Dict[str, Any]:
        """
        Sube un archivo grande en chunks paralelos

        Args:
            file_stream: Stream del archivo
            gcs_path: Ruta GCS destino (gs://bucket/path)
            content_type: Tipo MIME
            chunk_size: Tamaño de cada chunk (default: 50MB)
            max_workers: Número de uploads paralelos (default: 5)
            timeout_seconds: Timeout total

        Returns:
            Dict con stats: {
                'bytes_uploaded': int,
                'chunks_count': int,
                'elapsed_seconds': float,
                'avg_speed_mbps': float
            }
        """
        if not self.is_available():
            raise Exception("MultipartUploadService no está disponible")

        start_time = time.time()
        temp_dir = None

        try:
            # Parsear GCS path
            path_parts = gcs_path.replace("gs://", "").split("/", 1)
            if len(path_parts) != 2:
                raise ValueError(f"Path GCS inválido: {gcs_path}")

            bucket_name, blob_name = path_parts

            logger.info(f"📦 Iniciando multipart upload: {gcs_path}")
            logger.info(f"   Chunk size: {chunk_size / (1024*1024):.1f} MB")
            logger.info(f"   Workers: {max_workers}")

            # 1. Guardar archivo en temp y dividir en chunks
            temp_dir = tempfile.mkdtemp(prefix="multipart_")
            temp_file = os.path.join(temp_dir, "upload_file")
            
            logger.info(f"💾 Guardando stream a temp: {temp_file}")
            bytes_written = 0
            with open(temp_file, 'wb') as f:
                while True:
                    chunk = file_stream.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_written += len(chunk)
                    
                    # Log progreso de escritura
                    if bytes_written % (100 * 1024 * 1024) == 0:  # Cada 100MB
                        mb_written = bytes_written / (1024 * 1024)
                        logger.info(f"   💾 Escritura temp: {mb_written:.1f} MB")

            file_size = os.path.getsize(temp_file)
            logger.info(f"✅ Archivo temp creado: {file_size / (1024*1024):.1f} MB")

            # 2. Dividir en chunks
            chunks_info = self._dividir_archivo_chunks(
                temp_file, chunk_size
            )
            chunks_count = len(chunks_info)
            
            logger.info(f"🔪 Archivo dividido en {chunks_count} chunks")

            # 3. Subir chunks en paralelo
            logger.info(f"🚀 Subiendo {chunks_count} chunks con {max_workers} workers...")
            
            bucket = self.storage_client.bucket(bucket_name)
            chunks_completados = 0
            bytes_uploaded = 0
            last_log_time = time.time()

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Crear tareas para cada chunk
                futures = {}
                for chunk_info in chunks_info:
                    future = executor.submit(
                        self._subir_chunk,
                        bucket,
                        blob_name,
                        chunk_info,
                        content_type,
                        timeout_seconds
                    )
                    futures[future] = chunk_info

                # Procesar resultados conforme completan
                for future in as_completed(futures):
                    chunk_info = futures[future]
                    try:
                        result = future.result()
                        chunks_completados += 1
                        bytes_uploaded += result['bytes']
                        
                        # Log progreso cada 3 chunks o cada 10 segundos
                        current_time = time.time()
                        if chunks_completados % 3 == 0 or (current_time - last_log_time) >= 10:
                            percent = (chunks_completados / chunks_count) * 100
                            elapsed = current_time - start_time
                            speed = (bytes_uploaded / (1024*1024)) / elapsed if elapsed > 0 else 0
                            
                            logger.info(
                                f"⏳ Progreso: {chunks_completados}/{chunks_count} chunks "
                                f"({percent:.1f}%) | {speed:.2f} MB/s"
                            )
                            last_log_time = current_time
                            
                    except Exception as e:
                        logger.error(f"❌ Error subiendo chunk {chunk_info['index']}: {e}")
                        raise

            # 4. Componer chunks en GCS
            logger.info("🔗 Componiendo chunks en archivo final...")
            final_blob = self._componer_chunks(
                bucket, blob_name, chunks_info, content_type
            )

            # 5. Limpiar chunks temporales en GCS
            logger.info("🧹 Limpiando chunks temporales...")
            self._limpiar_chunks(bucket, blob_name, chunks_count)

            # Stats finales
            elapsed_total = time.time() - start_time
            mb_total = bytes_uploaded / (1024 * 1024)
            avg_speed = mb_total / elapsed_total if elapsed_total > 0 else 0

            logger.info(
                f"✅ MULTIPART UPLOAD COMPLETADO: {mb_total:.1f} MB en {elapsed_total:.1f}s "
                f"(promedio: {avg_speed:.2f} MB/s, {chunks_count} chunks)"
            )

            return {
                'bytes_uploaded': bytes_uploaded,
                'chunks_count': chunks_count,
                'elapsed_seconds': elapsed_total,
                'avg_speed_mbps': avg_speed,
            }

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ Error en multipart upload después de {elapsed:.1f}s: {e}")
            raise
        finally:
            # Limpiar directorio temporal
            if temp_dir and os.path.exists(temp_dir):
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                    logger.info("🧹 Temp dir limpiado")
                except Exception as e:
                    logger.warning(f"⚠️ Error limpiando temp dir: {e}")

    def _dividir_archivo_chunks(
        self, file_path: str, chunk_size: int
    ) -> List[Dict[str, Any]]:
        """
        Divide un archivo en chunks

        Returns:
            Lista de dicts con info de cada chunk:
            [
                {'index': 0, 'start': 0, 'end': 50MB, 'size': 50MB},
                {'index': 1, 'start': 50MB, 'end': 100MB, 'size': 50MB},
                ...
            ]
        """
        file_size = os.path.getsize(file_path)
        chunks = []
        
        start = 0
        index = 0
        
        while start < file_size:
            end = min(start + chunk_size, file_size)
            size = end - start
            
            chunks.append({
                'index': index,
                'start': start,
                'end': end,
                'size': size,
                'file_path': file_path,
            })
            
            start = end
            index += 1
        
        return chunks

    def _subir_chunk(
        self,
        bucket,
        blob_name: str,
        chunk_info: Dict[str, Any],
        content_type: str,
        timeout: int,
    ) -> Dict[str, Any]:
        """
        Sube un chunk individual a GCS

        Args:
            bucket: Bucket de GCS
            blob_name: Nombre base del blob
            chunk_info: Info del chunk
            content_type: Tipo MIME
            timeout: Timeout en segundos

        Returns:
            Dict con resultado: {'index': int, 'bytes': int, 'chunk_name': str}
        """
        index = chunk_info['index']
        chunk_name = f"{blob_name}.part{index:04d}"
        
        try:
            # Leer chunk del archivo
            with open(chunk_info['file_path'], 'rb') as f:
                f.seek(chunk_info['start'])
                chunk_data = f.read(chunk_info['size'])
            
            # Subir a GCS
            blob = bucket.blob(chunk_name)
            blob.content_type = content_type
            
            from google.api_core.retry import Retry
            retry = Retry(deadline=timeout)
            
            blob.upload_from_string(
                chunk_data,
                content_type=content_type,
                retry=retry,
                timeout=timeout,
            )
            
            return {
                'index': index,
                'bytes': len(chunk_data),
                'chunk_name': chunk_name,
            }
            
        except Exception as e:
            logger.error(f"❌ Error subiendo chunk {index}: {e}")
            raise

    def _componer_chunks(
        self,
        bucket,
        blob_name: str,
        chunks_info: List[Dict[str, Any]],
        content_type: str,
    ):
        """
        Compone los chunks en un único blob en GCS

        GCS tiene una operación nativa de compose para unir blobs
        """
        try:
            # Obtener blobs de chunks en orden
            chunk_blobs = []
            for chunk_info in sorted(chunks_info, key=lambda x: x['index']):
                chunk_name = f"{blob_name}.part{chunk_info['index']:04d}"
                chunk_blob = bucket.blob(chunk_name)
                chunk_blobs.append(chunk_blob)
            
            # Crear blob final
            final_blob = bucket.blob(blob_name)
            final_blob.content_type = content_type
            
            # Componer (GCS soporta hasta 32 chunks por operación)
            # Si hay más, hacer compose en batches
            if len(chunk_blobs) <= 32:
                final_blob.compose(chunk_blobs)
            else:
                # Compose en batches de 32
                temp_blobs = []
                for i in range(0, len(chunk_blobs), 32):
                    batch = chunk_blobs[i:i+32]
                    temp_name = f"{blob_name}.temp{i//32:04d}"
                    temp_blob = bucket.blob(temp_name)
                    temp_blob.compose(batch)
                    temp_blobs.append(temp_blob)
                
                # Componer temps en final
                final_blob.compose(temp_blobs)
                
                # Limpiar temps
                for temp_blob in temp_blobs:
                    temp_blob.delete()
            
            logger.info(f"✅ Chunks compuestos en: {blob_name}")
            return final_blob
            
        except Exception as e:
            logger.error(f"❌ Error componiendo chunks: {e}")
            raise

    def _limpiar_chunks(self, bucket, blob_name: str, chunks_count: int):
        """Elimina chunks temporales de GCS"""
        try:
            for i in range(chunks_count):
                chunk_name = f"{blob_name}.part{i:04d}"
                try:
                    blob = bucket.blob(chunk_name)
                    blob.delete()
                except Exception:
                    pass  # Ignorar si ya no existe
            
            logger.info(f"🧹 {chunks_count} chunks limpiados")
            
        except Exception as e:
            logger.warning(f"⚠️ Error limpiando chunks: {e}")
