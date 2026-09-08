"""
Adaptador de OpenCV para detección de movimiento en videos
Implementa estrategia híbrida: MOG2 + Optical Flow Sparse
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
import tempfile
import os

logger = logging.getLogger(__name__)


class MotionDetectorConfig:
    """Configuración para el detector de movimiento"""
    
    def __init__(
        self,
        sensitivity: float = 0.03,  # Más sensible para seguridad (antes 0.15)
        min_duration: int = 2,      # Mínimo 2 segundos (antes 5)
        blur_kernel: Tuple[int, int] = (21, 21),
        algorithm: str = "MOG2",
        use_optical_flow_validation: bool = True,
        skip_frames: int = 1,       # Procesar más frames (antes 2)
    ):
        """
        Args:
            sensitivity: Umbral de detección (0-1, menor = más sensible)
            min_duration: Duración mínima de movimiento en segundos
            blur_kernel: Tamaño del kernel de desenfoque
            algorithm: "MOG2" o "KNN"
            use_optical_flow_validation: Validar con optical flow
            skip_frames: Frames a saltar (2 = procesar 1 de cada 3)
        """
        self.sensitivity = sensitivity
        self.min_duration = min_duration
        self.blur_kernel = blur_kernel
        self.algorithm = algorithm
        self.use_optical_flow_validation = use_optical_flow_validation
        self.skip_frames = skip_frames


class OpenCVMotionDetector:
    """
    Detector de movimiento usando OpenCV
    
    Estrategia híbrida:
    1. MOG2/KNN para detección rápida (Background Subtraction)
    2. Optical Flow Sparse para validación (opcional pero recomendado)
    """
    
    def __init__(self, config: Optional[MotionDetectorConfig] = None):
        """Inicializa el detector de movimiento"""
        self.config = config or MotionDetectorConfig()
        self._cv2 = None
        self._numpy = None
        self._initialize_libraries()
    
    def _initialize_libraries(self):
        """Inicializa las librerías de OpenCV y NumPy"""
        try:
            import cv2
            import numpy as np
            self._cv2 = cv2
            self._numpy = np
            logger.info("✅ OpenCV y NumPy inicializados")
        except ImportError as e:
            logger.error(f"❌ Error importando OpenCV o NumPy: {e}")
            logger.error("Instala con: pip install opencv-python-headless numpy")
            self._cv2 = None
            self._numpy = None
    
    def is_available(self) -> bool:
        """Verifica si OpenCV está disponible"""
        return self._cv2 is not None and self._numpy is not None
    
    def detect_motion_segments(
        self, 
        video_path: str,
        progress_callback: Optional[callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Detecta segmentos con movimiento en un video
        
        Args:
            video_path: Ruta al archivo de video (local o descargado de GCS)
            progress_callback: Función para reportar progreso (recibe porcentaje)
        
        Returns:
            Lista de segmentos: [
                {
                    "timestamp_inicio": 123.5,
                    "timestamp_fin": 145.2,
                    "duracion": 21.7,
                    "intensidad": 0.85,
                    "frames_con_movimiento": 650,
                    "validado_optical_flow": True
                },
                ...
            ]
        """
        if not self.is_available():
            logger.error("❌ OpenCV no está disponible")
            return []
        
        if not os.path.exists(video_path):
            logger.error(f"❌ Video no encontrado: {video_path}")
            return []
        
        logger.info(f"🔍 Iniciando detección de movimiento: {video_path}")
        
        try:
            # Abrir video
            cap = self._cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"❌ No se pudo abrir el video: {video_path}")
                return []
            
            # Obtener metadata del video
            fps = cap.get(self._cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(self._cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0
            
            logger.info(f"📹 Video: {duration:.1f}s, {fps:.1f} FPS, {total_frames} frames")
            
            # Crear background subtractor
            if self.config.algorithm == "KNN":
                bg_subtractor = self._cv2.createBackgroundSubtractorKNN(
                    detectShadows=True
                )
            else:  # MOG2 (default)
                bg_subtractor = self._cv2.createBackgroundSubtractorMOG2(
                    detectShadows=True
                )
            
            # Variables de detección
            segments = []
            current_segment = None
            frame_count = 0
            frames_with_motion = 0
            prev_gray = None
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_count += 1
                
                # Saltar frames para velocidad
                if frame_count % (self.config.skip_frames + 1) != 0:
                    continue
                
                # Reportar progreso
                if progress_callback and frame_count % 300 == 0:
                    progress = (frame_count / total_frames) * 100
                    progress_callback(progress)
                
                # Timestamp actual
                timestamp = frame_count / fps
                
                # Preprocesar frame
                gray = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2GRAY)
                blurred = self._cv2.GaussianBlur(gray, self.config.blur_kernel, 0)
                
                # Aplicar background subtraction
                fg_mask = bg_subtractor.apply(blurred)
                
                # Limpiar ruido
                kernel = self._numpy.ones((5, 5), self._numpy.uint8)
                fg_mask = self._cv2.morphologyEx(fg_mask, self._cv2.MORPH_OPEN, kernel)
                fg_mask = self._cv2.morphologyEx(fg_mask, self._cv2.MORPH_CLOSE, kernel)
                
                # Calcular área de movimiento
                motion_pixels = self._numpy.sum(fg_mask > 0)
                total_pixels = fg_mask.shape[0] * fg_mask.shape[1]
                motion_ratio = motion_pixels / total_pixels
                
                # Detectar movimiento significativo
                has_motion = motion_ratio > self.config.sensitivity
                
                # Validar con Optical Flow si está habilitado
                if has_motion and self.config.use_optical_flow_validation and prev_gray is not None:
                    has_motion = self._validate_with_optical_flow(prev_gray, gray)
                
                prev_gray = gray.copy()
                
                # Gestionar segmentos
                if has_motion:
                    frames_with_motion += 1
                    
                    if current_segment is None:
                        # Iniciar nuevo segmento
                        current_segment = {
                            "timestamp_inicio": timestamp,
                            "frames": 1,
                            "intensity_sum": motion_ratio,
                        }
                    else:
                        # Continuar segmento actual
                        current_segment["frames"] += 1
                        current_segment["intensity_sum"] += motion_ratio
                else:
                    # Sin movimiento
                    if current_segment is not None:
                        # Finalizar segmento si cumple duración mínima
                        segment_duration = (timestamp - current_segment["timestamp_inicio"])
                        
                        if segment_duration >= self.config.min_duration:
                            segments.append({
                                "timestamp_inicio": current_segment["timestamp_inicio"],
                                "timestamp_fin": timestamp,
                                "duracion": segment_duration,
                                "intensidad": current_segment["intensity_sum"] / current_segment["frames"],
                                "frames_con_movimiento": current_segment["frames"],
                                "validado_optical_flow": self.config.use_optical_flow_validation,
                            })
                        
                        current_segment = None
            
            # Cerrar último segmento si existe
            if current_segment is not None:
                timestamp = frame_count / fps
                segment_duration = timestamp - current_segment["timestamp_inicio"]
                
                if segment_duration >= self.config.min_duration:
                    segments.append({
                        "timestamp_inicio": current_segment["timestamp_inicio"],
                        "timestamp_fin": timestamp,
                        "duracion": segment_duration,
                        "intensidad": current_segment["intensity_sum"] / current_segment["frames"],
                        "frames_con_movimiento": current_segment["frames"],
                        "validado_optical_flow": self.config.use_optical_flow_validation,
                    })
            
            cap.release()
            
            # Estadísticas
            total_motion_duration = sum(s["duracion"] for s in segments)
            motion_percentage = (total_motion_duration / duration) * 100 if duration > 0 else 0
            
            logger.info(f"✅ Detección completada:")
            logger.info(f"   • Segmentos detectados: {len(segments)}")
            logger.info(f"   • Duración total con movimiento: {total_motion_duration:.1f}s ({motion_percentage:.1f}%)")
            logger.info(f"   • Duración total video: {duration:.1f}s")
            
            return segments
        
        except Exception as e:
            logger.error(f"❌ Error detectando movimiento: {e}")
            return []
    
    def _validate_with_optical_flow(self, prev_gray, curr_gray) -> bool:
        """
        Valida movimiento usando Sparse Optical Flow (Lucas-Kanade)
        
        Returns:
            True si el movimiento es real (no es ruido o cambio de luz)
        """
        try:
            # Detectar puntos característicos (corners)
            corners = self._cv2.goodFeaturesToTrack(
                prev_gray,
                maxCorners=200,
                qualityLevel=0.01,
                minDistance=10,
                blockSize=7
            )
            
            if corners is None or len(corners) < 10:
                return False
            
            # Calcular optical flow
            next_corners, status, _ = self._cv2.calcOpticalFlowPyrLK(
                prev_gray,
                curr_gray,
                corners,
                None,
                winSize=(15, 15),
                maxLevel=2
            )
            
            if next_corners is None:
                return False
            
            # Filtrar puntos válidos
            good_old = corners[status == 1]
            good_new = next_corners[status == 1]
            
            if len(good_old) < 10:
                return False
            
            # Calcular magnitud del movimiento
            displacement = good_new - good_old
            magnitudes = self._numpy.linalg.norm(displacement, axis=1)
            avg_magnitude = self._numpy.mean(magnitudes)
            
            # Umbral: movimiento real si promedio > 2 píxeles
            return avg_magnitude > 2.0
        
        except Exception as e:
            logger.debug(f"Error en optical flow validation: {e}")
            return True  # En caso de error, aceptar el movimiento
    
    def download_from_gcs(self, gcs_path: str) -> Optional[str]:
        """
        Descarga un video de GCS a archivo temporal
        
        Args:
            gcs_path: Ruta GCS (gs://bucket/path)
        
        Returns:
            Ruta del archivo temporal o None si falla
        """
        try:
            from google.cloud import storage
            
            # Parsear GCS path
            if not gcs_path.startswith("gs://"):
                return None
            
            path_parts = gcs_path.replace("gs://", "").split("/", 1)
            if len(path_parts) != 2:
                return None
            
            bucket_name, blob_name = path_parts
            
            # Descargar a archivo temporal
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            
            # Crear archivo temporal
            suffix = os.path.splitext(blob_name)[1] or ".mp4"
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_path = temp_file.name
            temp_file.close()
            
            logger.info(f"📥 Descargando video de GCS: {gcs_path}")
            blob.download_to_filename(temp_path)
            
            file_size_mb = os.path.getsize(temp_path) / (1024 * 1024)
            logger.info(f"✅ Video descargado: {file_size_mb:.1f} MB")
            
            return temp_path
        
        except Exception as e:
            logger.error(f"❌ Error descargando de GCS: {e}")
            return None
    
    def cleanup_temp_file(self, temp_path: str):
        """Elimina archivo temporal"""
        try:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
                logger.debug(f"🗑️ Archivo temporal eliminado: {temp_path}")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo eliminar archivo temporal: {e}")
