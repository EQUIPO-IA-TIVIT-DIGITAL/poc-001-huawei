"""
Escáner Denso de Video para Seguridad — Nivel 0 del Pipeline

Escanea el 100% del video con múltiples capas de detección:
1. Diferencia absoluta entre frames (movimiento)
2. Background Subtraction MOG2 (personas/objetos estáticos)
3. Detección de contornos (clasificación por tamaño)
4. Análisis de zonas (bordes = entradas/salidas)
5. Análisis temporal multi-referencia (objeto abandonado, persona quieta)

Produce un mapa temporal completo de actividad que alimenta al clasificador
de eventos (Nivel 1) antes de enviar clips a la IA local.

Resolución de análisis: 320x240 (rápido, suficiente para detección) 
Intervalo de muestreo: 1 frame cada 0.5 segundos
Para 10.7h de video → ~77,000 frames analizados en ~3-8 minutos
"""

import cv2
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import logging
import time

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# ESTRUCTURAS DE DATOS
# ═══════════════════════════════════════════════════════════════

@dataclass
class FrameAnalysis:
    """Resultado del análisis de un frame individual"""
    timestamp: float  # Segundo en el video
    motion_score: float  # Diferencia absoluta normalizada (0-1)
    foreground_pct: float  # % del frame que es foreground (MOG2)
    contour_count: int  # Número de contornos significativos
    largest_contour_area: float  # Área del contorno más grande (% del frame)
    zone_activity: Dict[str, float]  # Actividad por zona (top/bottom/left/right/center)
    scene_change_score: float  # Cambio vs frame de referencia (30s atrás)


@dataclass 
class DetectedEvent:
    """Evento detectado por el escáner denso, clasificado por tipo"""
    start_second: float
    end_second: float
    event_type: str  # MOVEMENT, STATIC_PRESENCE, OBJECT_CHANGE, ENTRY_EXIT, SCENE_CHANGE
    priority: str  # HIGH, MEDIUM, LOW
    max_motion_score: float
    avg_motion_score: float
    max_foreground_pct: float
    contour_info: Dict  # {max_count, avg_area, max_area}
    active_zones: List[str]  # Zonas con más actividad
    frame_count: int
    details: Dict = field(default_factory=dict)  # Detalles adicionales según tipo


# ═══════════════════════════════════════════════════════════════
# ESCÁNER DENSO
# ═══════════════════════════════════════════════════════════════

