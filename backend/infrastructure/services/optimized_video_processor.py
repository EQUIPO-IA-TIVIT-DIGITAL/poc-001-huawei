"""
Procesador de video optimizado con:
- Reducción de resolución
- Skip frames
- Streaming desde GCS
- Análisis completo de todos los eventos
"""
import cv2
import numpy as np
import os
from typing import List, Optional, Tuple
from pathlib import Path
import tempfile
import logging

from .motion_detector import MotionDetector, MotionSegment

logger = logging.getLogger(__name__)

class OptimizedVideoProcessor:
    """Procesador de video optimizado para análisis de seguridad"""
    
    def __init__(
        self,
        target_resolution: Tuple[int, int] = (640, 480),
        frame_skip_rate: int = 3,
        motion_threshold: float = 0.02
    ):
        """
        Args:
            target_resolution: Resolución objetivo (ancho, alto)
            frame_skip_rate: Procesar 1 de cada N frames
            motion_threshold: Umbral para detectar movimiento
        """
        self.target_resolution = target_resolution
        self.frame_skip_rate = frame_skip_rate
        self.motion_detector = MotionDetector(motion_threshold=motion_threshold)
        
    def extract_optimized_frames(
        self,
        video_path: str,
        start_second: Optional[float] = None,
        end_second: Optional[float] = None,
        max_frames: Optional[int] = None
    ) -> List[np.ndarray]:
        """
        Extrae frames optimizados (resolución reducida + skip)
        
        Args:
            video_path: Ruta al video
            start_second: Segundo de inicio (opcional)
            end_second: Segundo de fin (opcional)
            max_frames: Máximo de frames a extraer (opcional)
            
        Returns:
            Lista de frames en formato numpy array
        """
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            logger.error(f"No se pudo abrir video: {video_path}")
            return []
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Calcular frame de inicio/fin
        start_frame = int(start_second * fps) if start_second else 0
        end_frame = int(end_second * fps) if end_second else total_frames
        
        frames = []
        frame_idx = 0
        
        try:
            # Posicionar en frame de inicio
            if start_frame > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                frame_idx = start_frame
                
            while frame_idx < end_frame:
                ret, frame = cap.read()
                if not ret:
                    break
                    
                # Skip frames
                if (frame_idx - start_frame) % self.frame_skip_rate == 0:
                    # Reducir resolución
                    frame_resized = cv2.resize(
                        frame,
                        self.target_resolution,
                        interpolation=cv2.INTER_AREA
                    )
                    frames.append(frame_resized)
                    
                    # Limitar frames si se especificó
                    if max_frames and len(frames) >= max_frames:
                        break
                        
                frame_idx += 1
                
        finally:
            cap.release()
            
        logger.info(
            f"📊 Extraídos {len(frames)} frames optimizados "
            f"(resolución: {self.target_resolution}, skip: {self.frame_skip_rate})"
        )
        return frames
    
    def get_motion_segments(self, video_path: str) -> List[MotionSegment]:
        """
        Obtiene segmentos con movimiento del video
        
        Returns:
            Lista de segmentos con movimiento detectado
        """
        return self.motion_detector.detect_motion_segments(
            video_path,
            sample_rate=self.frame_skip_rate
        )
    
    def download_from_storage(
        self,
        storage_uri: str,
        local_path: Optional[str] = None
    ) -> str:
        """
        Descarga video desde el almacenamiento local (MinIO/filesystem).

        Acepta URIs s3://bucket/key, file:///ruta y gs://bucket/key heredados.
        o keys/rutas desnudas.

        Args:
            storage_uri: URI del archivo
            local_path: Ruta local (si None, usa temporal)
            
        Returns:
            Ruta local del video descargado
        """
        # Crear path local si no se especificó
        if local_path is None:
            suffix = Path(storage_uri).suffix or '.mp4'
            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
                prefix='video_download_'
            )
            local_path = temp_file.name
            temp_file.close()

        blob_name = storage_uri
        if "://" in storage_uri:
            scheme, rest = storage_uri.split("://", 1)
            if scheme == "file":
                import shutil
                shutil.copy2(rest, local_path)
                logger.info(f"✅ Descarga completada (file): {local_path}")
                return local_path
            if "/" in rest:
                blob_name = rest.split("/", 1)[1]
            else:
                blob_name = rest

        logger.info(f"📥 Descargando {storage_uri} → {local_path}")

        import time as _dl_time
        if blob_name.startswith('/') and os.path.exists(blob_name):
            import shutil
            shutil.copy2(blob_name, local_path)
        else:
            from infrastructure.dependencies import get_storage_adapter
            storage = get_storage_adapter()
            if not storage or not storage.is_available():
                raise RuntimeError("Storage no disponible")
            dl_start = _dl_time.time()
            if hasattr(storage, 'descargar_archivo'):
                storage.descargar_archivo(blob_name, local_path)
            else:
                storage.download_file(blob_name, local_path)
            dl_elapsed = _dl_time.time() - dl_start

        local_size = os.path.getsize(local_path) / (1024 * 1024) if os.path.exists(local_path) else 0
        speed = local_size / max(_dl_time.time() - (locals().get('dl_start', _dl_time.time())), 0.1)
        logger.info(f"✅ Descarga completada: {local_path}")
        logger.info(f"   📊 {local_size:.1f} MB ({speed:.1f} MB/s)")

        return local_path
    
    def create_clip(
        self,
        video_path: str,
        start_second: float,
        end_second: float,
        output_path: Optional[str] = None
    ) -> str:
        """
        Crea un clip de video (segmento)
        
        Args:
            video_path: Ruta al video original
            start_second: Segundo de inicio
            end_second: Segundo de fin
            output_path: Ruta de salida (si None, usa temporal)
            
        Returns:
            Ruta al clip creado
        """
        if output_path is None:
            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix='.mp4',
                prefix=f'clip_{int(start_second)}_{int(end_second)}_'
            )
            output_path = temp_file.name
            temp_file.close()
            
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        start_frame = int(start_second * fps)
        end_frame = int(end_second * fps)
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        
        for _ in range(end_frame - start_frame):
            ret, frame = cap.read()
            if not ret:
                break
            out.write(frame)
            
        cap.release()
        out.release()
        
        logger.info(f"✂️  Clip creado: {output_path} ({start_second}s - {end_second}s)")
        return output_path
