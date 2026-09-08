"""
Servicio de detección de movimiento con OpenCV
Pre-filtra clips antes de enviarlos a análisis costoso
"""
import cv2
import numpy as np
from typing import List, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class MotionSegment:
    """Segmento con movimiento detectado"""
    start_second: float
    end_second: float
    motion_score: float
    frame_count: int

class MotionDetector:
    """Detecta movimiento en videos usando OpenCV (rápido y gratuito)"""
    
    # Intervalo de progreso (cada N frames procesados se loguea)
    PROGRESS_LOG_INTERVAL = 5000
    
    def __init__(
        self,
        motion_threshold: float = 0.008,
        min_segment_duration: float = 1.5,
        blur_size: int = 21,
        gap_tolerance: float = 3.0
    ):
        """
        Args:
            motion_threshold: Umbral de cambio para considerar movimiento (0-1)
            min_segment_duration: Duración mínima de un segmento (segundos)
            blur_size: Tamaño del kernel de blur (debe ser impar)
            gap_tolerance: Segundos de pausa permitidos sin romper un segmento
        """
        self.motion_threshold = motion_threshold
        self.min_segment_duration = min_segment_duration
        self.blur_size = blur_size
        self.gap_tolerance = gap_tolerance
        
    def detect_motion_segments(
        self,
        video_path: str,
        sample_rate: int = 3
    ) -> List[MotionSegment]:
        """
        Detecta segmentos con movimiento significativo
        
        Args:
            video_path: Ruta al video
            sample_rate: Procesar 1 de cada N frames (para velocidad)
            
        Returns:
            Lista de segmentos con movimiento
        """
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            logger.error(f"No se pudo abrir video: {video_path}")
            return []
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        duration_seconds = total_frames / fps if fps > 0 else 0
        duration_str = f"{duration_seconds/3600:.1f}h" if duration_seconds > 3600 else f"{duration_seconds/60:.1f}min"
        frames_to_process = total_frames // sample_rate
        logger.info(f"🔍 Analizando movimiento - FPS: {fps:.1f}, Frames: {total_frames:,}, Duración: {duration_str}")
        logger.info(f"🔍 Frames a procesar (sample_rate={sample_rate}): ~{frames_to_process:,}")
        
        import time as _time
        start_time = _time.time()
        
        segments = []
        current_segment = None
        prev_gray = None
        frame_idx = 0
        processed_count = 0
        last_progress_pct = -1
        
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                    
                # Solo procesar cada N frames
                if frame_idx % sample_rate != 0:
                    frame_idx += 1
                    continue
                
                processed_count += 1
                
                # Log de progreso cada 5% o cada PROGRESS_LOG_INTERVAL frames
                if total_frames > 0:
                    pct = int((frame_idx / total_frames) * 100)
                    if pct >= last_progress_pct + 5 or processed_count % self.PROGRESS_LOG_INTERVAL == 0:
                        elapsed = _time.time() - start_time
                        fps_real = processed_count / max(elapsed, 0.1)
                        remaining = (frames_to_process - processed_count) / max(fps_real, 0.1)
                        current_time_video = frame_idx / fps if fps > 0 else 0
                        logger.info(
                            f"   ⏳ Movimiento: {pct}% | "
                            f"Frame {frame_idx:,}/{total_frames:,} | "
                            f"Segmentos: {len(segments)} | "
                            f"Tiempo video: {current_time_video:.0f}s | "
                            f"Velocidad: {fps_real:.0f} frames/s | "
                            f"ETA: {remaining:.0f}s"
                        )
                        last_progress_pct = pct
                
                # Convertir a escala de grises y aplicar blur
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (self.blur_size, self.blur_size), 0)
                
                if prev_gray is not None:
                    # Calcular diferencia entre frames
                    frame_diff = cv2.absdiff(prev_gray, gray)
                    motion_score = frame_diff.mean() / 255.0  # Normalizar 0-1
                    
                    current_time = frame_idx / fps
                    
                    if motion_score >= self.motion_threshold:
                        # Hay movimiento
                        if current_segment is None:
                            # Iniciar nuevo segmento
                            current_segment = {
                                'start': current_time,
                                'end': current_time,
                                'scores': [motion_score],
                                'frames': 1,
                                'gap_frames': 0  # Contador de frames sin movimiento
                            }
                        else:
                            # Continuar segmento existente
                            current_segment['end'] = current_time
                            current_segment['scores'].append(motion_score)
                            current_segment['frames'] += 1
                            current_segment['gap_frames'] = 0  # Reset gap
                    else:
                        # No hay movimiento
                        if current_segment is not None:
                            # Tolerancia de gap: permitir pausas breves sin romper el segmento
                            gap_seconds = current_time - current_segment['end']
                            if gap_seconds <= self.gap_tolerance:
                                # Todavía dentro de tolerancia, seguir esperando
                                current_segment['gap_frames'] += 1
                            else:
                                # Gap supera tolerancia: finalizar segmento
                                duration = current_segment['end'] - current_segment['start']
                                if duration >= self.min_segment_duration:
                                    avg_score = np.mean(current_segment['scores'])
                                    segments.append(MotionSegment(
                                        start_second=current_segment['start'],
                                        end_second=current_segment['end'],
                                        motion_score=avg_score,
                                        frame_count=current_segment['frames']
                                    ))
                                current_segment = None
                
                prev_gray = gray
                frame_idx += 1
                
            # Finalizar último segmento si existe
            if current_segment is not None:
                duration = current_segment['end'] - current_segment['start']
                if duration >= self.min_segment_duration:
                    avg_score = np.mean(current_segment['scores'])
                    segments.append(MotionSegment(
                        start_second=current_segment['start'],
                        end_second=current_segment['end'],
                        motion_score=avg_score,
                        frame_count=current_segment['frames']
                    ))
                    
        finally:
            cap.release()
        
        elapsed_total = _time.time() - start_time
        total_motion_time = sum(s.end_second - s.start_second for s in segments)
        logger.info(f"✅ ════════════════════════════════════════")
        logger.info(f"✅ Detección de movimiento completada")
        logger.info(f"   📊 Segmentos encontrados: {len(segments)}")
        logger.info(f"   📊 Tiempo con movimiento: {total_motion_time:.1f}s de {duration_seconds:.1f}s ({total_motion_time/max(duration_seconds,1)*100:.1f}%)")
        logger.info(f"   📊 Frames procesados: {processed_count:,}")
        logger.info(f"   📊 Tiempo de análisis: {elapsed_total:.1f}s")
        logger.info(f"   📊 Velocidad: {processed_count/max(elapsed_total,0.1):.0f} frames/s")
        if segments:
            scores = [s.motion_score for s in segments]
            logger.info(f"   📊 Score movimiento: min={min(scores):.3f}, max={max(scores):.3f}, avg={np.mean(scores):.3f}")
        logger.info(f"✅ ════════════════════════════════════════")
        return segments
    
    def detect_scene_changes(
        self,
        video_path: str,
        sample_interval: float = 30.0,
        change_threshold: float = 0.015
    ) -> List[MotionSegment]:
        """
        Detecta cambios ESTÁTICOS en la escena comparando frames a intervalos amplios.
        
        A diferencia de detect_motion_segments (que compara frames consecutivos),
        este método compara frames separados por N segundos para detectar:
        - Objetos que aparecen o desaparecen (abandonados/removidos)
        - Personas que están quietas (no generan movimiento entre frames consecutivos)
        - Cambios de iluminación significativos
        - Puertas/ventanas que se abrieron/cerraron
        
        Args:
            video_path: Ruta al video
            sample_interval: Segundos entre cada comparación (default 30s)
            change_threshold: Umbral de cambio para considerar significativo (0-1)
            
        Returns:
            Lista de segmentos donde se detectaron cambios de escena
        """
        import time as _time
        start_time = _time.time()
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"No se pudo abrir video para scene changes: {video_path}")
            return []
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        if duration < sample_interval * 2:
            cap.release()
            return []
        
        logger.info(f"🔎 Detección de cambios de escena - intervalo: {sample_interval}s, umbral: {change_threshold}")
        
        scene_changes = []
        prev_gray = None
        prev_time = 0.0
        samples_checked = 0
        
        # Recorrer el video a intervalos de sample_interval segundos
        t = 0.0
        while t < duration:
            frame_idx = int(t * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            
            if not ret:
                t += sample_interval
                continue
            
            # Redimensionar para comparación rápida
            small = cv2.resize(frame, (320, 240))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (self.blur_size, self.blur_size), 0)
            
            if prev_gray is not None:
                # Comparar con el frame anterior (separado por sample_interval segundos)
                diff = cv2.absdiff(prev_gray, gray)
                change_score = diff.mean() / 255.0
                
                if change_score >= change_threshold:
                    # Cambio significativo de escena detectado
                    # Crear segmento centrado en el momento del cambio
                    seg_start = max(0, t - 5)
                    seg_end = min(t + 15, duration)
                    scene_changes.append(MotionSegment(
                        start_second=seg_start,
                        end_second=seg_end,
                        motion_score=change_score,
                        frame_count=1
                    ))
            
            prev_gray = gray
            prev_time = t
            samples_checked += 1
            t += sample_interval
        
        cap.release()
        
        elapsed = _time.time() - start_time
        logger.info(f"🔎 Scene changes: {len(scene_changes)} cambios en {samples_checked} muestras ({elapsed:.1f}s)")
        
        return scene_changes
    
    def calculate_motion_percentage(self, video_path: str) -> float:
        """
        Calcula porcentaje del video con movimiento significativo
        
        Returns:
            Porcentaje (0-100) del video con movimiento
        """
        segments = self.detect_motion_segments(video_path)
        
        if not segments:
            return 0.0
            
        cap = cv2.VideoCapture(video_path)
        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        
        total_motion_time = sum(seg.end_second - seg.start_second for seg in segments)
        return (total_motion_time / duration) * 100 if duration > 0 else 0.0
