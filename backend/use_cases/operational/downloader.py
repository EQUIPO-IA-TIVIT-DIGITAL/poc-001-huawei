import os
import json
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

class OperationalDownloader:
    """Fase 0: Maneja la descarga y extracción de metadata de videos operativos"""
    
    def __init__(self, optimized_processor):
        self.optimized_processor = optimized_processor
        
    def download_and_get_metadata(self, analysis, vid: str, local_video_path: str = "") -> dict:
        """Descarga el video (si es necesario) y extrae metadata"""
        if not local_video_path or not os.path.exists(local_video_path):
            if analysis.video_url:
                logger.info(f"[{vid}] 📥 Descargando video desde almacenamiento: {analysis.video_url}")
                # Descargar en OPERATIONAL_TMP_DIR si está configurado.
                base_tmp = os.environ.get("OPERATIONAL_TMP_DIR") or tempfile.gettempdir()
                os.makedirs(base_tmp, exist_ok=True)
                suffix = Path(analysis.video_url).suffix or ".mp4"
                dest = tempfile.NamedTemporaryFile(
                    delete=False, suffix=suffix, prefix="op_video_", dir=base_tmp
                )
                dest.close()
                local_video_path = self.optimized_processor.download_from_storage(
                    analysis.video_url, local_path=dest.name
                )
            else:
                raise ValueError("No hay video_path local ni video_url para descargar")

        video_metadata = self._get_video_metadata(local_video_path, vid)
        video_duration = video_metadata.get('duration_seconds', 0) if video_metadata else 0
        file_size_mb = os.path.getsize(local_video_path) / (1024 * 1024)
        
        return {
            'local_video_path': local_video_path,
            'duration_seconds': video_duration,
            'file_size_mb': file_size_mb,
            'metadata': video_metadata
        }
        
    def _get_video_metadata(self, video_path: str, vid: str) -> dict:
        """Obtiene metadata con FFmpeg (un reintento en caso de fallo transitorio)"""
        for attempt in range(2):
            try:
                import subprocess
                result = subprocess.run(
                    ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                     '-show_format', '-show_streams', video_path],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    fmt = data.get('format', {})
                    duration = float(fmt.get('duration', 0))
                    streams = data.get('streams', [])
                    video_stream = next((s for s in streams if s.get('codec_type') == 'video'), {})
                    fps = 0
                    if video_stream.get('r_frame_rate'):
                        parts = video_stream['r_frame_rate'].split('/')
                        if len(parts) == 2 and int(parts[1]) > 0:
                            fps = int(parts[0]) / int(parts[1])
                    meta = {
                        'duration_seconds': duration,
                        'fps': fps,
                        'width': int(video_stream.get('width', 0)),
                        'height': int(video_stream.get('height', 0)),
                        'codec': video_stream.get('codec_name', ''),
                        'file_size_bytes': int(fmt.get('size', 0))
                    }
                    logger.info(f"[{vid}] 📹 Metadata: {duration/3600:.1f}h, {fps:.0f}fps, "
                                f"{meta['width']}x{meta['height']}")
                    return meta
                logger.warning(
                    f"[{vid}] ⚠️ ffprobe intento {attempt + 1} falló (código {result.returncode}): "
                    f"{result.stderr[:200]}"
                )
            except Exception as e:
                logger.warning(f"[{vid}] ⚠️ ffprobe intento {attempt + 1} error: {e}")

        # Fallback OpenCV
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            logger.info(f"[{vid}] 📹 Metadata (fallback OpenCV): {frames/fps if fps > 0 else 0:.1f}s, {fps:.0f}fps")
            return {'duration_seconds': frames / fps if fps > 0 else 0, 'fps': fps}
        except Exception as e:
            logger.error(f"[{vid}] ❌ No se pudo obtener metadata (ffprobe ni OpenCV): {e}")
            return None
