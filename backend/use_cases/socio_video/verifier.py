import logging
import subprocess
from typing import Dict, Any

from domain.entities import Video

logger = logging.getLogger(__name__)

class VideoVerifier:
    """Paso 2: Verificar duración del video (60s máximo)"""

    def __init__(self, duracion_maxima: int = 60, tolerancia: int = 5):
        self.duracion_maxima = duracion_maxima
        self.tolerancia = tolerancia

    def _analizar_duracion_real(self, ruta_video: str) -> int:
        """Obtiene la duración real del video con ffprobe"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                ruta_video
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            if result.returncode == 0:
                return int(float(result.stdout.strip()))
            logger.error("ffprobe falló (código %d) al analizar %s", result.returncode, ruta_video)
            raise RuntimeError(f"ffprobe no pudo determinar la duración del video: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("ffprobe agotó el tiempo de espera al analizar el video")
        except FileNotFoundError:
            raise RuntimeError("ffprobe no está disponible en el sistema")

    def verify_duration(self, video: Video, archivo_analisis: str, contexto_analisis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Devuelve información sobre si pasó o no la verificación de duración.
        """
        logger.info(f"⏱️ [PASO 2] Verificando duración de {archivo_analisis}")
        duracion_segundos = self._analizar_duracion_real(archivo_analisis)
        video.agregar_metadatos("duracion_segundos", duracion_segundos)
        contexto_analisis["duracion_segundos"] = duracion_segundos

        valido = duracion_segundos <= (self.duracion_maxima + self.tolerancia)
        
        if not valido:
            msg = f"Duración excesiva: {duracion_segundos}s (máximo: {self.duracion_maxima + self.tolerancia}s)"
            return {
                "error": True,
                "msg": msg,
                "duracion_segundos": duracion_segundos
            }

        logger.info(f"✅ [PASO 2] Duración: {duracion_segundos}s (máx: {self.duracion_maxima + self.tolerancia}s)")
        return {
            "error": False,
            "duracion_segundos": duracion_segundos
        }
