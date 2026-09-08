from concurrent.futures import ThreadPoolExecutor
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from domain.entities import Video, EstadoVideo
from infrastructure.services.thumbnail_service import ThumbnailService

logger = logging.getLogger(__name__)

class VideoPreparator:
    """Paso 1: Compresión + Upload a GCS + Thumbnail (paralelo)"""

    def __init__(self, compressor, storage, gcp_enabled: bool):
        self.compressor = compressor
        self.storage = storage
        self.gcp_enabled = gcp_enabled

    def _generar_thumbnail_safe(self, video: Video):
        try:
            thumbnail_service = ThumbnailService()
            thumbnail_path = thumbnail_service.generate_thumbnail(video.ruta_archivo, video.id)
            if thumbnail_path:
                video.agregar_metadatos("thumbnail_generado", True)
        except Exception as e:
            logger.warning(f"No se pudo generar thumbnail: {e}")
            video.agregar_metadatos("thumbnail_generado", False)

    def _obtener_timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def process_preparation(
        self, video: Video, archivo_analisis: str, contexto_analisis: Dict[str, Any], upload_to_gcs: bool
    ) -> Dict[str, Any]:
        """
        Devuelve dict con result_data.
        Puede lanzar excepción o devolver {"error": True} si falla critical.
        """
        logger.info(f"📦 [PASO 1] Preparación: archivo={video.ruta_archivo}, formato={video.formato}")
        
        gcs_uri = None
        compression_stats = None
        compressed_path = None
        current_archivo_analisis = archivo_analisis

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}

            # Tarea 1: Comprimir si es necesario
            if self.compressor.is_available() and self.compressor.needs_compression(video.ruta_archivo):
                futures["compress"] = executor.submit(self.compressor.compress, video.ruta_archivo)

            # Tarea 2: Generar thumbnail
            futures["thumbnail"] = executor.submit(self._generar_thumbnail_safe, video)

            # Esperar compresión
            if "compress" in futures:
                try:
                    comp_result, comp_stats = futures["compress"].result(timeout=60)
                    compression_stats = comp_stats
                    if comp_result:
                        compressed_path = comp_result
                        current_archivo_analisis = compressed_path
                        contexto_analisis["compresion"] = comp_stats
                        logger.info(f"✅ Compresión: {comp_stats.get('savings_percent', 0):.1f}% ahorro")
                except Exception as e:
                    logger.warning(f"Compresión fallida, usando original: {e}")

            # Tarea 3: Upload a GCS
            if self.gcp_enabled and upload_to_gcs and self.storage and self.storage.is_available():
                gcs_uri = self.storage.upload_video(
                    file_path=current_archivo_analisis,
                    video_id=video.id,
                    content_type=f"video/{video.formato}",
                    metadata={
                        "socio_id": getattr(video, "socio_id", "unknown"),
                        "nombre_archivo": video.nombre_archivo,
                        "upload_date": self._obtener_timestamp(),
                        "compressed": str(compressed_path is not None),
                    },
                )

                if gcs_uri:
                    video.agregar_metadatos("gcs_uri", gcs_uri)
                    blob_name = f"videos/{video.id}.{video.formato}"
                    signed_url = self.storage.generate_signed_url(blob_name, expiration_minutes=1440)
                    if signed_url:
                        video.agregar_metadatos("video_url", signed_url)
                        video.agregar_metadatos("video_url_expiration", "24 hours")
                else:
                    return {
                        "error": True,
                        "msg": "Error crítico: No se pudo subir a Cloud Storage.",
                        "compressed_path": compressed_path
                    }

            # Esperar thumbnail
            if "thumbnail" in futures:
                try:
                    futures["thumbnail"].result(timeout=15)
                except Exception:
                    pass

        if compression_stats:
            video.agregar_metadatos("compresion", compression_stats)

        return {
            "error": False,
            "gcs_uri": gcs_uri,
            "compressed_path": compressed_path,
            "archivo_analisis": current_archivo_analisis
        }
