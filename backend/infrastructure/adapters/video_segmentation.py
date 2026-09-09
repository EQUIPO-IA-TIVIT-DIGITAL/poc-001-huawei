"""
Adaptador para segmentación y extracción de clips de video usando FFmpeg
"""

import logging
import subprocess
import os
import tempfile
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class VideoSegmentationAdapter:
    """
    Adaptador para extraer clips de video usando FFmpeg
    
    Funcionalidades:
    - Extraer clips de timestamps específicos
    - Extraer frames individuales
    - Obtener metadata del video
    """
    
    def __init__(self):
        """Inicializa el adaptador"""
        self._ffmpeg_available = self._check_ffmpeg()
    
    def _check_ffmpeg(self) -> bool:
        """Verifica si FFmpeg está instalado"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info("✅ FFmpeg disponible")
                return True
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("⚠️ FFmpeg no encontrado. Instala con: apt-get install ffmpeg")
            return False
    
    def is_available(self) -> bool:
        """Verifica si FFmpeg está disponible"""
        return self._ffmpeg_available
    
    def extract_clip(
        self,
        video_path: str,
        start_time: float,
        duration: float,
        output_path: str,
        add_buffer: float = 2.0
    ) -> bool:
        """
        Extrae un clip de video
        
        Args:
            video_path: Ruta al video fuente
            start_time: Tiempo de inicio en segundos
            duration: Duración del clip en segundos
            output_path: Ruta donde guardar el clip
            add_buffer: Segundos adicionales antes/después (default: 2s)
        
        Returns:
            True si se extrajo correctamente
        """
        if not self.is_available():
            logger.error("❌ FFmpeg no disponible")
            return False
        
        try:
            # Agregar buffer (2s antes y después)
            actual_start = max(0, start_time - add_buffer)
            actual_duration = duration + (2 * add_buffer)
            
            # Crear directorio si no existe
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Comando FFmpeg para extraer clip
            cmd = [
                "ffmpeg",
                "-y",  # Sobrescribir si existe
                "-ss", str(actual_start),  # Inicio
                "-i", video_path,  # Input
                "-t", str(actual_duration),  # Duración
                "-c:v", "libx264",  # Codec video
                "-preset", "fast",  # Preset rápido
                "-crf", "23",  # Calidad
                "-c:a", "aac",  # Codec audio
                "-b:a", "128k",  # Bitrate audio
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutos max por clip
            )
            
            if result.returncode == 0 and os.path.exists(output_path):
                file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                logger.info(f"✅ Clip extraído: {output_path} ({file_size_mb:.1f} MB)")
                return True
            else:
                logger.error(f"❌ Error extrayendo clip: {result.stderr}")
                return False
        
        except subprocess.TimeoutExpired:
            logger.error("❌ Timeout extrayendo clip")
            return False
        except Exception as e:
            logger.error(f"❌ Error extrayendo clip: {e}")
            return False
    
    def extract_frames(
        self,
        video_path: str,
        timestamps: List[float],
        output_dir: str
    ) -> List[str]:
        """
        Extrae frames individuales en timestamps específicos
        
        Args:
            video_path: Ruta al video fuente
            timestamps: Lista de timestamps en segundos
            output_dir: Directorio donde guardar los frames
        
        Returns:
            Lista de rutas a los frames extraídos
        """
        if not self.is_available():
            logger.error("❌ FFmpeg no disponible")
            return []
        
        os.makedirs(output_dir, exist_ok=True)
        frame_paths = []
        
        for i, timestamp in enumerate(timestamps):
            try:
                output_path = os.path.join(output_dir, f"frame_{i:04d}_{int(timestamp)}s.jpg")
                
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-ss", str(timestamp),
                    "-i", video_path,
                    "-frames:v", "1",  # Solo 1 frame
                    "-q:v", "2",  # Alta calidad
                    output_path
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0 and os.path.exists(output_path):
                    frame_paths.append(output_path)
                    logger.debug(f"✅ Frame extraído: {output_path}")
            
            except Exception as e:
                logger.error(f"❌ Error extrayendo frame en {timestamp}s: {e}")
        
        logger.info(f"✅ Frames extraídos: {len(frame_paths)}/{len(timestamps)}")
        return frame_paths
    
    def get_video_metadata(self, video_path: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene metadata del video usando FFprobe
        
        Returns:
            {
                "duration": 3600.5,
                "fps": 30.0,
                "width": 1920,
                "height": 1080,
                "codec": "h264",
                "bitrate": 8000000,
                "size_bytes": 42000000
            }
        """
        if not self.is_available():
            return None
        
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return None
            
            import json
            data = json.loads(result.stdout)
            
            # Extraer info relevante
            format_info = data.get("format", {})
            video_stream = next(
                (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
                {}
            )
            
            # Calcular FPS
            fps_str = video_stream.get("r_frame_rate", "30/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den) if float(den) > 0 else 30.0
            else:
                fps = float(fps_str)
            
            metadata = {
                "duration": float(format_info.get("duration", 0)),
                "fps": fps,
                "width": int(video_stream.get("width", 0)),
                "height": int(video_stream.get("height", 0)),
                "codec": video_stream.get("codec_name", "unknown"),
                "bitrate": int(format_info.get("bit_rate", 0)),
                "size_bytes": int(format_info.get("size", 0)),
            }
            
            logger.info(f"📹 Metadata: {metadata['duration']:.1f}s, {metadata['fps']:.1f}fps, {metadata['width']}x{metadata['height']}")
            return metadata
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo metadata: {e}")
            return None
    
    def extract_frames_from_clip(
        self,
        video_path: str,
        num_frames: int = 5,
        output_dir: Optional[str] = None
    ) -> List[str]:
        """
        Extrae frames equidistantes de un video completo
        
        Args:
            video_path: Ruta al video
            num_frames: Cantidad de frames a extraer
            output_dir: Directorio de salida (o temp si None)
        
        Returns:
            Lista de rutas a los frames
        """
        metadata = self.get_video_metadata(video_path)
        if not metadata or metadata["duration"] <= 0:
            return []
        
        duration = metadata["duration"]
        
        # Calcular timestamps equidistantes
        if num_frames == 1:
            timestamps = [duration / 2]
        else:
            interval = duration / (num_frames + 1)
            timestamps = [interval * (i + 1) for i in range(num_frames)]
        
        # Usar directorio temporal si no se especifica
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="frames_")
        
        return self.extract_frames(video_path, timestamps, output_dir)
    
    def upload_to_storage(self, local_path: str, storage_path: str) -> bool:
        """
        Sube un archivo al almacenamiento local
        
        Args:
            local_path: Ruta local del archivo
            storage_path: Ruta de destino (s3://bucket/path, file://path o key)
        
        Returns:
            True si se subió correctamente
        """
        try:
            from infrastructure.dependencies import get_storage_adapter

            blob_name = storage_path
            if "://" in storage_path:
                _, remainder = storage_path.split("://", 1)
                blob_name = remainder.split("/", 1)[1] if "/" in remainder else remainder

            storage = get_storage_adapter()
            if not storage or not storage.is_available():
                return False
            if hasattr(storage, "upload_file"):
                storage.upload_file(local_path, blob_name)
            else:
                storage.upload_video(local_path, blob_name)
            
            file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
            logger.info(f"✅ Archivo subido al almacenamiento: {storage_path} ({file_size_mb:.1f} MB)")
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Error subiendo al almacenamiento: {e}")
            return False
    
    def batch_extract_clips(
        self,
        video_path: str,
        segments: List[Dict[str, Any]],
        output_dir: str,
        upload_to_storage: bool = False,
        storage_base_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Extrae múltiples clips de un video
        
        Args:
            video_path: Ruta al video fuente
            segments: Lista de segmentos con timestamp_inicio y duracion
            output_dir: Directorio donde guardar los clips
            upload_to_storage: Si True, sube los clips al almacenamiento
            storage_base_path: Ruta base en el almacenamiento
        
        Returns:
            Lista de segmentos con rutas de clips agregadas
        """
        os.makedirs(output_dir, exist_ok=True)
        results = []
        
        for i, segment in enumerate(segments):
            try:
                # Generar nombre de archivo
                clip_filename = f"clip_{i:04d}_{int(segment['timestamp_inicio'])}s.mp4"
                local_clip_path = os.path.join(output_dir, clip_filename)
                
                # Extraer clip
                success = self.extract_clip(
                    video_path,
                    segment["timestamp_inicio"],
                    segment["duracion"],
                    local_clip_path
                )
                
                if not success:
                    continue
                
                # Actualizar segmento
                segment_result = segment.copy()
                segment_result["clip_path_local"] = local_clip_path
                
                if upload_to_storage and storage_base_path:
                    storage_clip_path = f"{storage_base_path.rstrip('/')}/{clip_filename}"
                    if self.upload_to_storage(local_clip_path, storage_clip_path):
                        segment_result["clip_url"] = storage_clip_path
                
                results.append(segment_result)
            
            except Exception as e:
                logger.error(f"❌ Error procesando clip {i}: {e}")
        
        logger.info(f"✅ Clips extraídos: {len(results)}/{len(segments)}")
        return results
