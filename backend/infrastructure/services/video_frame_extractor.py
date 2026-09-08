"""
Servicio de extracción de frames de video
Utiliza OpenCV para extraer fotogramas distribuidos uniformemente
"""
import cv2
import base64
import logging
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class VideoFrameExtractor:
    """
    Servicio para extraer frames de videos
    
    Extrae fotogramas distribuidos uniformemente para análisis visual
    """
    
    def __init__(self):
        """Inicializa el extractor de frames"""
        self.available = True
        try:
            # Verificar que OpenCV está disponible
            import cv2
            logger.info("✅ OpenCV disponible para extracción de frames")
        except ImportError:
            logger.warning("⚠️ OpenCV no está instalado - Extracción de frames deshabilitada")
            self.available = False
    
    def is_available(self) -> bool:
        """Verifica si el servicio está disponible"""
        return self.available
    
    def extract_frames(self, video_path: str, num_frames: int = 10, 
                      max_dimension: int = 1024) -> Optional[List[str]]:
        """
        Extrae frames distribuidos uniformemente del video
        
        Args:
            video_path: Ruta del archivo de video
            num_frames: Número de frames a extraer (default: 10)
            max_dimension: Dimensión máxima para redimensionar (default: 1024px)
            
        Returns:
            Lista de frames codificados en base64 (JPEG) o None si falla
        """
        if not self.available:
            logger.error("OpenCV no está disponible")
            return None
        
        if not Path(video_path).exists():
            logger.error(f"El archivo de video no existe: {video_path}")
            return None
        
        try:
            # Abrir el video
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                logger.error(f"No se pudo abrir el video: {video_path}")
                return None
            
            # Obtener información del video
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duracion = total_frames / fps if fps > 0 else 0
            
            logger.info(f"📹 Video: {total_frames} frames, {fps:.2f} FPS, {duracion:.1f}s")
            
            if total_frames < num_frames:
                num_frames = max(1, total_frames)
                logger.info(f"⚠️ Video tiene menos frames que lo solicitado, extrayendo {num_frames}")
            
            # Calcular índices de frames distribuidos uniformemente
            if num_frames == 1:
                frame_indices = [total_frames // 2]  # Frame del medio
            else:
                frame_indices = [
                    int(i * total_frames / num_frames) 
                    for i in range(num_frames)
                ]
            
            frames_base64 = []
            frames_extraidos = 0
            
            # Extraer cada frame
            for idx in frame_indices:
                # Posicionar en el frame deseado
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                
                if not ret or frame is None:
                    logger.warning(f"No se pudo leer el frame {idx}")
                    continue
                
                # Redimensionar si es necesario (mantener aspect ratio)
                height, width = frame.shape[:2]
                if max(height, width) > max_dimension:
                    scale = max_dimension / max(height, width)
                    new_width = int(width * scale)
                    new_height = int(height * scale)
                    frame = cv2.resize(frame, (new_width, new_height), 
                                      interpolation=cv2.INTER_AREA)
                    logger.debug(f"Frame redimensionado: {width}x{height} → {new_width}x{new_height}")
                
                # Codificar a JPEG con calidad media
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                success, buffer = cv2.imencode('.jpg', frame, encode_param)
                
                if not success:
                    logger.warning(f"No se pudo codificar el frame {idx}")
                    continue
                
                # Convertir a base64
                frame_b64 = base64.b64encode(buffer).decode('utf-8')
                frames_base64.append(frame_b64)
                frames_extraidos += 1
                
                logger.debug(f"✓ Frame {idx}/{total_frames} extraído ({len(frame_b64)} chars)")
            
            cap.release()
            
            if frames_extraidos == 0:
                logger.error("No se pudo extraer ningún frame del video")
                return None
            
            logger.info(f"✅ {frames_extraidos} frames extraídos exitosamente")
            return frames_base64
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo frames: {str(e)}")
            return None
        finally:
            # Asegurar que el video se cierre
            if 'cap' in locals():
                cap.release()
    
    def get_video_info(self, video_path: str) -> Optional[dict]:
        """
        Obtiene información básica del video
        
        Args:
            video_path: Ruta del archivo de video
            
        Returns:
            Dict con información del video o None si falla
        """
        if not self.available:
            return None
        
        try:
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                return None
            
            info = {
                'total_frames': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                'fps': cap.get(cv2.CAP_PROP_FPS),
                'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                'codec': int(cap.get(cv2.CAP_PROP_FOURCC))
            }
            
            info['duracion_segundos'] = info['total_frames'] / info['fps'] if info['fps'] > 0 else 0
            
            cap.release()
            
            return info
            
        except Exception as e:
            logger.error(f"Error obteniendo info del video: {str(e)}")
            return None
