import os
import time
import uuid
import logging
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed

# Try importing domain entities, assuming they are available
from domain.entities import SecurityVideo
from infrastructure.services.motion_detector import MotionSegment

logger = logging.getLogger(__name__)

class SecurityVideoGeminiAnalyzer:
    """Extrae la lógica de análisis con Gemini y extracción multimedia"""
    
    HD_RESOLUTION = (1280, 720)
    MAX_FRAMES_PER_SEGMENT = 5
    MAX_CLIP_DURATION = 120
    CLIP_BUFFER_SECONDS = 3.0

    def __init__(self, gemini_adapter, storage_adapter, optimized_processor, get_temp_dir_func, update_progress_func):
        self.gemini_adapter = gemini_adapter
        self.storage_adapter = storage_adapter
        self.optimized_processor = optimized_processor
        self.get_temp_dir = get_temp_dir_func
        self.update_progress = update_progress_func
        # This will be injected by the orchestrator
        self.events_map = {}

    def analyze_all_segments(self, video_id: str, video_path: str, segments: List[MotionSegment], video: SecurityVideo) -> List[Dict[str, Any]]:
        all_events = []
        failed_segments = []
        total = len(segments)
        phase_start = time.time()
        vid = video_id[:8]

        logger.info(f"[{vid}] 🔬 Iniciando análisis de {total} segmentos con Gemini")
        
        for idx, segment in enumerate(segments):
            try:
                seg_start = time.time()
                detected_ev = self.events_map.get(segment.start_second)
                ev_type = detected_ev.event_type if detected_ev else 'UNKNOWN'
                ev_priority = detected_ev.priority if detected_ev else '-'
                
                segment_progress = int(30 + (idx / total) * 50)
                self.update_progress(
                    video=video,
                    message=f"Analizando segmento {idx+1}/{total}",
                    progress_pct=segment_progress,
                    fase='analisis',
                    paso_actual=idx + 1,
                    total_pasos=total
                )
                
                event_data = self.analyze_single_segment(video_id, video_path, segment, idx, video)
                seg_elapsed = time.time() - seg_start
                
                if event_data:
                    all_events.append(event_data)
                else:
                    failed_segments.append({
                        'index': idx,
                        'start': segment.start_second,
                        'end': segment.end_second,
                        'reason': 'empty_result',
                        'motion_score': segment.motion_score,
                        'duration': seg_elapsed
                    })
                
                if idx < total - 1:
                    if seg_elapsed > 10: time.sleep(0.3)
                    elif seg_elapsed > 5: time.sleep(0.5)
                    else: time.sleep(0.8)
                    
            except Exception as e:
                logger.error(f"[{vid}] ❌ Error en segmento {idx}: {e}")
                failed_segments.append({
                    'index': idx,
                    'start': segment.start_second,
                    'end': segment.end_second,
                    'reason': str(e)[:200],
                    'motion_score': segment.motion_score,
                    'error_type': type(e).__name__
                })
        
        if failed_segments:
            video.metadata_tecnico['segmentos_fallidos'] = failed_segments
        
        return sorted(all_events, key=lambda x: x['timestamp_inicio'])

    def analyze_single_segment(self, video_id: str, video_path: str, segment: MotionSegment, segment_index: int, video: SecurityVideo) -> Optional[Dict[str, Any]]:
        import cv2
        import base64
        
        temp_dir = self.get_temp_dir()
        clip_path = None
        vid = video_id[:8]
        
        try:
            clip_start_time = time.time()
            clip_duration = segment.end_second - segment.start_second
            effective_end = segment.end_second
            if clip_duration > self.MAX_CLIP_DURATION:
                effective_end = segment.start_second + self.MAX_CLIP_DURATION
            
            clip_start = max(0, segment.start_second - self.CLIP_BUFFER_SECONDS)
            clip_end = effective_end + self.CLIP_BUFFER_SECONDS
            
            clip_path = self.extract_clip_ffmpeg(video_path, clip_start, clip_end, os.path.join(temp_dir, f"clip_{segment_index}.mp4"))
            
            if not clip_path or not os.path.exists(clip_path):
                return self.analyze_segment_frames_only(video_id, video_path, segment, segment_index, video)
            
            clip_size_mb = os.path.getsize(clip_path) / (1024 * 1024)
            frames_hd = self.extract_hd_frames(video_path, segment.start_second, effective_end, max_frames=self.MAX_FRAMES_PER_SEGMENT)
            
            frames_b64 = []
            frames_paths = []
            if frames_hd:
                for i, frame in enumerate(frames_hd):
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    frames_b64.append(base64.b64encode(buffer).decode('utf-8'))
                    frame_path = os.path.join(temp_dir, f"frame_{segment_index}_{i}.jpg")
                    cv2.imwrite(frame_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    frames_paths.append(frame_path)
            
            gemini_analysis = self.analyze_clip_with_gemini(clip_path, segment, frames_b64, video)
            
            frames_urls = self.upload_frames_to_gcs(video_id, segment_index, frames_paths)
            
            analysis_data = gemini_analysis.get('analisis', {}) if gemini_analysis.get('success') else {}
            
            return {
                'id': f"ev_{video_id}_{segment_index}_{uuid.uuid4().hex[:6]}",
                'security_video_id': video_id,
                'timestamp_inicio': segment.start_second,
                'timestamp_fin': segment.end_second,
                'duracion': segment.end_second - segment.start_second,
                'descripcion': analysis_data.get('descripcion_escena', analysis_data.get('description', 'Evento detectado')),
                'objetos_detectados': analysis_data.get('objetos_detectados', analysis_data.get('visible_objects', [])),
                'acciones_detectadas': analysis_data.get('acciones_detectadas', analysis_data.get('main_actions', [])),
                'personas_count': analysis_data.get('personas_estimadas', analysis_data.get('estimated_persons', 0)),
                'vehiculos_count': analysis_data.get('vehiculos_estimados', analysis_data.get('estimated_vehicles', 0)),
                'nivel_riesgo': analysis_data.get('nivel_riesgo', 'BAJO'),
                'razon_riesgo': analysis_data.get('razon_riesgo', ''),
                'confianza': min(max(analysis_data.get('confianza', 50) / 100.0, 0.0), 1.0),
                'frames_urls': frames_urls,
                'analisis_detallado': {
                    'gemini_video': analysis_data,
                    'motion_score': segment.motion_score,
                    'tipo_analisis': 'video_clip',
                    'tokens_usados': gemini_analysis.get('tokens_usados')
                },
                'metadata': {
                    'frames_guardados': len(frames_urls),
                    'clip_size_mb': clip_size_mb,
                    'motion_score': segment.motion_score,
                    'segment_index': segment_index,
                    'resolucion_frames': '1280x720',
                    'analisis_tipo': 'video_clip_gemini'
                }
            }
        except Exception as e:
            logger.error(f"[{vid}] Error analizando segmento {segment_index}: {e}")
            return None
        finally:
            if clip_path and os.path.exists(clip_path):
                try: os.remove(clip_path)
                except: pass

    def analyze_segment_frames_only(self, video_id: str, video_path: str, segment: MotionSegment, segment_index: int, video: SecurityVideo) -> Optional[Dict[str, Any]]:
        import cv2
        import base64
        try:
            frames_hd = self.extract_hd_frames(video_path, segment.start_second, segment.end_second, max_frames=8)
            if not frames_hd: return None
            
            frames_b64 = []
            for frame in frames_hd:
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                frames_b64.append(base64.b64encode(buffer).decode('utf-8'))
            
            prompt = self.build_security_analysis_prompt(segment, video, is_frames_only=True)
            result = self.gemini_adapter.analyze_frames(prompt, frames_b64)
            analysis_data = result.get('analisis', {}) if result.get('success') else {}
            
            return {
                'id': f"ev_{video_id}_{segment_index}_{uuid.uuid4().hex[:6]}",
                'security_video_id': video_id,
                'timestamp_inicio': segment.start_second,
                'timestamp_fin': segment.end_second,
                'duracion': segment.end_second - segment.start_second,
                'descripcion': analysis_data.get('descripcion_escena', 'Evento detectado (análisis de frames)'),
                'objetos_detectados': analysis_data.get('objetos_detectados', []),
                'acciones_detectadas': analysis_data.get('acciones_detectadas', []),
                'personas_count': analysis_data.get('personas_estimadas', 0),
                'vehiculos_count': analysis_data.get('vehiculos_estimados', 0),
                'nivel_riesgo': analysis_data.get('nivel_riesgo', 'BAJO'),
                'razon_riesgo': analysis_data.get('razon_riesgo', ''),
                'confianza': min(max(analysis_data.get('confianza', 30) / 100.0, 0.0), 1.0),
                'frames_urls': [],
                'analisis_detallado': {
                    'gemini_frames': analysis_data,
                    'motion_score': segment.motion_score,
                    'tipo_analisis': 'frames_only_fallback'
                },
                'metadata': {
                    'frames_guardados': 0,
                    'motion_score': segment.motion_score,
                    'segment_index': segment_index,
                    'analisis_tipo': 'frames_fallback'
                }
            }
        except Exception:
            return None

    def extract_clip_ffmpeg(self, video_path: str, start: float, end: float, output_path: str) -> Optional[str]:
        try:
            import subprocess
            duration = end - start
            target_size_mb = 18
            target_bitrate = int((target_size_mb * 8 * 1024) / max(duration, 1))
            target_bitrate = min(max(target_bitrate, 200), 2000)
            
            cmd = [
                "ffmpeg", "-y", "-ss", str(start), "-i", video_path, "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast", "-b:v", f"{target_bitrate}k",
                "-maxrate", f"{target_bitrate * 2}k", "-bufsize", f"{target_bitrate * 4}k",
                "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
                "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result.returncode == 0 and os.path.exists(output_path): return output_path
            return None
        except FileNotFoundError:
            return self.optimized_processor.create_clip(video_path, start, end, output_path)
        except Exception:
            return None

    def extract_hd_frames(self, video_path: str, start: float, end: float, max_frames: int = 5) -> list:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened(): return []
        fps = cap.get(cv2.CAP_PROP_FPS)
        duration = end - start
        if fps <= 0 or duration <= 0: return []
        
        if max_frames == 1: timestamps = [start + duration / 2]
        else:
            interval = duration / (max_frames + 1)
            timestamps = [start + interval * (i + 1) for i in range(max_frames)]
        
        frames = []
        for ts in timestamps:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(ts * fps))
            ret, frame = cap.read()
            if ret: frames.append(cv2.resize(frame, self.HD_RESOLUTION, interpolation=cv2.INTER_LANCZOS4))
        cap.release()
        return frames

    def analyze_clip_with_gemini(self, clip_path: str, segment: MotionSegment, frames_b64: List[str], video: SecurityVideo) -> Dict:
        prompt = self.build_security_analysis_prompt(segment, video, is_frames_only=False)
        return self.gemini_adapter.analyze_video_clip(clip_path=clip_path, prompt=prompt, frames_base64=frames_b64[:3])

    def upload_frames_to_gcs(self, video_id: str, segment_index: int, frame_paths: List[str]) -> List[str]:
        if not frame_paths: return []
        urls = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for i, fp in enumerate(frame_paths):
                if os.path.exists(fp):
                    blob_name = f"security_frames/{video_id}/seg_{segment_index:03d}/frame_{i:02d}.jpg"
                    future = executor.submit(self.storage_adapter.upload_file, fp, blob_name, None, True)
                    futures[future] = i
            for future in as_completed(futures):
                try:
                    url = future.result()
                    if url: urls.append(url)
                except Exception: pass
        return urls

    def build_security_analysis_prompt(self, segment: MotionSegment, video: SecurityVideo, is_frames_only: bool = False) -> str:
        media_type = "frames de imagen" if is_frames_only else "video clip completo"
        
        event_info = self.events_map.get(segment.start_second)
        
        if event_info:
            event_type = event_info.event_type
            priority = event_info.priority
            zones = ', '.join(event_info.active_zones) if event_info.active_zones else 'no específica'
            
            type_context = {
                'MOVEMENT': f"""
CONTEXTO: Se detectó MOVIMIENTO ACTIVO en este segmento (prioridad: {priority}).
Zonas activas: {zones}. Contornos detectados: {event_info.contour_info.get('max_count', 0)}.
Analiza con MÁXIMO DETALLE todo lo que ocurre: movimiento de personas, velocidad, dirección,
objetos transportados, interacciones, cualquier actividad sospechosa.
""",
                'ENTRY_EXIT': f"""
CONTEXTO: Se detectó ENTRADA o SALIDA de persona/vehículo en los BORDES del frame.
Zonas activas: {zones}. Prioridad: {priority}.
ENFOQUE PRINCIPAL:
- ¿Quién entra o sale? Descripción física detallada
- ¿Carga objetos? ¿Qué tipo?
- ¿Tiene autorización aparente (uniforme, badge, actitud)?
- ¿Horario/contexto apropiado para esta entrada/salida?
- Dirección: ¿de dónde viene, hacia dónde va?
""",
                'STATIC_PRESENCE': f"""
CONTEXTO: Se detectó una PERSONA u OBJETO QUE PERMANECE INMÓVIL (prioridad: {priority}).
Zonas activas: {zones}. Área del contorno: {event_info.contour_info.get('max_area', 0):.1f}% del frame.
ENFOQUE PRINCIPAL:
- ¿Hay una persona quieta? ¿Qué hace? ¿Está sentada, de pie, acostada?
- ¿Cuánto tiempo lleva en esa posición? (basado en la duración del evento)
- ¿Es merodeo (persona sin propósito aparente)?
- ¿Hay un objeto nuevo en la escena que antes no estaba?
- ¿Podría ser una situación de emergencia (persona inconsciente)?
""",
                'OBJECT_CHANGE': f"""
CONTEXTO: Se detectó un CAMBIO DE OBJETO en la escena sin movimiento continuo (prioridad: {priority}).
Algo apareció o desapareció entre un momento y otro.
ENFOQUE PRINCIPAL:
- ¿Qué objeto nuevo hay en la escena? ¿O qué desapareció?
- ¿Es un paquete, bolsa o mochila abandonada?
- ¿Se removió algún equipamiento o propiedad?
- ¿Cambió el estado de puertas, ventanas, cercos?
- Si es un objeto abandonado: ¿quién lo dejó? (buscar en el contexto temporal)
""",
                'SCENE_CHANGE': f"""
CONTEXTO: Se detectó un CAMBIO SIGNIFICATIVO en la escena general (prioridad: {priority}).
Score de cambio: {event_info.details.get('avg_scene_change', 0):.4f}.
ENFOQUE PRINCIPAL:
- ¿Cambió la iluminación drásticamente? ¿Causa natural o artificial?
- ¿Se obstruyó o manipuló la cámara?
- ¿Hubo un evento grande (multitud, vehículo grande, etc.)?
- ¿Las condiciones generales de la zona son normales?
- ¿Hay evidencia de vandalismo o manipulación deliberada?
"""
            }
            
            segment_type = event_type.replace('_', ' ')
            analysis_context = type_context.get(event_type, type_context['MOVEMENT'])
        else:
            if segment.motion_score >= 0.005:
                segment_type = "MOVIMIENTO DETECTADO"
                analysis_context = """
CONTEXTO: Se detectó MOVIMIENTO significativo en este segmento. Analiza con MÁXIMO DETALLE 
todo lo que ocurre, especialmente acciones, personas, y cualquier actividad sospechosa.
"""
            elif segment.motion_score > 0.001:
                segment_type = "CAMBIO DE ESCENA DETECTADO"
                analysis_context = """
CONTEXTO: Se detectó un CAMBIO en la escena. Presta atención a objetos, personas estáticas,
cambios de iluminación, puertas/ventanas abiertas o cerradas.
"""
            else:
                segment_type = "VERIFICACIÓN DE ESCENA"
                analysis_context = """
CONTEXTO: Verificación programada de la escena. Analiza el estado general:
personas presentes, objetos, condiciones de seguridad.
"""
        
        motion_note = ""
        if not is_frames_only:
            motion_note = """
IMPORTANTE: Estás viendo un VIDEO EN MOVIMIENTO. Presta especial atención a:
- Dirección y velocidad del movimiento de personas/vehículos
- Gestos, interacciones entre personas
- Objetos siendo cargados, depositados o manipulados
- Cambios en la escena a lo largo del clip
- Audio si está disponible (voces, alarmas, golpes, etc.)
"""
        
        prompt = f"""Eres un analista senior de seguridad con 20 años de experiencia en vigilancia CCTV.
Analiza este {media_type} de una cámara de seguridad con MÁXIMO DETALLE. NO dejes pasar NADA.

TIPO DE ANÁLISIS: {segment_type}
{analysis_context}
INFORMACIÓN DE LA CÁMARA:
- Nombre: {video.nombre_camara}
- Ubicación: {video.ubicacion}
- Timestamp: {segment.start_second:.0f}s - {segment.end_second:.0f}s (duración: {segment.end_second - segment.start_second:.1f}s)
- Intensidad de movimiento detectado: {segment.motion_score:.3f}
{motion_note}
CHECKLIST DE ANÁLISIS OBLIGATORIO (revisa CADA punto):
✅ PERSONAS: ¿Cuántas? ¿Qué hacen? ¿Cómo visten? ¿Llevan objetos? ¿Movimiento rápido/lento?
✅ VEHÍCULOS: ¿Hay? ¿Tipo, color? ¿Se mueven o están estacionados? ¿Placas visibles?
✅ OBJETOS: ¿Qué es visible? ¿Hay algo fuera de lugar o abandonado?
✅ COMPORTAMIENTO: ¿Las acciones son normales o inusuales? ¿Interacciones sospechosas?
✅ AMBIENTE: ¿Día/noche? ¿Interior/exterior? ¿Iluminación? ¿Clima visible?
✅ ACCESOS: ¿Se observan puertas, ventanas, cercas siendo cruzadas?
✅ OBJETOS ABANDONADOS: ¿Mochilas, bolsas o paquetes sin dueño?
✅ MULTITUDES: ¿Aglomeración inusual de personas?
✅ MERODEO: ¿Alguien permanece sin propósito aparente?
✅ VANDALISMO: ¿Daño a propiedad?
✅ ROBOS/HURTOS: ¿Alguien toma algo que no le pertenece?

CLASIFICACIÓN DE RIESGO:
- BAJO: Actividad normal y rutinaria
- MEDIO: Actividad inusual pero no necesariamente peligrosa
- ALTO: Actividad potencialmente peligrosa (intrusión, pelea, daño a propiedad)
- CRITICO: Emergencia evidente (violencia activa, robo en progreso, incendio)

Responde ÚNICAMENTE con este JSON:
{{
    "descripcion_escena": "Descripción MUY detallada de TODO lo que ocurre (mínimo 3 oraciones)",
    "nivel_riesgo": "BAJO/MEDIO/ALTO/CRITICO",
    "razon_riesgo": "Explicación detallada del nivel de riesgo asignado",
    "confianza": 85,
    "personas_estimadas": 0,
    "vehiculos_estimados": 0,
    "objetos_detectados": ["objeto1", "objeto2"],
    "acciones_detectadas": ["acción1", "acción2"],
    "descripcion_personas": ["Persona 1: descripción física, vestimenta, acción, dirección"],
    "descripcion_vehiculos": ["Vehículo 1: tipo, color, acción, dirección"],
    "ambiente": {{
        "iluminacion": "día/noche/atardecer/artificial",
        "interior_exterior": "interior/exterior",
        "clima": "despejado/nublado/lluvioso/no aplicable",
        "visibilidad": "buena/media/baja"
    }},
    "comportamiento_general": "normal/sospechoso/alarmante",
    "alertas": ["Cualquier cosa que requiera atención inmediata"],
    "puntos_interes": ["Elementos de la escena que merecen seguimiento"],
    "actividad_zona": "sin actividad/baja/moderada/alta",
    "resumen_ejecutivo": "Resumen de 1 oración de lo más importante"
}}"""
        return prompt

    def perform_cross_analysis(self, video: SecurityVideo, events: List[Dict]) -> Dict:
        if not events:
            return {
                'nivel_riesgo_global': 'BAJO',
                'resumen_ejecutivo': 'No se detectaron eventos relevantes',
                'patrones_detectados': [],
                'recomendaciones_seguridad': []
            }
        
        video_metadata = {
            'nombre_camara': video.nombre_camara,
            'ubicacion': video.ubicacion,
            'duracion_segundos': video.duracion_segundos,
            'fecha_grabacion': video.fecha_grabacion
        }
        
        result = self.gemini_adapter.analyze_multiple_clips_summary(
            all_events_analysis=events,
            video_metadata=video_metadata
        )
        
        if result.get('success') and result.get('analisis_cruzado'):
            return result['analisis_cruzado']
        
        return self.generate_basic_cross_analysis(events)

    def generate_basic_cross_analysis(self, events: List[Dict]) -> Dict:
        risk_levels = [e.get('nivel_riesgo', 'BAJO') for e in events]
        risk_order = {'BAJO': 0, 'MEDIO': 1, 'ALTO': 2, 'CRITICO': 3}
        max_risk = max(risk_levels, key=lambda r: risk_order.get(r, 0)) if risk_levels else 'BAJO'
        
        return {
            'nivel_riesgo_global': max_risk,
            'resumen_ejecutivo': f'{len(events)} eventos detectados. Riesgo máximo: {max_risk}.',
            'personas_total_estimado': sum(e.get('personas_count', 0) for e in events),
            'vehiculos_total_estimado': sum(e.get('vehiculos_count', 0) for e in events),
            'patrones_detectados': [],
            'recomendaciones_seguridad': [],
            'anomalias': []
        }
