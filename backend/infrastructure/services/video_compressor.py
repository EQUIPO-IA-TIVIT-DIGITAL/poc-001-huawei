"""
Servicio de compresión de video para optimizar análisis
Comprime videos a 720p antes de enviar al almacenamiento y al análisis de IA
"""
import subprocess
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class VideoCompressor:
    """
    Comprime videos a 720p para reducir tiempos de upload y análisis.
    La IA local no necesita 4K; 720p es suficiente para detección.
    """

    def __init__(self):
        self.available = self._check_ffmpeg()
        if self.available:
            logger.info("✅ VideoCompressor disponible (FFmpeg encontrado)")
        else:
            logger.warning("⚠️ FFmpeg no encontrado - compresión deshabilitada")

    def _check_ffmpeg(self) -> bool:
        """Verifica que FFmpeg esté disponible"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def is_available(self) -> bool:
        return self.available

    def needs_compression(self, video_path: str, max_height: int = 720) -> bool:
        """
        Determina si el video necesita compresión.
        Solo comprime si la resolución es mayor a max_height.
        """
        try:
            info = self.get_video_info(video_path)
            if not info:
                return False
            return info["height"] > max_height
        except Exception:
            return False

    def get_video_info(self, video_path: str) -> Optional[dict]:
        """Obtiene resolución y tamaño del video"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,codec_name",
                "-show_entries", "format=size,duration",
                "-of", "json",
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return None

            import json
            data = json.loads(result.stdout)
            stream = data.get("streams", [{}])[0]
            fmt = data.get("format", {})

            return {
                "width": int(stream.get("width", 0)),
                "height": int(stream.get("height", 0)),
                "codec": stream.get("codec_name", "unknown"),
                "size_bytes": int(fmt.get("size", 0)),
                "duration": float(fmt.get("duration", 0)),
            }
        except Exception as e:
            logger.warning(f"Error obteniendo info del video: {e}")
            return None

    def compress(
        self,
        input_path: str,
        max_height: int = 720,
        crf: int = 28,
        preset: str = "fast"
    ) -> Tuple[Optional[str], dict]:
        """
        Comprime el video a max_height manteniendo aspect ratio.

        Args:
            input_path: Ruta del video original
            max_height: Altura máxima (default 720p)
            crf: Calidad (18=alta, 28=media, 35=baja; default 28)
            preset: FFmpeg preset (ultrafast/fast/medium; default fast)

        Returns:
            Tuple[ruta_comprimido | None, stats_dict]
        """
        if not self.available:
            return None, {"error": "FFmpeg no disponible"}

        original_info = self.get_video_info(input_path)
        if not original_info:
            return None, {"error": "No se pudo leer info del video"}

        # Si ya es menor o igual a 720p, no comprimir
        if original_info["height"] <= max_height:
            logger.info(f"📹 Video ya es {original_info['height']}p, sin comprimir")
            return None, {
                "skipped": True,
                "reason": f"Ya es {original_info['height']}p",
                "original_size": original_info["size_bytes"]
            }

        # Crear archivo temporal para el video comprimido
        input_ext = Path(input_path).suffix
        fd, output_path = tempfile.mkstemp(suffix=input_ext)
        os.close(fd)

        try:
            # Escala proporcional: -2 mantiene divisible por 2
            scale_filter = f"scale=-2:{max_height}"

            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", scale_filter,
                "-c:v", "libx264",
                "-crf", str(crf),
                "-preset", preset,
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                "-threads", "2",
                output_path
            ]

            logger.info(f"🔄 Comprimiendo video a {max_height}p (CRF={crf})...")
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300  # 5 min max
            )

            if result.returncode != 0:
                logger.error(f"Error FFmpeg: {result.stderr[:500]}")
                os.unlink(output_path)
                return None, {"error": f"FFmpeg falló: {result.stderr[:200]}"}

            compressed_info = self.get_video_info(output_path)
            original_size = original_info["size_bytes"]
            compressed_size = compressed_info["size_bytes"] if compressed_info else os.path.getsize(output_path)

            savings_pct = ((original_size - compressed_size) / original_size * 100) if original_size > 0 else 0

            stats = {
                "original_size": original_size,
                "compressed_size": compressed_size,
                "savings_percent": round(savings_pct, 1),
                "original_resolution": f"{original_info['width']}x{original_info['height']}",
                "compressed_resolution": f"{compressed_info['width']}x{compressed_info['height']}" if compressed_info else f"?x{max_height}",
            }

            logger.info(
                f"✅ Compresión: {original_size // 1024}KB → {compressed_size // 1024}KB "
                f"({stats['savings_percent']}% ahorro)"
            )

            return output_path, stats

        except subprocess.TimeoutExpired:
            logger.error("Timeout comprimiendo video (5 min)")
            if os.path.exists(output_path):
                os.unlink(output_path)
            return None, {"error": "Timeout de compresión"}

        except Exception as e:
            logger.error(f"Error comprimiendo video: {e}")
            if os.path.exists(output_path):
                os.unlink(output_path)
            return None, {"error": str(e)}

    def has_audio(self, video_path: str) -> bool:
        """
        Verifica rápidamente si un video tiene pista de audio.
        Usado para Speech-to-Text condicional.
        """
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            return bool(result.stdout.strip())
        except Exception:
            return False