class DenseVideoScanner:
    """
    Escáner denso multinivel para cobertura 100% del video.
    
    Analiza 1 frame cada 0.5 segundos con 5 capas de detección simultáneas.
    Todo el procesamiento es local con OpenCV (costo $0).
    """
    
    # Resolución de análisis (bajo para velocidad)
    SCAN_RESOLUTION = (320, 240)
    SCAN_AREA = 320 * 240  # Para cálculos de porcentaje de área
    
    # Umbrales de detección
    MOTION_THRESHOLD = 0.008  # Diferencia absoluta mínima
    FOREGROUND_THRESHOLD = 0.5  # % mínimo de foreground para considerar presencia
    CONTOUR_MIN_AREA = 0.005  # Área mínima de contorno (% del frame)
    CONTOUR_PERSON_AREA = 0.02  # Área mínima para considerar "persona" (% del frame)
    SCENE_CHANGE_THRESHOLD = 0.025  # Cambio vs referencia de 30s
    BORDER_ZONE_WIDTH = 0.15  # 15% de cada borde = zona de entrada/salida
    
    # Configuración de escaneo
    SAMPLE_INTERVAL = 0.5  # Segundos entre muestras (2 frames por segundo)
    REFERENCE_INTERVAL = 30.0  # Segundos entre frames de referencia
    
    # MOG2 config
    MOG2_HISTORY = 500
    MOG2_THRESHOLD = 16
    MOG2_DETECT_SHADOWS = True
    
    # Progreso
    PROGRESS_INTERVAL = 5  # Log cada 5%
    
    def __init__(
        self,
        sample_interval: float = 0.5,
        motion_threshold: float = 0.008,
        reference_interval: float = 30.0
    ):
        self.sample_interval = sample_interval
        self.motion_threshold = motion_threshold
        self.reference_interval = reference_interval
    
    def scan_video(self, video_path: str, video_id: str = "") -> List[FrameAnalysis]:
        """
        Escaneo denso completo del video.
        
        Analiza cada frame a intervalos de sample_interval segundos
        con 5 capas de detección simultáneas.
        
        Args:
            video_path: Ruta al archivo de video
            video_id: ID del video para trazabilidad en logs
            
        Returns:
            Lista de FrameAnalysis con el mapa temporal completo
        """
        pfx = f"[{video_id[:8]}] " if video_id else ""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"{pfx}No se pudo abrir video: {video_path}")
            return []
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        if duration <= 0:
            cap.release()
            return []
        
        total_samples = int(duration / self.sample_interval)
        duration_str = f"{duration/3600:.1f}h" if duration > 3600 else f"{duration/60:.1f}min"
        
        logger.info(f"{pfx}🔬 ═════════════════════════════════════════════════")
        logger.info(f"{pfx}🔬 ESCÁNER DENSO MULTINIVEL — Cobertura 100%")
        logger.info(f"{pfx}🔬 ═════════════════════════════════════════════════")
        logger.info(f"{pfx}   📹 Video: {duration_str} ({duration:.0f}s), {fps:.0f}fps, {total_frames:,} frames")
        logger.info(f"{pfx}   🔍 Muestras a analizar: {total_samples:,} (cada {self.sample_interval}s)")
        logger.info(f"{pfx}   📐 Resolución análisis: {self.SCAN_RESOLUTION[0]}x{self.SCAN_RESOLUTION[1]}")
        logger.info(f"{pfx}   🧠 Capas: diff + MOG2 + contornos + zonas + temporal")
        
        start_time = time.time()
        
        # Inicializar Background Subtractor MOG2
        bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=self.MOG2_HISTORY,
            varThreshold=self.MOG2_THRESHOLD,
            detectShadows=self.MOG2_DETECT_SHADOWS
        )
        
        analyses: List[FrameAnalysis] = []
        prev_gray = None
        reference_gray = None  # Frame de referencia (actualizado cada 30s)
        reference_time = -self.reference_interval  # Forzar primera referencia
        last_progress_pct = -1
        
        # Iterar sobre el video a intervalos regulares
        t = 0.0
        sample_count = 0
        
        while t < duration:
            # Posicionar en el frame correcto
            frame_idx = int(t * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            
            if not ret:
                t += self.sample_interval
                continue
            
            sample_count += 1
            
            # Progreso
            pct = int((t / duration) * 100)
            if pct >= last_progress_pct + self.PROGRESS_INTERVAL:
                elapsed = time.time() - start_time
                speed = sample_count / max(elapsed, 0.1)
                remaining = (total_samples - sample_count) / max(speed, 0.1)
                logger.info(
                    f"{pfx}   ⏳ Escaneo: {pct}% | "
                    f"t={t:.0f}s/{duration:.0f}s | "
                    f"Muestras: {sample_count:,}/{total_samples:,} | "
                    f"Velocidad: {speed:.0f}/s | "
                    f"ETA: {remaining:.0f}s"
                )
                last_progress_pct = pct
            
            # ── Preparar frame para análisis ──
            small = cv2.resize(frame, self.SCAN_RESOLUTION)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            gray_blurred = cv2.GaussianBlur(gray, (21, 21), 0)
            
            # ══ CAPA 1: Diferencia absoluta (movimiento) ══
            motion_score = 0.0
            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray_blurred)
                motion_score = diff.mean() / 255.0
            
            # ══ CAPA 2: Background Subtraction MOG2 ══
            fg_mask = bg_subtractor.apply(small)
            # Eliminar sombras (valor 127) y quedarse solo con foreground real (255)
            fg_binary = (fg_mask == 255).astype(np.uint8) * 255
            # Limpiar ruido
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            fg_clean = cv2.morphologyEx(fg_binary, cv2.MORPH_OPEN, kernel)
            fg_clean = cv2.morphologyEx(fg_clean, cv2.MORPH_CLOSE, kernel)
            foreground_pct = (fg_clean > 0).sum() / self.SCAN_AREA * 100
            
            # ══ CAPA 3: Detección de contornos ══
            contours, _ = cv2.findContours(
                fg_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            # Filtrar contornos por tamaño mínimo
            min_area_px = self.CONTOUR_MIN_AREA * self.SCAN_AREA
            significant_contours = [
                c for c in contours if cv2.contourArea(c) >= min_area_px
            ]
            contour_count = len(significant_contours)
            largest_contour_area = 0.0
            if significant_contours:
                largest_area_px = max(cv2.contourArea(c) for c in significant_contours)
                largest_contour_area = largest_area_px / self.SCAN_AREA * 100
            
            # ══ CAPA 4: Análisis de zonas ══
            h, w = self.SCAN_RESOLUTION[1], self.SCAN_RESOLUTION[0]
            border_h = int(h * self.BORDER_ZONE_WIDTH)
            border_w = int(w * self.BORDER_ZONE_WIDTH)
            
            zone_activity = {}
            # Bordes (entradas/salidas)
            zone_activity['top'] = float(fg_clean[0:border_h, :].mean() / 255.0 * 100)
            zone_activity['bottom'] = float(fg_clean[h-border_h:h, :].mean() / 255.0 * 100)
            zone_activity['left'] = float(fg_clean[:, 0:border_w].mean() / 255.0 * 100)
            zone_activity['right'] = float(fg_clean[:, w-border_w:w].mean() / 255.0 * 100)
            # Centro
            zone_activity['center'] = float(
                fg_clean[border_h:h-border_h, border_w:w-border_w].mean() / 255.0 * 100
            )
            
            # ══ CAPA 5: Análisis temporal (cambio vs referencia) ══
            scene_change_score = 0.0
            if reference_gray is not None:
                ref_diff = cv2.absdiff(reference_gray, gray_blurred)
                scene_change_score = ref_diff.mean() / 255.0
            
            # Actualizar frame de referencia cada N segundos
            if t - reference_time >= self.reference_interval:
                reference_gray = gray_blurred.copy()
                reference_time = t
            
            # ── Guardar resultado ──
            analyses.append(FrameAnalysis(
                timestamp=t,
                motion_score=motion_score,
                foreground_pct=foreground_pct,
                contour_count=contour_count,
                largest_contour_area=largest_contour_area,
                zone_activity=zone_activity,
                scene_change_score=scene_change_score
            ))
            
            prev_gray = gray_blurred.copy()
            t += self.sample_interval
        
        cap.release()
        
        elapsed = time.time() - start_time
        speed = sample_count / max(elapsed, 0.1)
        
        # Estadísticas del escaneo
        if analyses:
            motion_scores = [a.motion_score for a in analyses if a.motion_score > 0]
            fg_scores = [a.foreground_pct for a in analyses]
            active_frames = sum(1 for a in analyses if 
                               a.motion_score >= self.MOTION_THRESHOLD or
                               a.foreground_pct >= self.FOREGROUND_THRESHOLD)
            
            logger.info(f"{pfx}✅ ═════════════════════════════════════════════════")
            logger.info(f"{pfx}✅ ESCANEO DENSO COMPLETADO")
            logger.info(f"{pfx}   📊 Muestras analizadas: {sample_count:,}")
            logger.info(f"{pfx}   📊 Tiempo de escaneo: {elapsed:.1f}s ({speed:.0f} muestras/s)")
            logger.info(f"{pfx}   📊 Frames con actividad: {active_frames:,} ({active_frames/max(sample_count,1)*100:.1f}%)")
            if motion_scores:
                logger.info(f"{pfx}   📊 Motion score: min={min(motion_scores):.4f}, "
                           f"max={max(motion_scores):.4f}, avg={np.mean(motion_scores):.4f}")
            logger.info(f"{pfx}   📊 Foreground avg: {np.mean(fg_scores):.2f}%")
            logger.info(f"{pfx}✅ ═════════════════════════════════════════════════")
        
        return analyses
    
    def classify_events(
        self,
        analyses: List[FrameAnalysis],
        video_duration: float,
        video_id: str = ""
    ) -> List[DetectedEvent]:
        """
        Nivel 1: Clasifica los resultados del escaneo denso en eventos tipados.
        
        Agrupa frames contiguos con actividad en eventos y les asigna:
        - Tipo (MOVEMENT, STATIC_PRESENCE, OBJECT_CHANGE, ENTRY_EXIT, SCENE_CHANGE)
        - Prioridad (HIGH, MEDIUM, LOW)
        - Metadatos de las capas de detección
        
        Args:
            analyses: Lista de FrameAnalysis del escaneo denso
            video_duration: Duración total del video en segundos
            video_id: ID del video para trazabilidad en logs
            
        Returns:
            Lista de DetectedEvent ordenados cronológicamente
        """
        pfx = f"[{video_id[:8]}] " if video_id else ""
        if not analyses:
            return []
        
        logger.info(f"{pfx}🏷️ ═══════════════════════════════════════════")
        logger.info(f"{pfx}🏷️ CLASIFICACIÓN DE EVENTOS (Nivel 1)")
        logger.info(f"{pfx}🏷️ ═══════════════════════════════════════════")
        
        events: List[DetectedEvent] = []
        
        # ── Paso 1: Identificar frames "activos" ──
        # Un frame es activo si CUALQUIER capa detecta algo significativo
        active_frames = []
        for a in analyses:
            is_active = False
            activity_reasons = []
            
            if a.motion_score >= self.MOTION_THRESHOLD:
                is_active = True
                activity_reasons.append('motion')
            
            if a.foreground_pct >= self.FOREGROUND_THRESHOLD:
                is_active = True
                activity_reasons.append('foreground')
            
            if a.contour_count > 0 and a.largest_contour_area >= self.CONTOUR_MIN_AREA * 100:
                is_active = True
                activity_reasons.append('contour')
            
            if a.scene_change_score >= self.SCENE_CHANGE_THRESHOLD:
                is_active = True
                activity_reasons.append('scene_change')
            
            # Actividad en bordes (entrada/salida)
            border_activity = max(
                a.zone_activity.get('top', 0),
                a.zone_activity.get('bottom', 0),
                a.zone_activity.get('left', 0),
                a.zone_activity.get('right', 0)
            )
            if border_activity >= 2.0:  # >2% de foreground en un borde
                is_active = True
                activity_reasons.append('border')
            
            if is_active:
                active_frames.append((a, activity_reasons))
        
        logger.info(f"{pfx}   📊 Frames activos: {len(active_frames)}/{len(analyses)} "
                    f"({len(active_frames)/max(len(analyses),1)*100:.1f}%)")
        
        if not active_frames:
            logger.info(f"{pfx}   ℹ️ No se detectó actividad significativa")
            return []
        
        # ── Paso 2: Agrupar frames activos en eventos continuos ──
        # Permitir gap de hasta 3 segundos sin romper el evento
        GAP_TOLERANCE = 3.0
        MIN_EVENT_DURATION = 1.0  # Mínimo 1 segundo para ser evento
        
        raw_events = []
        current_group = [active_frames[0]]
        
        for i in range(1, len(active_frames)):
            prev_t = active_frames[i-1][0].timestamp
            curr_t = active_frames[i][0].timestamp
            
            if curr_t - prev_t <= GAP_TOLERANCE:
                current_group.append(active_frames[i])
            else:
                raw_events.append(current_group)
                current_group = [active_frames[i]]
        
        raw_events.append(current_group)  # Último grupo
        
        logger.info(f"{pfx}   📊 Grupos de actividad: {len(raw_events)}")
        
        # ── Paso 3: Clasificar cada grupo como un tipo de evento ──
        for group in raw_events:
            frames_in_group = [g[0] for g in group]
            reasons_in_group = [g[1] for g in group]
            
            start_t = frames_in_group[0].timestamp
            end_t = frames_in_group[-1].timestamp
            duration = end_t - start_t
            
            if duration < MIN_EVENT_DURATION and len(frames_in_group) < 3:
                continue  # Demasiado corto, probablemente ruido
            
            # Agregar al menos sample_interval para que end > start
            if end_t <= start_t:
                end_t = start_t + self.SAMPLE_INTERVAL
            
            # Calcular métricas agregadas
            motion_scores = [f.motion_score for f in frames_in_group]
            fg_pcts = [f.foreground_pct for f in frames_in_group]
            contour_counts = [f.contour_count for f in frames_in_group]
            contour_areas = [f.largest_contour_area for f in frames_in_group]
            scene_scores = [f.scene_change_score for f in frames_in_group]
            
            # Razones más comunes en el grupo
            all_reasons = [r for reasons in reasons_in_group for r in reasons]
            reason_counts = {}
            for r in all_reasons:
                reason_counts[r] = reason_counts.get(r, 0) + 1
            
            # Zonas activas
            zone_totals = {'top': 0, 'bottom': 0, 'left': 0, 'right': 0, 'center': 0}
            for f in frames_in_group:
                for zone, val in f.zone_activity.items():
                    zone_totals[zone] += val
            active_zones = [z for z, v in zone_totals.items() if v > len(frames_in_group) * 1.0]
            
            # ── Determinar tipo de evento ──
            event_type = self._classify_event_type(
                reason_counts, motion_scores, fg_pcts, 
                contour_areas, scene_scores, active_zones, duration
            )
            
            # ── Determinar prioridad ──
            priority = self._calculate_priority(
                event_type, max(motion_scores), max(fg_pcts),
                max(contour_areas), max(scene_scores), active_zones, duration
            )
            
            events.append(DetectedEvent(
                start_second=start_t,
                end_second=end_t,
                event_type=event_type,
                priority=priority,
                max_motion_score=max(motion_scores),
                avg_motion_score=float(np.mean(motion_scores)),
                max_foreground_pct=max(fg_pcts),
                contour_info={
                    'max_count': max(contour_counts),
                    'avg_area': float(np.mean(contour_areas)) if contour_areas else 0,
                    'max_area': max(contour_areas) if contour_areas else 0
                },
                active_zones=active_zones,
                frame_count=len(frames_in_group),
                details={
                    'reason_counts': reason_counts,
                    'avg_scene_change': float(np.mean(scene_scores)) if scene_scores else 0,
                    'avg_foreground': float(np.mean(fg_pcts)) if fg_pcts else 0
                }
            ))
        
        # Estadísticas de clasificación
        type_counts = {}
        priority_counts = {}
        for ev in events:
            type_counts[ev.event_type] = type_counts.get(ev.event_type, 0) + 1
            priority_counts[ev.priority] = priority_counts.get(ev.priority, 0) + 1
        
        total_event_time = sum(e.end_second - e.start_second for e in events)
        coverage_pct = (total_event_time / max(video_duration, 1)) * 100
        
        # Calcular gap máximo
        max_gap = 0
        sorted_events = sorted(events, key=lambda e: e.start_second)
        prev_end = 0
        for ev in sorted_events:
            gap = ev.start_second - prev_end
            max_gap = max(max_gap, gap)
            prev_end = ev.end_second
        if video_duration > 0:
            max_gap = max(max_gap, video_duration - prev_end)
        
        logger.info(f"{pfx}✅ ═════════════════════════════════════════════════")
        logger.info(f"{pfx}✅ CLASIFICACIÓN COMPLETADA")
        logger.info(f"{pfx}   📊 Eventos detectados: {len(events)}")
        logger.info(f"{pfx}   📊 Por tipo: {type_counts}")
        logger.info(f"{pfx}   📊 Por prioridad: {priority_counts}")
        logger.info(f"{pfx}   📊 Tiempo con eventos: {total_event_time:.0f}s ({coverage_pct:.1f}%)")
        logger.info(f"{pfx}   📊 Gap máximo sin evento: {max_gap:.0f}s ({max_gap/60:.1f}min)")
        logger.info(f"{pfx}✅ ═════════════════════════════════════════════════")
        
        return sorted_events
    
    def _classify_event_type(
        self,
        reason_counts: Dict[str, int],
        motion_scores: List[float],
        fg_pcts: List[float],
        contour_areas: List[float],
        scene_scores: List[float],
        active_zones: List[str],
        duration: float
    ) -> str:
        """Clasifica el tipo de evento basado en las capas de detección"""
        
        has_motion = 'motion' in reason_counts
        has_foreground = 'foreground' in reason_counts
        has_contour = 'contour' in reason_counts
        has_scene_change = 'scene_change' in reason_counts
        has_border = 'border' in reason_counts
        
        avg_motion = float(np.mean(motion_scores))
        max_fg = max(fg_pcts) if fg_pcts else 0
        max_contour = max(contour_areas) if contour_areas else 0
        
        # ENTRY_EXIT: Actividad significativa en bordes del frame
        border_zones = [z for z in active_zones if z in ('top', 'bottom', 'left', 'right')]
        if has_border and has_motion and len(border_zones) >= 1:
            return 'ENTRY_EXIT'
        
        # MOVEMENT: Movimiento activo (diferencia entre frames consecutivos)
        if has_motion and avg_motion >= self.MOTION_THRESHOLD * 2:
            return 'MOVEMENT'
        
        # STATIC_PRESENCE: Hay foreground (persona/objeto) pero poco movimiento
        if has_foreground and max_contour >= self.CONTOUR_PERSON_AREA * 100:
            if not has_motion or avg_motion < self.MOTION_THRESHOLD * 3:
                return 'STATIC_PRESENCE'
        
        # OBJECT_CHANGE: Cambio vs referencia sin movimiento continuo
        if has_scene_change and not has_motion:
            return 'OBJECT_CHANGE'
        
        # SCENE_CHANGE: Cambio grande en la escena (puede ser iluminación o manipulación)
        if has_scene_change and max(scene_scores) >= self.SCENE_CHANGE_THRESHOLD * 2:
            return 'SCENE_CHANGE'
        
        # Default: MOVEMENT si hay cualquier tipo de actividad
        if has_motion:
            return 'MOVEMENT'
        
        return 'SCENE_CHANGE'
    
    def _calculate_priority(
        self,
        event_type: str,
        max_motion: float,
        max_fg: float,
        max_contour_area: float,
        max_scene_change: float,
        active_zones: List[str],
        duration: float
    ) -> str:
        """Calcula la prioridad del evento"""
        
        # ENTRY_EXIT siempre es al menos MEDIUM
        if event_type == 'ENTRY_EXIT':
            if max_contour_area >= self.CONTOUR_PERSON_AREA * 100:
                return 'HIGH'
            return 'MEDIUM'
        
        # MOVEMENT: prioridad por intensidad y duración
        if event_type == 'MOVEMENT':
            if max_motion >= 0.05 or duration >= 15:
                return 'HIGH'
            if max_motion >= 0.02 or duration >= 5:
                return 'MEDIUM'
            return 'LOW'
        
        # STATIC_PRESENCE: persona quieta es sospechoso
        if event_type == 'STATIC_PRESENCE':
            if duration >= 30:  # >30s quieto
                return 'HIGH'
            if duration >= 10:
                return 'MEDIUM'
            return 'LOW'
        
        # OBJECT_CHANGE: objeto que aparece/desaparece
        if event_type == 'OBJECT_CHANGE':
            if max_contour_area >= self.CONTOUR_PERSON_AREA * 100:
                return 'HIGH'
            return 'MEDIUM'
        
        # SCENE_CHANGE
        if max_scene_change >= 0.05:
            return 'HIGH'
        return 'LOW'
    
    def events_to_segments(
        self,
        events: List[DetectedEvent],
        video_duration: float,
        max_segment_duration: float = 30.0,
        max_segments: int = 400,
        video_id: str = ""
     ) -> list:  # List[MotionSegment] — MotionSegment importado lazy dentro del método
        """
        Convierte DetectedEvents del escáner en MotionSegments
        compatibles con el pipeline existente (clip extraction + IA local).
        
        Estrategia:
        - Subdivide eventos largos en ventanas de ~30s
        - Añade buffer de contexto
        - Prioriza eventos HIGH > MEDIUM > LOW si excede límite
        
        Args:
            events: Lista de DetectedEvent del clasificador
            video_duration: Duración total del video
            max_segment_duration: Duración máxima de cada segmento
            max_segments: Límite máximo de segmentos
            
        Returns:
            Lista de MotionSegment para el pipeline de clips
        """
        from .motion_detector import MotionSegment
        
        pfx = f"[{video_id[:8]}] " if video_id else ""
        if not events:
            return []
        
        logger.info(f"{pfx}🔄 Convirtiendo {len(events)} eventos en segmentos de análisis...")
        
        segments = []
        
        for ev in events:
            duration = ev.end_second - ev.start_second
            
            # Codificar tipo y prioridad en el motion_score para el pipeline
            # Score > 0.1: movimiento real
            # Score 0.01-0.099: presencia estática / cambio de escena  
            # Score < 0.01: muestreo periódico
            if ev.event_type == 'MOVEMENT':
                base_score = max(ev.max_motion_score, 0.01)
            elif ev.event_type == 'ENTRY_EXIT':
                base_score = max(ev.max_motion_score, 0.015)
            elif ev.event_type == 'STATIC_PRESENCE':
                base_score = 0.003  # Indica presencia estática
            elif ev.event_type == 'OBJECT_CHANGE':
                base_score = 0.004  # Indica cambio de objeto
            else:  # SCENE_CHANGE
                base_score = 0.002
            
            if duration <= max_segment_duration * 2:
                segments.append(MotionSegment(
                    start_second=ev.start_second,
                    end_second=ev.end_second,
                    motion_score=base_score,
                    frame_count=ev.frame_count
                ))
            else:
                # Subdividir eventos largos
                n_windows = int(duration / max_segment_duration) + 1
                window_size = duration / n_windows
                for i in range(n_windows):
                    sub_start = ev.start_second + (i * window_size)
                    sub_end = min(sub_start + window_size, ev.end_second)
                    segments.append(MotionSegment(
                        start_second=sub_start,
                        end_second=sub_end,
                        motion_score=base_score,
                        frame_count=max(1, ev.frame_count // n_windows)
                    ))
        
        # Ordenar cronológicamente
        segments.sort(key=lambda s: s.start_second)
        
        # Aplicar límite si excede
        if len(segments) > max_segments:
            logger.info(f"{pfx}   ⚠️ {len(segments)} segmentos excede límite de {max_segments}")
            
            # Separar por prioridad (usando score como proxy)
            high = [s for s in segments if s.motion_score >= 0.015]
            medium = [s for s in segments if 0.002 <= s.motion_score < 0.015]
            low = [s for s in segments if s.motion_score < 0.002]
            
            # Budget: 60% HIGH, 30% MEDIUM, 10% LOW
            high_budget = int(max_segments * 0.6)
            med_budget = int(max_segments * 0.3)
            low_budget = max_segments - high_budget - med_budget
            
            # Seleccionar uniformemente de cada grupo
            selected = (
                self._uniform_select(high, high_budget) +
                self._uniform_select(medium, med_budget) +
                self._uniform_select(low, low_budget)
            )
            selected.sort(key=lambda s: s.start_second)
            segments = selected
            
            logger.info(f"{pfx}   📊 Recortado a {len(segments)} segmentos")
        
        # Calcular métricas finales
        total_time = sum(s.end_second - s.start_second for s in segments)
        coverage = (total_time / max(video_duration, 1)) * 100
        
        # Gap máximo
        max_gap = 0
        prev_end = 0
        for seg in segments:
            gap = seg.start_second - prev_end
            max_gap = max(max_gap, gap)
            prev_end = seg.end_second
        if video_duration > 0:
            max_gap = max(max_gap, video_duration - prev_end)
        
        logger.info(f"{pfx}✅ Segmentos para análisis: {len(segments)}")
        logger.info(f"{pfx}   📊 Tiempo total: {total_time:.0f}s ({coverage:.1f}% del video)")
        logger.info(f"{pfx}   📊 Gap máximo: {max_gap:.0f}s ({max_gap/60:.1f}min)")
        
        return segments
    
    def _uniform_select(self, items: list, budget: int) -> list:
        """Selecciona uniformemente distribuidos de una lista"""
        if len(items) <= budget:
            return items
        if budget <= 0:
            return []
        step = len(items) / budget
        return [items[int(i * step)] for i in range(budget)]
