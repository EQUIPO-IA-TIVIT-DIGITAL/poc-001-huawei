"""
Caso de Uso: Procesamiento de Videos de Seguridad con IA
Pipeline completo: OpenCV → Gemini Vision → Video Intelligence → Reporte

Flujo:
1. Descarga video de GCS
2. Motion Detection (OpenCV MOG2 + Optical Flow)
3. Extracción de clips con movimiento
4. Clasificación con Gemini Vision (NORMAL/SOSPECHOSO/IMPORTANTE)
5. Análisis profundo con Video Intelligence (solo eventos IMPORTANTES)
6. Generación de reporte profesional (TXT + PDF)
7. Notificación por email

Mejoras:
- Gestión de cuotas de API con rate limiting
- Cleanup automático de archivos temporales
- Procesamiento con context managers
"""

import logging
import os
import tempfile
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from domain.entities import (
    SecurityVideo,
    EventoSeguridad,
    EstadoSecurityVideo,
    ClasificacionEvento,
)
from infrastructure.repositories.security_video_repository import SecurityVideoRepository
from infrastructure.adapters.opencv_motion_detector import (
    OpenCVMotionDetector,
    MotionDetectorConfig,
)
from infrastructure.adapters.video_segmentation import VideoSegmentationAdapter

# Nuevas utilidades
from infrastructure.services.quota_manager import get_quota_manager, QuotaExceededException
from infrastructure.services.temp_file_manager import (
    temporary_video_clip,
    temporary_directory,
    temporary_frames,
    temporary_download,
    TempFileTracker
)

# Gestores de índices y caché (Arquitectura Lazy)
from infrastructure.services.security_index_manager import get_index_manager
from infrastructure.services.analysis_cache_manager import get_cache_manager

# Logger estándar
logger = logging.getLogger(__name__)

# Logger especializado para trazabilidad
from infrastructure.services.security_logger import get_security_logger, log_phase
sec_logger = get_security_logger()


class SecurityVideoProcessor:
    """
    Procesador completo de videos de seguridad
    
    Orquesta todo el pipeline de análisis con IA
    """
    
    def __init__(
        self,
        repository: Optional[SecurityVideoRepository] = None,
        motion_detector: Optional[OpenCVMotionDetector] = None,
        video_segmentation: Optional[VideoSegmentationAdapter] = None,
    ):
        """Inicializa el procesador"""
        self.repository = repository or SecurityVideoRepository()
        self.motion_detector = motion_detector or OpenCVMotionDetector()
        self.video_segmentation = video_segmentation or VideoSegmentationAdapter()
        
        # Se inicializarán bajo demanda
        self.gemini_adapter = None
        self.video_intelligence = None
        
        # Gestor de cuotas de API
        self.quota_manager = get_quota_manager()
        
        # Gestores de índices y caché (Lazy Architecture)
        self.index_manager = get_index_manager()
        self.cache_manager = get_cache_manager()
        
        # Importar EnhancedReportGenerator para reportes con imágenes
        from infrastructure.services.enhanced_report_generator import EnhancedReportGenerator
        self.report_generator = EnhancedReportGenerator()
        
        # Directorio para frames del reporte
        self.report_frames_dir = os.path.join(tempfile.gettempdir(), "security_report_frames")
        
        # Servicio de notificaciones
        from infrastructure.services.notification_service import get_notification_service
        self.notification_service = get_notification_service()
        
        # Email de alerta (configurable)
        self.alert_email = os.getenv('SECURITY_ALERT_EMAIL', 'seguridad@tivit.com')
        
        # Configuración de procesamiento paralelo
        self.max_parallel_workers = int(os.getenv('GEMINI_MAX_WORKERS', '5'))
        
        # Checkpoints válidos para recuperación
        self.valid_checkpoints = [
            'INICIO',
            'MOTION_DONE',
            'CLIPS_EXTRACTED',
            'CLASSIFICATION_DONE',
            'DEEP_ANALYSIS_DONE',
            'EVENTS_SAVED',
            'REPORT_DONE',
        ]
    
    def _init_gemini(self):
        """Inicializa Gemini Vision bajo demanda"""
        if self.gemini_adapter is None:
            try:
                from infrastructure.adapters.ai_gateway import get_ai_gateway
                self.gemini_adapter = get_ai_gateway()
                logger.info("✅ Gemini Vision inicializado")
            except Exception as e:
                logger.error(f"❌ Error inicializando Gemini: {e}")
    
    def _init_video_intelligence(self):
        self.video_intelligence = None
    
    def _get_checkpoint(self, video: SecurityVideo) -> str:
        """
        Obtiene el checkpoint actual del video para recuperación.
        
        Returns:
            Nombre del checkpoint ('INICIO', 'MOTION_DONE', etc.)
        """
        checkpoint = video.metadata_tecnico.get('processing_checkpoint', 'INICIO')
        if checkpoint not in self.valid_checkpoints:
            checkpoint = 'INICIO'
        logger.info(f"📍 Checkpoint actual: {checkpoint}")
        return checkpoint
    
    def _save_checkpoint(self, video: SecurityVideo, checkpoint: str, extra_data: Dict = None):
        """
        Guarda un checkpoint de progreso para recuperación.
        
        Args:
            video: Video de seguridad
            checkpoint: Nombre del checkpoint
            extra_data: Datos adicionales a persistir (ej: clips procesados)
        """
        if checkpoint not in self.valid_checkpoints:
            logger.warning(f"⚠️ Checkpoint inválido: {checkpoint}")
            return
        
        video.metadata_tecnico['processing_checkpoint'] = checkpoint
        video.metadata_tecnico['checkpoint_timestamp'] = datetime.utcnow().isoformat()
        
        if extra_data:
            video.metadata_tecnico['checkpoint_data'] = extra_data
        
        self.repository.guardar_video(video)
        logger.info(f"💾 Checkpoint guardado: {checkpoint}")
    
    # =========================================================================
    # LAZY ARCHITECTURE: Procesamiento On-Demand
    # =========================================================================
    
    def index_security_video(self, video_id: str) -> bool:
        """
        INDEXADO LIGERO: Motion Detection + Clasificación Básica
        NO hace análisis profundo (Video Intelligence)
        
        Ideal para:
        - Procesamiento rápido (10-15 min vs 35-45 min)
        - Bajo costo ($1-2 vs $12-18)
        - Análisis posterior bajo demanda
        
        Args:
            video_id: ID del video en el repositorio
        
        Returns:
            True si se indexó correctamente
        """
        sec_logger.set_context(video_id, "INDEX")
        sec_logger.start_phase("INDEX_PIPELINE", "Indexado ligero de video de seguridad")
        
        logger.info(f"🚀 Iniciando INDEXADO de video: {video_id}")
        start_time = datetime.utcnow()
        
        try:
            # 1. Obtener video del repositorio
            video = self.repository.obtener_video(video_id)
            if not video:
                sec_logger.error(f"Video no encontrado: {video_id}")
                logger.error(f"❌ Video no encontrado: {video_id}")
                return False
            
            logger.info(f"📹 Video: {video.nombre_camara} - {video.ubicacion}")
            
            # 2. Motion Detection
            sec_logger.start_phase("MOTION_DETECTION", "Detectando movimiento")
            motion_segments = self._phase_motion_detection(video)
            sec_logger.end_phase("MOTION_DETECTION", success=True, details=f"{len(motion_segments)} segmentos")
            
            if not motion_segments:
                logger.warning("⚠️ No se detectó movimiento en el video")
                # Crear índice vacío
                video.actualizar_estado(EstadoSecurityVideo.INDEXED)
                video.estadisticas = {"eventos_totales": 0, "sin_movimiento": True}
                self.repository.guardar_video(video)
                return True
            
            # 3. Extraer clips
            sec_logger.start_phase("CLIP_EXTRACTION", f"Extrayendo {len(motion_segments)} clips")
            clips = self._extract_motion_clips(video, motion_segments)
            sec_logger.end_phase("CLIP_EXTRACTION", success=True, details=f"{len(clips)} clips")
            
            # 4. Clasificación LIGERA con Gemini (solo descripción básica)
            sec_logger.start_phase("GEMINI_LIGHT", "Clasificación rápida con Gemini")
            classified_clips = self._phase_gemini_classification_light(video, clips)
            sec_logger.end_phase("GEMINI_LIGHT", success=True, details=f"{len(classified_clips)} clips")
            
            # 5. Crear índice estructurado
            sec_logger.start_phase("CREATE_INDEX", "Creando índice estructurado")
            
            video_metadata = {
                'nombre_camara': video.nombre_camara,
                'ubicacion': video.ubicacion,
                'fecha_grabacion': video.fecha_grabacion,
                'duracion_segundos': video.duracion_segundos,
                'fps': video.metadata_tecnico.get('fps') or self._detect_video_fps(video),
            }
            
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            processing_stats = {
                'tiempo_segundos': processing_time,
                'costo_estimado': self._estimate_indexing_cost(len(classified_clips))
            }
            
            index_data = self.index_manager.create_index(
                video_id=video.id,
                video_metadata=video_metadata,
                clips=classified_clips,
                processing_stats=processing_stats
            )
            
            # 6. Guardar índice en GCS
            index_path = self.index_manager.save_index_to_gcs(video.id, index_data)
            sec_logger.end_phase("CREATE_INDEX", success=True, details=f"Guardado en {index_path}")
            
            # 7. Actualizar video como INDEXED
            video.actualizar_estado(EstadoSecurityVideo.INDEXED)
            video.metadata_tecnico['index_path'] = index_path
            video.metadata_tecnico['indexado_en'] = datetime.utcnow().isoformat()
            video.estadisticas = index_data['estadisticas_basicas']
            self.repository.guardar_video(video)
            
            logger.info(f"✅ Video indexado correctamente: {video_id}")
            logger.info(f"⏱️  Tiempo: {processing_time:.1f}s")
            logger.info(f"💰 Costo estimado: ${processing_stats['costo_estimado']:.2f}")
            
            sec_logger.end_phase("INDEX_PIPELINE", success=True, details=f"Completado en {processing_time:.1f}s")
            
            # 8. Notificación
            self._send_indexing_notification(video, index_data)
            
            return True
        
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            sec_logger.log_exception(f"Error fatal en indexado: {e}")
            logger.error(f"❌ Error indexando video {video_id}: {e}\n{error_traceback}")
            
            # Marcar como error
            video = self.repository.obtener_video(video_id)
            if video:
                video.actualizar_estado(EstadoSecurityVideo.ERROR)
                video.estadisticas = {"error": str(e)}
                self.repository.guardar_video(video)
            
            return False
    
    def _phase_gemini_classification_light(
        self, video: SecurityVideo, clips: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Clasificación LIGERA con Gemini Vision
        Solo descripción básica y clasificación, sin análisis profundo
        Más rápido y económico que la clasificación completa
        """
        logger.info("🤖 Clasificación ligera con Gemini Vision")
        
        video.actualizar_estado(EstadoSecurityVideo.CLASSIFYING)
        self.repository.guardar_video(video)
        
        self._init_gemini()
        if not self.gemini_adapter or not self.gemini_adapter.is_available():
            logger.error("❌ Gemini no disponible")
            return clips
        
        classified_clips = []
        total_clips = len(clips)
        
        def process_single_clip_light(args):
            """Procesa un clip con análisis ligero"""
            idx, clip = args
            try:
                # Extraer solo 3 frames (vs 5 en versión completa)
                clip_path = clip.get("clip_path_local")
                if not clip_path or not os.path.exists(clip_path):
                    return None
                
                frames_dir = tempfile.mkdtemp(prefix="frames_light_")
                frame_paths = self.video_segmentation.extract_frames_from_clip(
                    clip_path,
                    num_frames=3,  # Menos frames = más rápido
                    output_dir=frames_dir
                )
                
                if not frame_paths:
                    return None
                
                # Convertir frames a base64
                import base64
                frames_base64 = []
                for frame_path in frame_paths:
                    with open(frame_path, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode("utf-8")
                        frames_base64.append(b64_data)
                
                # Clasificar con prompt simplificado
                clasificacion_result = self._classify_with_gemini_light(
                    frames_base64, video, clip
                )
                
                # Guardar primer frame para referencia
                saved_frame_path = None
                if frame_paths:
                    report_frames_base = os.path.join(tempfile.gettempdir(), "security_report_frames")
                    os.makedirs(report_frames_base, exist_ok=True)
                    
                    import shutil
                    frame_filename = f"frame_{video.id}_{idx:04d}.jpg"
                    saved_frame_path = os.path.join(report_frames_base, frame_filename)
                    try:
                        shutil.copy2(frame_paths[0], saved_frame_path)
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudo guardar frame: {e}")
                        saved_frame_path = None
                
                # Cleanup
                for frame_path in frame_paths:
                    try:
                        os.remove(frame_path)
                    except Exception as e:
                        logger.debug(f"Could not remove frame file: {e}")
                try:
                    os.rmdir(frames_dir)
                except Exception as e:
                    logger.debug(f"Could not remove frames directory: {e}")
                
                # Agregar a clip
                clip_classified = clip.copy()
                clip_classified.update(clasificacion_result)
                if saved_frame_path:
                    clip_classified['frame_path'] = saved_frame_path
                
                # Extraer tags básicos de la descripción
                descripcion = clasificacion_result.get('descripcion_gemini', '')
                clip_classified['tags'] = self._extract_tags_from_description(descripcion)
                
                return (idx, clip_classified)
            
            except Exception as e:
                logger.error(f"❌ Error clasificando clip {idx}: {e}")
                return (idx, clip.copy())
        
        # Procesamiento paralelo
        logger.info(f"🔄 Procesando {total_clips} clips con {self.max_parallel_workers} workers")
        
        with ThreadPoolExecutor(max_workers=self.max_parallel_workers) as executor:
            futures = {
                executor.submit(process_single_clip_light, (i, clip)): i 
                for i, clip in enumerate(clips)
            }
            
            results = [None] * total_clips
            processed = 0
            for future in as_completed(futures):
                result = future.result()
                if result:
                    idx, clip_classified = result
                    results[idx] = clip_classified
                    processed += 1
                    
                    if processed % 10 == 0 or processed == total_clips:
                        logger.info(f"   Progreso: {processed}/{total_clips} clips")
        
        classified_clips = [r for r in results if r is not None]
        
        logger.info(f"✅ Clips clasificados: {len(classified_clips)}/{total_clips}")
        return classified_clips
    
    def _classify_with_gemini_light(
        self, frames_base64: List[str], video: SecurityVideo, clip: Dict
    ) -> Dict[str, Any]:
        """
        Clasificación ligera con Gemini (prompt simplificado)
        """
        prompt = f"""Clasifica este clip de cámara de seguridad de forma breve.

Ubicación: {video.ubicacion}
Timestamp: {clip.get('timestamp_inicio', 0):.0f}s

Clasifica como NORMAL, SOSPECHOSO o IMPORTANTE.
Responde SOLO en JSON sin markdown:
{{"clasificacion": "NORMAL", "confianza": 0.85, "descripcion": "Breve descripción"}}"""
        
        try:
            # Adquirir cuota
            self.quota_manager.acquire_gemini(blocking=True, timeout=30.0)
            
            # Llamar a Gemini
            response = self.gemini_adapter.analyze_frames(prompt, frames_base64)
            
            if not isinstance(response, dict):
                import json
                response = json.loads(response)
            
            if not response.get('success', False):
                return self._default_classification()
            
            analisis = response.get('analisis', {})
            
            clasificacion_raw = analisis.get('clasificacion', 'normal').upper().strip()
            clasificacion_map = {
                'NORMAL': ClasificacionEvento.NORMAL,
                'SOSPECHOSO': ClasificacionEvento.SOSPECHOSO,
                'IMPORTANTE': ClasificacionEvento.IMPORTANTE,
            }
            clasificacion = clasificacion_map.get(clasificacion_raw, ClasificacionEvento.NORMAL)
            
            confianza = float(analisis.get('confianza', 0.7))
            confianza = max(0.0, min(1.0, confianza))
            
            descripcion = analisis.get('descripcion', f"Clip clasificado como {clasificacion_raw}")
            
            return {
                "clasificacion": clasificacion,
                "confianza": confianza,
                "descripcion_gemini": descripcion[:200],  # Más corto
            }
        
        except Exception as e:
            logger.warning(f"⚠️ Error en clasificación ligera: {e}")
            return self._default_classification()
    
    def _default_classification(self) -> Dict[str, Any]:
        """Clasificación por defecto en caso de error"""
        return {
            "clasificacion": ClasificacionEvento.NORMAL,
            "confianza": 0.5,
            "descripcion_gemini": "Clasificación pendiente",
        }
    
    def _extract_tags_from_description(self, descripcion: str) -> List[str]:
        """Extrae tags básicos de una descripción"""
        tags = []
        descripcion_lower = descripcion.lower()
        
        # Tags comunes
        tag_keywords = {
            'persona': 'persona',
            'personas': 'personas',
            'vehiculo': 'vehiculo',
            'auto': 'auto',
            'coche': 'auto',
            'moto': 'moto',
            'bicicleta': 'bicicleta',
            'noche': 'noche',
            'dia': 'dia',
            'corriendo': 'movimiento_rapido',
            'caminando': 'caminando',
            'entrada': 'entrada',
            'salida': 'salida',
        }
        
        for keyword, tag in tag_keywords.items():
            if keyword in descripcion_lower:
                if tag not in tags:
                    tags.append(tag)
        
        return tags if tags else ['sin_clasificar']
    
    def _estimate_indexing_cost(self, num_clips: int) -> float:
        """Estima el costo de indexado"""
        # Gemini: ~$0.001 por clip (3 frames)
        # No incluye Video Intelligence
        gemini_cost = num_clips * 0.001
        overhead = 0.20  # Costos de storage, etc
        return gemini_cost + overhead
    
    def _send_indexing_notification(self, video: SecurityVideo, index_data: Dict):
        """Envía notificación cuando termina el indexado"""
        try:
            if self.notification_service:
                stats = index_data.get('estadisticas_basicas', {})
                self.notification_service.enviar_notificacion(
                    tipo="VIDEO_INDEXADO",
                    titulo=f"Video indexado: {video.nombre_camara}",
                    mensaje=f"Listo para consultas. {stats.get('total_clips', 0)} clips detectados.",
                    datos={
                        "video_id": video.id,
                        "clips_totales": stats.get('total_clips', 0),
                        "por_clasificacion": stats.get('por_clasificacion', {})
                    }
                )
        except Exception as e:
            logger.warning(f"⚠️ Error enviando notificación: {e}")
    
    def generate_full_report(
        self,
        video_id: str,
        analisis_profundo: bool = True,
        formato: str = "pdf"
    ) -> Dict[str, Any]:
        """
        Genera reporte completo de un video indexado
        
        Si analisis_profundo=True → analiza todos los clips faltantes con VI
        Si analisis_profundo=False → usa solo data disponible en caché
        
        Args:
            video_id: ID del video indexado
            analisis_profundo: Si True, analiza clips faltantes
            formato: 'txt' | 'pdf' | 'json'
        
        Returns:
            Dict con info del reporte generado y costo
        """
        logger.info(f"📄 Generando reporte completo: {video_id} (profundo={analisis_profundo})")
        start_time = datetime.utcnow()
        
        resultado = {
            'video_id': video_id,
            'formato': formato,
            'analisis_profundo': analisis_profundo,
            'estado': 'procesando',
            'costo_total': 0.0,
            'clips_analizados_nuevos': 0,
            'reporte_url': None,
            'error': None
        }
        
        try:
            # 1. Cargar índice
            index_data = self.index_manager.load_index_from_gcs(video_id)
            if not index_data:
                raise ValueError(f"Video no indexado: {video_id}")
            
            metadata = index_data.get('metadata', {})
            todos_clips = index_data.get('clips', [])
            
            logger.info(f"📊 Total de clips en índice: {len(todos_clips)}")
            
            # 2. Cargar caché
            cache = self.cache_manager.load_cache(video_id)
            clips_analizados = cache.get('clips_analizados', {})
            
            logger.info(f"💾 Clips ya analizados en caché: {len(clips_analizados)}")
            
            # 3. Si análisis profundo, procesar clips faltantes
            if analisis_profundo:
                clips_faltantes = [
                    clip for clip in todos_clips
                    if clip['id'] not in clips_analizados
                ]
                
                if clips_faltantes:
                    logger.info(f"🔬 Analizando {len(clips_faltantes)} clips faltantes con Video Intelligence")
                    
                    self._init_video_intelligence()
                    if not self.video_intelligence or not self.video_intelligence.is_available():
                        logger.warning("⚠️ Video Intelligence no disponible, usando data existente")
                    else:
                        costo_analisis = self._analyze_missing_clips(
                            video_id,
                            clips_faltantes,
                            cache
                        )
                        resultado['costo_total'] += costo_analisis
                        resultado['clips_analizados_nuevos'] = len(clips_faltantes)
                else:
                    logger.info("✅ Todos los clips ya están analizados")
            
            # 4. Recargar caché actualizado
            cache = self.cache_manager.load_cache(video_id)
            
            # 5. Preparar eventos para reporte
            eventos_reporte = self._prepare_events_for_report(
                todos_clips,
                cache
            )
            
            # 6. Generar reporte según formato
            if formato == 'pdf':
                reporte_path = self._generate_pdf_report(
                    video_id,
                    metadata,
                    eventos_reporte,
                    index_data.get('estadisticas_basicas', {})
                )
            elif formato == 'txt':
                reporte_path = self._generate_txt_report(
                    video_id,
                    metadata,
                    eventos_reporte,
                    index_data.get('estadisticas_basicas', {})
                )
            else:  # json
                reporte_path = self._generate_json_report(
                    video_id,
                    metadata,
                    eventos_reporte,
                    index_data.get('estadisticas_basicas', {})
                )
            
            # 7. Actualizar resultado
            resultado['estado'] = 'completado'
            resultado['reporte_url'] = reporte_path
            resultado['tiempo_generacion'] = (datetime.utcnow() - start_time).total_seconds()
            resultado['costo_total'] += 0.10  # Costo de generación
            
            # 8. Actualizar video en repositorio
            video = self.repository.obtener_video(video_id)
            if video:
                if analisis_profundo:
                    video.actualizar_estado(EstadoSecurityVideo.COMPLETED)
                video.metadata_tecnico['ultimo_reporte'] = datetime.utcnow().isoformat()
                video.metadata_tecnico['reporte_url'] = reporte_path
                self.repository.guardar_video(video)
            
            logger.info(f"✅ Reporte generado: {reporte_path}")
            logger.info(f"💰 Costo total: ${resultado['costo_total']:.2f}")
            
            return resultado
        
        except Exception as e:
            logger.error(f"❌ Error generando reporte: {e}", exc_info=True)
            resultado['estado'] = 'error'
            resultado['error'] = str(e)
            return resultado
    
    def _analyze_missing_clips(
        self,
        video_id: str,
        clips: List[Dict[str, Any]],
        cache: Dict[str, Any]
    ) -> float:
        """
        Analiza clips faltantes con Video Intelligence
        
        Returns:
            Costo total del análisis
        """
        features = [
            "PERSON_DETECTION",
            "OBJECT_TRACKING",
            "FACE_DETECTION",
            "LABEL_DETECTION"
        ]
        costo_por_clip = 0.10
        costo_total = 0.0
        
        for i, clip in enumerate(clips):
            try:
                logger.info(f"   Analizando clip {i+1}/{len(clips)}: {clip['id']}")
                
                clip_url = clip.get('ruta_clip')
                if not clip_url:
                    continue
                
                # Analizar con VI
                analysis = self.video_intelligence.analyze_video(clip_url, features)
                
                if analysis:
                    # Guardar en caché
                    self.cache_manager.add_clip_analysis(
                        video_id=video_id,
                        clip_id=clip['id'],
                        analysis_data=analysis,
                        costo=costo_por_clip,
                        query_context="full_report"
                    )
                    
                    costo_total += costo_por_clip
                    logger.info(f"   ✅ Clip analizado: {clip['id']}")
                
            except Exception as e:
                logger.error(f"   ❌ Error analizando clip {clip['id']}: {e}")
        
        return costo_total
    
    def _prepare_events_for_report(
        self,
        clips: List[Dict[str, Any]],
        cache: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Prepara eventos para el reporte combinando índice + caché
        """
        eventos = []
        
        for clip in clips:
            clip_id = clip['id']
            analysis = cache.get('clips_analizados', {}).get(clip_id)
            
            evento = {
                'timestamp_inicio': clip.get('timestamp_inicio', 0),
                'timestamp_fin': clip.get('timestamp_fin', 0),
                'duracion': clip.get('duracion', 0),
                'clasificacion': clip.get('clasificacion_rapida', 'NORMAL'),
                'confianza': clip.get('confianza', 0.0),
                'descripcion': clip.get('descripcion_basica', ''),
                'frame_url': clip.get('ruta_frame', ''),
                'clip_url': clip.get('ruta_clip', ''),
                'analisis_profundo': None
            }
            
            # Agregar análisis profundo si existe
            if analysis:
                vi_data = analysis.get('video_intelligence', {})
                evento['analisis_profundo'] = {
                    'personas': vi_data.get('personas', {}),
                    'objetos': vi_data.get('objects', []),
                    'rostros': vi_data.get('faces', {}),
                    'etiquetas': vi_data.get('labels', [])
                }
            
            eventos.append(evento)
        
        # Ordenar por timestamp
        eventos.sort(key=lambda x: x['timestamp_inicio'])

        return eventos

    def _detect_video_fps(self, video) -> float:
        """
        Intenta obtener el FPS real del video usando OpenCV.
        Retorna 30.0 como fallback si no puede leer el archivo.
        """
        DEFAULT_FPS = 30.0
        try:
            import cv2
            local_path = video.metadata_tecnico.get('local_path') or video.storage_path
            if not local_path or not os.path.exists(local_path):
                return DEFAULT_FPS
            cap = cv2.VideoCapture(local_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
            if fps and fps > 0:
                logger.debug("FPS detectado del video %s: %.2f", video.id, fps)
                return fps
        except Exception as e:
            logger.debug("No se pudo detectar FPS, usando %s: %s", DEFAULT_FPS, e)
        return DEFAULT_FPS

    def _upload_report_to_gcs(self, local_path: str, video_id: str, formato: str) -> str:
        try:
            from config.app_config import AppConfig
            backend = getattr(AppConfig, "STORAGE_BACKEND", "filesystem")
            if backend == "minio":
                from infrastructure.adapters.minio_storage_adapter import MinioStorageAdapter
                storage = MinioStorageAdapter(AppConfig)
            else:
                from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
                storage = FilesystemStorageAdapter()
            if not storage.is_available():
                logger.warning("Storage no disponible, reporte solo en disco local: %s", local_path)
                return local_path

            blob_name = f"reports/{video_id}/report_{video_id}.{formato}"
            url = storage.upload_file(local_path, blob_name)
            if url:
                logger.info("Reporte subido a storage: %s", url)
                try:
                    os.remove(local_path)
                except OSError:
                    pass
                return url
        except Exception as e:
            logger.error("Error subiendo reporte: %s", e)

        return local_path

    def _generate_pdf_report(
        self,
        video_id: str,
        metadata: Dict[str, Any],
        eventos: List[Dict[str, Any]],
        estadisticas: Dict[str, Any]
    ) -> str:
        """
        Genera reporte PDF completo
        Usa el EnhancedReportGenerator existente
        """
        video = self.repository.obtener_video(video_id)
        if not video:
            raise ValueError(f"Video no encontrado: {video_id}")
        
        # Convertir eventos al formato esperado por el generador
        eventos_formato_reporte = []
        for evento in eventos:
            evento_reporte = EventoSeguridad(
                timestamp_inicio=evento['timestamp_inicio'],
                timestamp_fin=evento['timestamp_fin'],
                clasificacion=evento['clasificacion'],
                confianza=evento['confianza'],
                descripcion=evento['descripcion']
            )
            eventos_formato_reporte.append(evento_reporte)
        
        # Generar PDF
        pdf_path = self.report_generator.generar_reporte(
            video=video,
            eventos=eventos_formato_reporte,
            metadata_adicional={'generado_bajo_demanda': True}
        )

        return self._upload_report_to_gcs(pdf_path, video_id, 'pdf')
    
    def _generate_txt_report(
        self,
        video_id: str,
        metadata: Dict[str, Any],
        eventos: List[Dict[str, Any]],
        estadisticas: Dict[str, Any]
    ) -> str:
        """Genera reporte TXT simple"""
        import os
        
        output_dir = os.path.join(tempfile.gettempdir(), "security_reports")
        os.makedirs(output_dir, exist_ok=True)
        
        output_path = os.path.join(output_dir, f"report_{video_id}.txt")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"REPORTE DE SEGURIDAD - {metadata.get('nombre_camara', 'N/A')}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Ubicación: {metadata.get('ubicacion', 'N/A')}\n")
            f.write(f"Fecha: {metadata.get('fecha_grabacion', 'N/A')}\n")
            f.write(f"Duración total: {metadata.get('duracion_total', 0) / 3600:.1f} horas\n\n")
            
            f.write("ESTADÍSTICAS:\n")
            f.write(f"- Total de eventos: {estadisticas.get('total_clips', 0)}\n")
            f.write(f"- Importantes: {estadisticas.get('por_clasificacion', {}).get('IMPORTANTE', 0)}\n")
            f.write(f"- Sospechosos: {estadisticas.get('por_clasificacion', {}).get('SOSPECHOSO', 0)}\n")
            f.write(f"- Normales: {estadisticas.get('por_clasificacion', {}).get('NORMAL', 0)}\n\n")
            
            f.write("=" * 80 + "\n")
            f.write("TIMELINE DE EVENTOS\n")
            f.write("=" * 80 + "\n\n")
            
            for evento in eventos:
                timestamp_str = self._format_timestamp(evento['timestamp_inicio'])
                f.write(f"[{timestamp_str}] {evento['clasificacion']}\n")
                f.write(f"  {evento['descripcion']}\n")
                if evento.get('analisis_profundo'):
                    personas = evento['analisis_profundo'].get('personas', {})
                    if personas.get('total_persons', 0) > 0:
                        f.write(f"  → Personas detectadas: {personas['total_persons']}\n")
                f.write("\n")
        
        logger.info("Reporte TXT generado: %s", output_path)

        return self._upload_report_to_gcs(output_path, video_id, 'txt')
    
    def _generate_json_report(
        self,
        video_id: str,
        metadata: Dict[str, Any],
        eventos: List[Dict[str, Any]],
        estadisticas: Dict[str, Any]
    ) -> str:
        """Genera reporte JSON estructurado"""
        import json
        import os
        
        output_dir = os.path.join(tempfile.gettempdir(), "security_reports")
        os.makedirs(output_dir, exist_ok=True)
        
        output_path = os.path.join(output_dir, f"report_{video_id}.json")
        
        reporte = {
            'video_id': video_id,
            'metadata': metadata,
            'estadisticas': estadisticas,
            'eventos': eventos,
            'generado_en': datetime.utcnow().isoformat()
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(reporte, f, indent=2, ensure_ascii=False)
        
        logger.info("Reporte JSON generado: %s", output_path)

        return self._upload_report_to_gcs(output_path, video_id, 'json')
    
    def _format_timestamp(self, seconds: float) -> str:
        """Formatea segundos a HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    # =========================================================================
    # Método original (análisis completo)
    # =========================================================================
    
    def process_security_video(self, video_id: str) -> bool:
        """
        Procesa un video de seguridad completo
        
        Args:
            video_id: ID del video en el repositorio
        
        Returns:
            True si se procesó correctamente
        """
        # Configurar contexto del logger
        sec_logger.set_context(video_id, "INIT")
        sec_logger.start_phase("PIPELINE_INICIO", f"Procesamiento completo de video de seguridad")
        
        logger.info(f"🚀 Iniciando procesamiento de video: {video_id}")
        start_time = datetime.utcnow()
        
        try:
            # 1. Obtener video del repositorio
            sec_logger.set_context(video_id, "LOAD_VIDEO")
            video = self.repository.obtener_video(video_id)
            if not video:
                sec_logger.error(f"Video no encontrado: {video_id}")
                logger.error(f"❌ Video no encontrado: {video_id}")
                return False
            
            # Log información del video
            sec_logger.log_video_info({
                'id': video.id,
                'nombre_camara': video.nombre_camara,
                'ubicacion': video.ubicacion,
                'duracion_segundos': video.duracion_segundos,
                'storage_path': video.storage_path
            })
            
            logger.info(f"📹 Video: {video.nombre_camara} - {video.ubicacion}")
            
            # 2. FASE 5: Motion Detection
            sec_logger.start_phase("MOTION_DETECTION", "Detectando movimiento con OpenCV MOG2")
            motion_segments = self._phase_motion_detection(video)
            
            if not motion_segments:
                sec_logger.warning("No se detectó movimiento en el video")
                sec_logger.end_phase("MOTION_DETECTION", success=True, details="Sin movimiento detectado")
                logger.warning("⚠️ No se detectó movimiento en el video")
                # Completar con reporte vacío
                video.actualizar_estado(EstadoSecurityVideo.COMPLETED)
                video.estadisticas = {"eventos_totales": 0, "sin_movimiento": True}
                self.repository.guardar_video(video)
                sec_logger.end_phase("PIPELINE_INICIO", success=True, details="Completado sin eventos")
                return True
            
            sec_logger.log_motion_detection(len(motion_segments), motion_segments)
            sec_logger.end_phase("MOTION_DETECTION", success=True, details=f"{len(motion_segments)} segmentos")
            
            # 3. Extraer clips de segmentos con movimiento
            sec_logger.start_phase("CLIP_EXTRACTION", f"Extrayendo {len(motion_segments)} clips")
            clips = self._extract_motion_clips(video, motion_segments)
            sec_logger.end_phase("CLIP_EXTRACTION", success=True, details=f"{len(clips)} clips extraídos")
            
            # 4. FASE 6: Clasificación con Gemini Vision
            sec_logger.start_phase("GEMINI_CLASSIFICATION", f"Clasificando {len(clips)} clips con Gemini Vision")
            classified_segments = self._phase_gemini_classification(video, clips)
            sec_logger.end_phase("GEMINI_CLASSIFICATION", success=True, details=f"{len(classified_segments)} clips clasificados")
            
            # 5. FASE 7: Análisis profundo (solo eventos IMPORTANTES)
            eventos_importantes = [
                s for s in classified_segments
                if s.get("clasificacion") == ClasificacionEvento.IMPORTANTE
            ]
            if eventos_importantes:
                sec_logger.start_phase("DEEP_ANALYSIS", f"Análisis profundo de {len(eventos_importantes)} eventos importantes")
                self._phase_deep_analysis(video, eventos_importantes)
                sec_logger.end_phase("DEEP_ANALYSIS", success=True)
                
                # 🚨 ALERTA INMEDIATA: Eventos importantes detectados
                self._send_immediate_alert(video, eventos_importantes)
            else:
                sec_logger.info("No hay eventos IMPORTANTES para análisis profundo")
            
            # 6. Guardar eventos en repositorio
            sec_logger.start_phase("SAVE_EVENTS", f"Guardando {len(classified_segments)} eventos en la base de datos")
            self._save_events(video, classified_segments)
            sec_logger.end_phase("SAVE_EVENTS", success=True)
            
            # 7. FASE 8: Generar reporte
            sec_logger.start_phase("REPORT_GENERATION", "Generando reportes TXT y PDF")
            self._phase_generate_report(video)
            sec_logger.end_phase("REPORT_GENERATION", success=True)
            
            # 8. Actualizar video como completado
            video.actualizar_estado(EstadoSecurityVideo.COMPLETED)
            video.fecha_procesamiento = datetime.utcnow().isoformat()
            video.tiempo_procesamiento_segundos = (
                datetime.utcnow() - start_time
            ).total_seconds()
            
            # Estadísticas finales
            video.estadisticas = self._calculate_statistics(classified_segments)
            self.repository.guardar_video(video)
            
            # Log estadísticas
            sec_logger.log_statistics(video.estadisticas)
            
            logger.info(f"✅ Procesamiento completado: {video_id}")
            logger.info(f"⏱️  Tiempo total: {video.tiempo_procesamiento_segundos:.1f}s")
            
            sec_logger.info(f"⏱️ Tiempo total de procesamiento: {video.tiempo_procesamiento_segundos:.1f}s")
            sec_logger.end_phase("PIPELINE_INICIO", success=True, details=f"Completado en {video.tiempo_procesamiento_segundos:.1f}s")
            
            # 9. Notificación por email (si hay eventos importantes o sospechosos)
            eventos_notificar = [
                s for s in classified_segments
                if s.get("clasificacion") in [ClasificacionEvento.IMPORTANTE, ClasificacionEvento.SOSPECHOSO]
            ]
            if eventos_notificar:
                sec_logger.info(f"Enviando notificación por email ({len(eventos_notificar)} eventos)")
                self._send_email_notification(video, eventos_notificar)
            
            # 10. Notificación de procesamiento completado
            self._send_completion_notification(video)
            
            return True
        
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            sec_logger.log_exception(f"Error fatal en procesamiento: {e}")
            sec_logger.error(f"Traceback completo:\n{error_traceback}")
            logger.error(f"❌ Error procesando video {video_id}: {e}\n{error_traceback}")
            
            # Marcar como error
            video = self.repository.obtener_video(video_id)
            if video:
                video.actualizar_estado(EstadoSecurityVideo.ERROR)
                video.estadisticas = {"error": str(e)}
                self.repository.guardar_video(video)
                
                # Notificación de error
                self._send_error_notification(video, str(e))
            
            return False
    
    def process_with_context(
        self, 
        video_id: str, 
        contexto_usuario: str,
        modo_analisis: str = "ESTANDAR"
    ) -> Dict[str, Any]:
        """
        Procesa un video de seguridad con contexto del usuario
        
        Args:
            video_id: ID del video en el repositorio
            contexto_usuario: Pregunta/contexto del usuario (ej: "cuántas personas salieron")
            modo_analisis: "ESTANDAR" (Gemini) o "PROFUNDO" (+ Video Intelligence)
        
        Returns:
            Dict con resultados del análisis
        """
        sec_logger.set_context(video_id, "CONTEXT_ANALYSIS")
        sec_logger.start_phase("CONTEXTUAL_PIPELINE", f"Análisis contextual: {contexto_usuario[:50]}...")
        
        logger.info(f"🎯 Iniciando análisis contextual: {video_id}")
        logger.info(f"   📝 Contexto: {contexto_usuario}")
        logger.info(f"   🔍 Modo: {modo_analisis}")
        
        start_time = datetime.utcnow()
        
        resultado = {
            "video_id": video_id,
            "contexto_usuario": contexto_usuario,
            "modo_analisis": modo_analisis,
            "estado": "procesando",
            "eventos_totales": 0,
            "eventos_relevantes": 0,
            "respuesta_consulta": "",
            "timeline": [],
            "estadisticas": {},
            "analisis_profundo": None
        }
        
        try:
            # 1. Obtener video
            video = self.repository.obtener_video(video_id)
            if not video:
                raise ValueError(f"Video no encontrado: {video_id}")
            
            resultado["video_info"] = {
                "nombre_camara": video.nombre_camara,
                "ubicacion": video.ubicacion,
                "duracion_segundos": video.duracion_segundos
            }
            
            # 2. Detección de movimiento (más sensible)
            logger.info("🔍 FASE 1: Detección de movimiento")
            motion_segments = self._phase_motion_detection(video)
            resultado["eventos_totales"] = len(motion_segments)
            
            if not motion_segments:
                logger.info("⚠️ No se detectó movimiento")
                resultado["estado"] = "completado"
                resultado["respuesta_consulta"] = "No se detectó actividad en el video."
                return resultado
            
            # 3. Extraer clips
            logger.info(f"📹 FASE 2: Extrayendo {len(motion_segments)} clips")
            clips = self._extract_motion_clips(video, motion_segments)
            
            # 4. Filtrar por contexto con Gemini
            logger.info(f"🎯 FASE 3: Filtrando clips por contexto")
            self._init_gemini()
            
            clips_relevantes = []
            for i, clip in enumerate(clips):
                logger.info(f"   Validando clip {i+1}/{len(clips)}...")
                
                # Extraer frames del clip
                frames_b64 = self._extract_frames_from_clip(clip.get("ruta_local"))
                if not frames_b64:
                    continue
                
                # Validar relevancia
                validacion = self.gemini_adapter.validar_contexto(frames_b64, contexto_usuario)
                
                if validacion.get("es_relevante", False):
                    clip["validacion_contexto"] = validacion
                    clips_relevantes.append(clip)
                    logger.info(f"   ✅ Relevante: {validacion.get('razon', '')[:50]}")
                else:
                    logger.info(f"   ❌ No relevante: {validacion.get('razon', '')[:50]}")
            
            resultado["eventos_relevantes"] = len(clips_relevantes)
            logger.info(f"📊 {len(clips_relevantes)}/{len(clips)} clips son relevantes")
            
            if not clips_relevantes:
                resultado["estado"] = "completado"
                resultado["respuesta_consulta"] = f"No se encontró actividad relacionada con: '{contexto_usuario}'"
                return resultado
            
            # 5. Análisis detallado de clips relevantes
            logger.info(f"🔬 FASE 4: Análisis detallado de {len(clips_relevantes)} clips")
            timeline = []
            
            for i, clip in enumerate(clips_relevantes):
                logger.info(f"   Analizando clip {i+1}/{len(clips_relevantes)}...")
                
                frames_b64 = self._extract_frames_from_clip(clip.get("ruta_local"))
                if not frames_b64:
                    continue
                
                # Análisis detallado con Gemini
                analisis = self.gemini_adapter.analizar_escena_detallada(frames_b64, contexto_usuario)
                
                if analisis.get("success"):
                    evento = {
                        "timestamp_inicio": clip.get("timestamp_inicio", 0),
                        "timestamp_fin": clip.get("timestamp_fin", 0),
                        "timestamp_formatted": self._format_timestamp(clip.get("timestamp_inicio", 0)),
                        "analisis": analisis.get("analisis", {}),
                        "frame_path": clip.get("frame_path")
                    }
                    timeline.append(evento)
                    
                    # Guardar frame si existe
                    if clip.get("frame_path"):
                        evento["frame_path"] = clip["frame_path"]
            
            resultado["timeline"] = timeline
            
            # 6. Si modo PROFUNDO, usar Video Intelligence
            if modo_analisis == "PROFUNDO" and clips_relevantes:
                logger.info(f"🔬 FASE 5: Análisis PROFUNDO con Video Intelligence")
                resultado["analisis_profundo"] = self._run_deep_analysis(video, clips_relevantes)
            
            # 7. Generar respuesta a la consulta
            resultado["respuesta_consulta"] = self._generate_context_response(
                contexto_usuario, 
                timeline, 
                resultado.get("analisis_profundo")
            )
            
            # 8. Calcular estadísticas
            resultado["estadisticas"] = {
                "total_movimientos": len(motion_segments),
                "relevantes_contexto": len(clips_relevantes),
                "porcentaje_relevancia": round(len(clips_relevantes) / len(motion_segments) * 100, 1) if motion_segments else 0,
                "duracion_total_eventos": sum(c.get("timestamp_fin", 0) - c.get("timestamp_inicio", 0) for c in clips_relevantes),
                "modo_analisis": modo_analisis
            }
            
            # 9. Tiempo de procesamiento
            tiempo_total = (datetime.utcnow() - start_time).total_seconds()
            resultado["tiempo_procesamiento_segundos"] = tiempo_total
            resultado["estado"] = "completado"
            
            logger.info(f"✅ Análisis contextual completado en {tiempo_total:.1f}s")
            
            # 10. Enviar notificación
            self._send_context_analysis_notification(video, resultado)
            
            sec_logger.end_phase("CONTEXTUAL_PIPELINE", success=True, 
                                details=f"{len(clips_relevantes)} eventos relevantes")
            
            return resultado
            
        except Exception as e:
            import traceback
            logger.error(f"❌ Error en análisis contextual: {e}")
            logger.error(traceback.format_exc())
            resultado["estado"] = "error"
            resultado["error"] = str(e)
            sec_logger.end_phase("CONTEXTUAL_PIPELINE", success=False, details=str(e))
            return resultado
    
    def _extract_frames_from_clip(self, clip_path: str, num_frames: int = 3) -> List[str]:
        """Extrae frames de un clip y los retorna en base64"""
        if not clip_path or not os.path.exists(clip_path):
            return []
        
        try:
            import cv2
            import base64
            
            cap = cv2.VideoCapture(clip_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            if total_frames < num_frames:
                num_frames = max(1, total_frames)
            
            frame_indices = [int(i * total_frames / num_frames) for i in range(num_frames)]
            frames_b64 = []
            
            for idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret:
                    _, buffer = cv2.imencode('.jpg', frame)
                    frames_b64.append(base64.b64encode(buffer).decode('utf-8'))
            
            cap.release()
            return frames_b64
            
        except Exception as e:
            logger.error(f"Error extrayendo frames: {e}")
            return []
    
    def _run_deep_analysis(self, video: SecurityVideo, clips: List[Dict]) -> Dict[str, Any]:
        """Ejecuta análisis profundo con Video Intelligence"""
        self._init_video_intelligence()
        
        if not self.video_intelligence or not self.video_intelligence.is_available():
            return {"error": "Video Intelligence no disponible"}
        
        resultados = {
            "personas": {"total": 0, "detalles": []},
            "rostros": {"total": 0, "emociones": []},
            "objetos": [],
            "etiquetas": []
        }
        
        features = [
            "PERSON_DETECTION",
            "FACE_DETECTION", 
            "OBJECT_TRACKING",
            "LABEL_DETECTION"
        ]
        
        for i, clip in enumerate(clips[:5]):  # Limitar a 5 clips para costos
            clip_url = clip.get("clip_url") or clip.get("storage_path")
            if not clip_url:
                continue
            
            logger.info(f"   🔬 Análisis VI {i+1}/{min(len(clips), 5)}...")
            
            try:
                analysis = self.video_intelligence.analyze_video(clip_url, features)
                if analysis:
                    # Agregar resultados
                    if analysis.get("persons"):
                        resultados["personas"]["total"] += analysis["persons"].get("total_persons", 0)
                    if analysis.get("faces"):
                        resultados["rostros"]["total"] += analysis["faces"].get("total_faces", 0)
                    if analysis.get("objects"):
                        resultados["objetos"].extend(analysis["objects"][:5])
                    if analysis.get("labels"):
                        resultados["etiquetas"].extend([l["description"] for l in analysis["labels"][:5]])
            except Exception as e:
                logger.error(f"Error en VI: {e}")
        
        # Deduplicate labels
        resultados["etiquetas"] = list(set(resultados["etiquetas"]))
        
        return resultados
    
    def _generate_context_response(
        self, 
        contexto: str, 
        timeline: List[Dict], 
        analisis_profundo: Dict = None
    ) -> str:
        """Genera una respuesta basada en el contexto y los resultados"""
        if not timeline:
            return f"No se encontró actividad relacionada con: '{contexto}'"
        
        # Contar personas detectadas
        total_personas = 0
        for evento in timeline:
            analisis = evento.get("analisis", {})
            personas = analisis.get("personas", {})
            if isinstance(personas, dict):
                total_personas += personas.get("cantidad_estimada", 0)
        
        # Generar respuesta basada en el contexto
        if "persona" in contexto.lower() or "salieron" in contexto.lower() or "entraron" in contexto.lower():
            resp = f"Se detectaron aproximadamente {total_personas or len(timeline)} eventos de personas"
            resp += f" entre las {timeline[0].get('timestamp_formatted', '??')} y las {timeline[-1].get('timestamp_formatted', '??')}."
        else:
            resp = f"Se detectaron {len(timeline)} eventos relevantes para '{contexto}'."
        
        # Agregar info de análisis profundo si disponible
        if analisis_profundo and not analisis_profundo.get("error"):
            if analisis_profundo.get("personas", {}).get("total", 0) > 0:
                resp += f" Video Intelligence confirmó {analisis_profundo['personas']['total']} personas únicas."
            if analisis_profundo.get("rostros", {}).get("total", 0) > 0:
                resp += f" Se detectaron {analisis_profundo['rostros']['total']} rostros."
        
        return resp
    
    def _format_timestamp(self, seconds: float) -> str:
        """Formatea segundos a HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _send_context_analysis_notification(self, video: SecurityVideo, resultado: Dict):
        """Envía notificación cuando el análisis contextual termina"""
        try:
            if self.notification_service:
                self.notification_service.enviar_notificacion(
                    tipo="ANALISIS_CONTEXTUAL_COMPLETADO",
                    titulo=f"Análisis completado: {video.nombre_camara}",
                    mensaje=resultado.get("respuesta_consulta", "Análisis completado"),
                    datos={
                        "video_id": video.id,
                        "eventos_relevantes": resultado.get("eventos_relevantes", 0),
                        "modo": resultado.get("modo_analisis", "ESTANDAR")
                    }
                )
        except Exception as e:
            logger.warning(f"Error enviando notificación: {e}")
    
    def _phase_motion_detection(self, video: SecurityVideo) -> List[Dict[str, Any]]:
        """FASE 5: Detección de movimiento con OpenCV"""
        logger.info("🔍 FASE 5: Motion Detection con OpenCV")
        
        video.actualizar_estado(EstadoSecurityVideo.MOTION_DETECTING)
        self.repository.guardar_video(video)
        
        # Detectar si es ruta local o de almacenamiento
        video_path = video.storage_path
        temp_video_path = None
        is_local_file = False
        
        # Soportar archivos locales para testing/desarrollo
        if video_path.startswith('/') or video_path.startswith('~'):
            # Es una ruta local
            import os
            expanded_path = os.path.expanduser(video_path)
            if os.path.exists(expanded_path):
                temp_video_path = expanded_path
                is_local_file = True
                logger.info(f"📁 Usando archivo local: {temp_video_path}")
            else:
                logger.error(f"❌ Archivo local no encontrado: {expanded_path}")
                return []
        else:
            # Es una ruta de almacenamiento: descargar.
            temp_video_path = self.motion_detector.download_from_storage(video_path)
        
        if not temp_video_path:
            logger.error("❌ No se pudo obtener el video")
            return []
        
        try:
            # Callback para progreso
            def progress_callback(percentage):
                if int(percentage) % 10 == 0:
                    logger.info(f"   Progreso: {percentage:.1f}%")
            
            # Detectar movimiento
            segments = self.motion_detector.detect_motion_segments(
                temp_video_path,
                progress_callback=progress_callback
            )
            
            # Actualizar estado
            video.actualizar_estado(EstadoSecurityVideo.MOTION_DETECTED)
            video.metadata_tecnico["motion_segments_count"] = len(segments)
            video.metadata_tecnico["temp_video_path"] = temp_video_path  # Guardar para uso posterior
            self.repository.guardar_video(video)
            
            logger.info(f"✅ Movimiento detectado en {len(segments)} segmentos")
            return segments
        
        except Exception as e:
            logger.error(f"❌ Error en motion detection: {e}")
            self.motion_detector.cleanup_temp_file(temp_video_path)
            return []
    
    def _extract_motion_clips(
        self, video: SecurityVideo, segments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extrae clips de los segmentos con movimiento"""
        logger.info("✂️ Extrayendo clips de segmentos con movimiento")
        
        temp_video_path = video.metadata_tecnico.get("temp_video_path")
        if not temp_video_path:
            logger.error("❌ No hay video temporal")
            return []
        
        # Crear directorio temporal para clips
        clips_dir = tempfile.mkdtemp(prefix="security_clips_")
        
        # Ruta base de almacenamiento para clips.
        storage_base_path = f"{video.storage_path.rsplit('/', 1)[0]}/clips/{video.id}"
        
        # Extraer clips
        clips = self.video_segmentation.batch_extract_clips(
            temp_video_path,
            segments,
            clips_dir,
            upload_to_storage=True,
            storage_base_path=storage_base_path
        )
        
        logger.info(f"✅ Clips extraídos: {len(clips)}")
        return clips
    
    def _phase_gemini_classification(
        self, video: SecurityVideo, clips: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """FASE 6: Clasificación con Gemini Vision (PARALELO)"""
        logger.info("🤖 FASE 6: Clasificación con Gemini Vision (paralelo)")
        
        video.actualizar_estado(EstadoSecurityVideo.CLASSIFYING)
        self.repository.guardar_video(video)
        
        self._init_gemini()
        if not self.gemini_adapter or not self.gemini_adapter.is_available():
            logger.error("❌ Gemini no disponible")
            return clips
        
        classified_clips = []
        total_clips = len(clips)
        processed_count = 0
        
        def process_single_clip(args):
            """Procesa un clip individual (thread-safe)"""
            idx, clip = args
            try:
                # Extraer frames del clip
                clip_path = clip.get("clip_path_local")
                if not clip_path or not os.path.exists(clip_path):
                    return None
                
                frames_dir = tempfile.mkdtemp(prefix="frames_")
                frame_paths = self.video_segmentation.extract_frames_from_clip(
                    clip_path,
                    num_frames=5,
                    output_dir=frames_dir
                )
                
                if not frame_paths:
                    return None
                
                # Convertir frames a base64
                import base64
                frames_base64 = []
                for frame_path in frame_paths:
                    with open(frame_path, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode("utf-8")
                        frames_base64.append(b64_data)
                
                # Clasificar con Gemini (con retry automático)
                clasificacion_result = self._classify_with_gemini_retry(
                    frames_base64, video, clip
                )
                
                # Guardar el primer frame para el reporte (en lugar de eliminarlo)
                saved_frame_path = None
                if frame_paths:
                    # Crear directorio para frames del reporte si no existe
                    report_frames_base = os.path.join(tempfile.gettempdir(), "security_report_frames")
                    os.makedirs(report_frames_base, exist_ok=True)
                    
                    # Copiar el primer frame con nombre único
                    import shutil
                    frame_filename = f"frame_{video.id}_{idx:04d}.jpg"
                    saved_frame_path = os.path.join(report_frames_base, frame_filename)
                    try:
                        shutil.copy2(frame_paths[0], saved_frame_path)
                        logger.debug(f"📸 Frame guardado para reporte: {saved_frame_path}")
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudo guardar frame: {e}")
                        saved_frame_path = None
                
                # Cleanup frames restantes (excepto el que guardamos)
                for frame_path in frame_paths[1:]:
                    try:
                        os.remove(frame_path)
                    except Exception as e:
                        logger.debug(f"Could not remove frame file: {e}")
                # Eliminar primer frame del temporal
                if frame_paths and os.path.exists(frame_paths[0]):
                    try:
                        os.remove(frame_paths[0])
                    except Exception as e:
                        logger.debug(f"Could not remove first frame: {e}")
                try:
                    os.rmdir(frames_dir)
                except Exception as e:
                    logger.debug(f"Could not remove frames directory: {e}")
                
                # Agregar clasificación al clip con ruta del frame guardado
                clip_classified = clip.copy()
                clip_classified.update(clasificacion_result)
                if saved_frame_path:
                    clip_classified['frame_path'] = saved_frame_path
                return (idx, clip_classified)
            
            except Exception as e:
                logger.error(f"❌ Error clasificando clip {idx}: {e}")
                clip_copy = clip.copy()
                clip_copy["clasificacion"] = ClasificacionEvento.NORMAL
                clip_copy["confianza"] = 0.5
                clip_copy["descripcion_gemini"] = f"Error en clasificación: {str(e)}"
                return (idx, clip_copy)
        
        # Procesamiento paralelo con ThreadPoolExecutor
        logger.info(f"🔄 Procesando {total_clips} clips con {self.max_parallel_workers} workers paralelos")
        sec_logger.info(f"Iniciando clasificación paralela: {total_clips} clips, {self.max_parallel_workers} workers")
        
        with ThreadPoolExecutor(max_workers=self.max_parallel_workers) as executor:
            # Enviar todos los clips al pool
            futures = {
                executor.submit(process_single_clip, (i, clip)): i 
                for i, clip in enumerate(clips)
            }
            
            # Recolectar resultados a medida que completan
            results = [None] * total_clips
            for future in as_completed(futures):
                result = future.result()
                if result:
                    idx, clip_classified = result
                    results[idx] = clip_classified
                    processed_count += 1
                    
                    # Log progreso cada 10 clips
                    if processed_count % 10 == 0 or processed_count == total_clips:
                        sec_logger.log_progress(processed_count, total_clips, "Clasificación paralela")
                        logger.info(f"   Progreso: {processed_count}/{total_clips} clips")
        
        # Filtrar None y mantener orden
        classified_clips = [r for r in results if r is not None]
        
        video.actualizar_estado(EstadoSecurityVideo.CLASSIFIED)
        self.repository.guardar_video(video)
        
        logger.info(f"✅ Clips clasificados: {len(classified_clips)}/{total_clips}")
        sec_logger.info(f"Clasificación paralela completada: {len(classified_clips)}/{total_clips}")
        return classified_clips
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((Exception,)),
        before_sleep=lambda retry_state: logger.warning(
            f"⚠️ Retry Gemini: intento {retry_state.attempt_number}, esperando {retry_state.next_action.sleep}s"
        )
    )
    def _classify_with_gemini_retry(
        self, frames_base64: List[str], video: SecurityVideo, clip: Dict
    ) -> Dict[str, Any]:
        """
        Wrapper con retry exponencial para llamadas a Gemini.
        Maneja rate limiting y errores transitorios automáticamente.
        """
        return self._classify_with_gemini(frames_base64, video, clip)
    
    def _classify_with_gemini(
        self, frames_base64: List[str], video: SecurityVideo, clip: Dict
    ) -> Dict[str, Any]:
        """Clasifica un clip con Gemini Vision con gestión de cuotas"""
        prompt = f"""Analiza estos frames de una cámara de seguridad.
        
Ubicación: {video.ubicacion}
Cámara: {video.nombre_camara}
Timestamp: {clip.get('timestamp_inicio', 0):.1f}s

Clasifica el contenido como:
- NORMAL: Actividad rutinaria (personas caminando, vehículos pasando, etc.)
- SOSPECHOSO: Comportamiento inusual que requiere revisión
- IMPORTANTE: Incidente de seguridad, emergencia, o evento crítico

Responde SOLO en formato JSON sin markdown:
{{
    "clasificacion": "NORMAL",
    "confianza": 0.85,
    "descripcion": "Descripción breve del evento"
}}"""
        
        try:
            # Adquirir cuota de Gemini (con rate limiting)
            try:
                self.quota_manager.acquire_gemini(blocking=True, timeout=60.0)
            except QuotaExceededException as qe:
                logger.warning(f"⚠️ Cuota de Gemini agotada: {qe}")
                # Retornar clasificación por defecto
                return {
                    "clasificacion": ClasificacionEvento.NORMAL,
                    "confianza": 0.5,
                    "descripcion_gemini": "Cuota de API agotada, clasificación pendiente",
                }
            
            # Llamar a Gemini
            response = self.gemini_adapter.analyze_frames(prompt, frames_base64)
            
            # analyze_frames devuelve: {'success': bool, 'analisis': dict, ...}
            if not isinstance(response, dict):
                import json
                response = json.loads(response)
            
            # Verificar si la llamada fue exitosa
            if not response.get('success', False):
                error_msg = response.get('error', 'Error desconocido')
                logger.warning(f"⚠️ Gemini no pudo analizar: {error_msg}")
                return {
                    "clasificacion": ClasificacionEvento.NORMAL,
                    "confianza": 0.5,
                    "descripcion_gemini": f"Error de análisis: {error_msg}",
                }
            
            # Extraer el análisis real
            analisis = response.get('analisis', {})
            
            # Obtener clasificación (puede estar en varios formatos)
            clasificacion_raw = analisis.get('clasificacion', 'normal')
            if isinstance(clasificacion_raw, str):
                clasificacion_raw = clasificacion_raw.upper().strip()
            
            # Mapear clasificación a enum válido
            clasificacion_map = {
                'NORMAL': ClasificacionEvento.NORMAL,
                'SOSPECHOSO': ClasificacionEvento.SOSPECHOSO,
                'IMPORTANTE': ClasificacionEvento.IMPORTANTE,
                'SUSPICIOUS': ClasificacionEvento.SOSPECHOSO,
                'IMPORTANT': ClasificacionEvento.IMPORTANTE,
                'CRITICAL': ClasificacionEvento.IMPORTANTE,
            }
            clasificacion = clasificacion_map.get(clasificacion_raw, ClasificacionEvento.NORMAL)
            
            # Obtener confianza
            confianza = analisis.get('confianza', 0.7)
            if isinstance(confianza, str):
                try:
                    confianza = float(confianza)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse confidence value: {e}")
                    confianza = 0.7
            confianza = max(0.0, min(1.0, float(confianza)))
            
            # Obtener descripción
            descripcion = analisis.get('descripcion', analisis.get('descripcion_contenido', ''))
            if not descripcion:
                descripcion = f"Clip analizado - Clasificación: {clasificacion_raw}"
            
            logger.info(f"✅ Clasificación Gemini: {clasificacion_raw} (confianza: {confianza:.2f})")
            
            return {
                "clasificacion": clasificacion,
                "confianza": confianza,
                "descripcion_gemini": descripcion[:500],  # Limitar longitud
            }
        
        except Exception as e:
            logger.error(f"Error en clasificación Gemini: {e}", exc_info=True)
            return {
                "clasificacion": ClasificacionEvento.NORMAL,
                "confianza": 0.5,
                "descripcion_gemini": f"Error: {str(e)}",
            }
    
    def _phase_deep_analysis(
        self, video: SecurityVideo, eventos_importantes: List[Dict[str, Any]]
    ):
        """FASE 7: Análisis profundo con Video Intelligence"""
        logger.info("🔬 FASE 7: Análisis profundo con Video Intelligence")
        
        video.actualizar_estado(EstadoSecurityVideo.DEEP_ANALYZING)
        self.repository.guardar_video(video)
        
        self._init_video_intelligence()
        if not self.video_intelligence or not self.video_intelligence.is_available():
            logger.warning("⚠️ Video Intelligence no disponible")
            return
        
        for i, evento in enumerate(eventos_importantes):
            try:
                logger.info(f"   Analizando evento {i+1}/{len(eventos_importantes)}")
                
                # Obtener GCS URI del clip
                clip_url = evento.get("clip_url")
                if not clip_url:
                    continue
                
                # Analizar con Video Intelligence
                features = [
                    "PERSON_DETECTION",
                    "OBJECT_TRACKING",
                    "FACE_DETECTION",
                    "LABEL_DETECTION",
                ]
                
                analysis = self.video_intelligence.analyze_video(clip_url, features)
                
                if analysis:
                    evento["analisis_profundo"] = analysis
                    logger.info(f"   ✅ Análisis completado para evento {i+1}")
            
            except Exception as e:
                logger.error(f"❌ Error analizando evento {i}: {e}")
    
    def _save_events(self, video: SecurityVideo, segments: List[Dict[str, Any]]):
        """Guarda eventos en el repositorio"""
        logger.info("💾 Guardando eventos en repositorio")
        sec_logger.info(f"Iniciando guardado de {len(segments)} eventos")
        
        eventos_guardados = 0
        errores = 0
        
        for i, segment in enumerate(segments):
            try:
                evento_id = f"evt_{video.id}_{uuid.uuid4().hex[:8]}"
                sec_logger.debug(f"Guardando evento {i+1}/{len(segments)}: {evento_id}")
                
                # Crear copia de metadata sin enums para Firestore
                metadata_safe = {}
                for key, value in segment.items():
                    if isinstance(value, ClasificacionEvento):
                        metadata_safe[key] = value.value
                    elif hasattr(value, '__dict__'):
                        # Convertir objetos complejos a dict
                        metadata_safe[key] = str(value)
                    else:
                        metadata_safe[key] = value
                
                # Asegurar que clasificación es un enum válido
                clasificacion = segment.get("clasificacion", ClasificacionEvento.NORMAL)
                if isinstance(clasificacion, str):
                    try:
                        clasificacion = ClasificacionEvento(clasificacion.lower())
                    except ValueError:
                        clasificacion = ClasificacionEvento.NORMAL
                
                evento = EventoSeguridad(
                    id=evento_id,
                    security_video_id=video.id,
                    timestamp_inicio=float(segment.get("timestamp_inicio", 0)),
                    timestamp_fin=float(segment.get("timestamp_fin", 0)),
                    duracion=float(segment.get("duracion", 0)),
                    clasificacion=clasificacion,
                    confianza=float(segment.get("confianza", 0.5)),
                    descripcion_gemini=str(segment.get("descripcion_gemini", ""))[:1000],
                    analisis_profundo=segment.get("analisis_profundo") or {},
                    clip_url=str(segment.get("clip_url", "")),
                    frames_urls=segment.get("frames_urls") or [],
                    metadata=metadata_safe,
                )
                
                if not self.repository.guardar_evento(evento):
                    raise RuntimeError(f"No se pudo persistir el evento {evento_id}")
                eventos_guardados += 1
                sec_logger.debug(f"✅ Evento {evento_id} guardado correctamente")
            
            except Exception as e:
                errores += 1
                sec_logger.error(f"Error guardando evento {i+1}: {e}", exc_info=True)
                logger.error(f"❌ Error guardando evento {i+1}: {e}", exc_info=True)
        
        sec_logger.info(f"Guardado completado: {eventos_guardados}/{len(segments)} eventos OK, {errores} errores")
        logger.info(f"✅ Eventos guardados: {eventos_guardados}/{len(segments)}")
    
    def _phase_generate_report(self, video: SecurityVideo):
        """FASE 8: Generación de reporte profesional"""
        logger.info("📄 FASE 8: Generación de reporte")
        
        video.actualizar_estado(EstadoSecurityVideo.GENERATING_REPORT)
        self.repository.guardar_video(video)
        
        try:
            # Obtener eventos del video
            eventos = self.repository.obtener_eventos_video(video.id)
            logger.info(f"📊 Generando reporte con {len(eventos)} eventos")
            
            # Directorio para reportes locales
            reports_dir = os.path.join(tempfile.gettempdir(), "security_reports")
            os.makedirs(reports_dir, exist_ok=True)
            
            # Generar reporte TXT
            txt_filename = f"reporte_{video.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
            txt_path = os.path.join(reports_dir, txt_filename)
            
            if self.report_generator.save_text_report(video, eventos, txt_path):
                logger.info(f"✅ Reporte TXT guardado: {txt_path}")
                video.reporte_txt_url = txt_path

                is_local_test = video.metadata_tecnico.get('is_local_test', False)
                if not is_local_test:
                    try:
                        from config.app_config import AppConfig
                        backend = getattr(AppConfig, "STORAGE_BACKEND", "filesystem")
                        if backend == "minio":
                            from infrastructure.adapters.minio_storage_adapter import MinioStorageAdapter
                            storage = MinioStorageAdapter(AppConfig)
                        else:
                            from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
                            storage = FilesystemStorageAdapter()
                        if storage.is_available():
                            txt_storage_path = f"reportes/{video.id}/{txt_filename}"
                            txt_url = storage.upload_file(txt_path, txt_storage_path, content_type='text/plain')
                            if txt_url:
                                video.reporte_txt_url = txt_url
                                logger.info(f"✅ Reporte TXT subido a storage: {txt_url}")
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudo subir TXT a storage: {e}")
            
            # Generar reporte PDF MEJORADO (con imágenes y timeline)
            pdf_filename = f"reporte_{video.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
            pdf_path = os.path.join(reports_dir, pdf_filename)
            
            # Preparar datos del video para el generador mejorado
            video_data = {
                'id': video.id,
                'nombre_camara': video.nombre_camara,
                'ubicacion': video.ubicacion,
                'fecha_grabacion': video.fecha_grabacion,
                'duracion_segundos': video.duracion_segundos,
                'tiempo_procesamiento': video.tiempo_procesamiento_segundos or 0,
                'width': video.metadata_tecnico.get('width', 'N/A'),
                'height': video.metadata_tecnico.get('height', 'N/A'),
            }
            
            # Convertir eventos a formato dict para el generador
            eventos_dict = []
            for evt in eventos:
                evt_dict = {
                    'timestamp_inicio': evt.timestamp_inicio,
                    'timestamp_fin': evt.timestamp_fin,
                    'duracion': evt.duracion,
                    'clasificacion': evt.clasificacion.value.upper() if hasattr(evt.clasificacion, 'value') else str(evt.clasificacion).upper(),
                    'confianza': evt.confianza,
                    'descripcion_gemini': evt.descripcion_gemini,
                    'analisis_profundo': evt.analisis_profundo or {},
                    'frame_path': evt.metadata.get('frame_path') if evt.metadata else None,
                    'clip_url': evt.clip_url,
                }
                eventos_dict.append(evt_dict)
            
            # Generar PDF mejorado con imágenes
            if self.report_generator.generate_enhanced_pdf(video_data, eventos_dict, pdf_path):
                logger.info(f"✅ Reporte PDF MEJORADO guardado: {pdf_path}")
                video.reporte_pdf_url = pdf_path
                
                if not is_local_test:
                    try:
                        pdf_storage_path = f"reportes/{video.id}/{pdf_filename}"
                        pdf_url = storage.upload_file(pdf_path, pdf_storage_path, content_type='application/pdf')
                        if pdf_url:
                            video.reporte_pdf_url = pdf_url
                            logger.info(f"✅ Reporte PDF subido a storage: {pdf_url}")
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudo subir PDF a storage: {e}")
            else:
                logger.warning("⚠️ No se pudo generar PDF (ReportLab no disponible)")
            
            # Guardar URLs en el video
            self.repository.guardar_video(video)
            logger.info("✅ Reportes generados y almacenados")
            
        except Exception as e:
            logger.error(f"❌ Error generando reportes: {e}")
            raise
    
    def _calculate_statistics(self, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcula estadísticas del análisis"""
        stats = {
            "eventos_totales": len(segments),
            "eventos_normales": len(
                [s for s in segments if s.get("clasificacion") == ClasificacionEvento.NORMAL]
            ),
            "eventos_sospechosos": len(
                [s for s in segments if s.get("clasificacion") == ClasificacionEvento.SOSPECHOSO]
            ),
            "eventos_importantes": len(
                [s for s in segments if s.get("clasificacion") == ClasificacionEvento.IMPORTANTE]
            ),
        }
        return stats
    
    def _send_immediate_alert(self, video: SecurityVideo, eventos_importantes: List[Dict]):
        """
        🚨 ALERTA INMEDIATA: Envía notificación en tiempo real cuando se 
        detectan eventos IMPORTANTES, sin esperar a que termine el análisis.
        """
        logger.info(f"🚨 Enviando alerta INMEDIATA: {len(eventos_importantes)} eventos importantes")
        sec_logger.info(f"Alerta inmediata: {len(eventos_importantes)} eventos importantes detectados")
        
        try:
            # Obtener email del metadata (si el usuario lo proporcionó)
            notify_email = video.metadata_tecnico.get('notify_email', self.alert_email)
            
            # Generar resumen de eventos para la alerta
            eventos_resumen = []
            for i, evento in enumerate(eventos_importantes[:5], 1):  # Máximo 5
                timestamp = evento.get('timestamp_inicio', 0)
                hours = int(timestamp // 3600)
                mins = int((timestamp % 3600) // 60)
                secs = int(timestamp % 60)
                timestamp_str = f"{hours:02d}:{mins:02d}:{secs:02d}"
                
                descripcion = evento.get('descripcion_gemini', 'Evento importante detectado')[:100]
                eventos_resumen.append(f"  • [{timestamp_str}] {descripcion}")
            
            eventos_texto = "\n".join(eventos_resumen)
            
            # Enviar email de alerta
            self.notification_service.send_email(
                to=notify_email,
                subject=f"🚨 ALERTA: {len(eventos_importantes)} eventos importantes - {video.nombre_camara}",
                body=f"""
⚠️ ALERTA DE SEGURIDAD - ATENCIÓN INMEDIATA REQUERIDA

Se han detectado {len(eventos_importantes)} eventos IMPORTANTES en el video:

📹 Cámara: {video.nombre_camara}
📍 Ubicación: {video.ubicacion}
📅 Fecha: {video.fecha_grabacion}

EVENTOS DETECTADOS:
{eventos_texto}

{'...(y más eventos)' if len(eventos_importantes) > 5 else ''}

El análisis aún está en progreso. Recibirás el reporte completo cuando finalice.

⚡ Esta es una notificación automática de alta prioridad.

--
Sistema TIVIT-CU002 Security Intelligence
                """
            )
            
            logger.info(f"✅ Alerta inmediata enviada a {notify_email}")
            sec_logger.info(f"Alerta inmediata enviada a {notify_email}")
            
        except Exception as e:
            logger.warning(f"⚠️ No se pudo enviar alerta inmediata: {e}")
            sec_logger.warning(f"Error enviando alerta inmediata: {e}")
    
    def _send_email_notification(self, video: SecurityVideo, eventos_importantes: List[Dict]):
        """Envía notificación por email sobre eventos de seguridad"""
        logger.info("📧 Enviando notificación por email")
        
        try:
            # Preparar datos del video
            video_data = {
                'id': video.id,
                'nombre_camara': video.nombre_camara,
                'ubicacion': video.ubicacion,
                'fecha_grabacion': video.fecha_grabacion,
                'duracion_segundos': video.duracion_segundos,
                'tiempo_procesamiento_segundos': video.tiempo_procesamiento_segundos,
                'reporte_url': video.reporte_txt_url or video.reporte_pdf_url,
                'video_url': video.storage_path,
            }
            
            # Separar eventos sospechosos de importantes
            sospechosos = [
                s for s in eventos_importantes 
                if s.get('clasificacion') == ClasificacionEvento.SOSPECHOSO
            ]
            importantes = [
                s for s in eventos_importantes 
                if s.get('clasificacion') == ClasificacionEvento.IMPORTANTE
            ]
            
            # Enviar alerta si hay eventos importantes o sospechosos
            if importantes or sospechosos:
                self.notification_service.send_security_alert(
                    to_email=self.alert_email,
                    video_data=video_data,
                    eventos_importantes=importantes,
                    eventos_sospechosos=sospechosos
                )
                logger.info(f"✅ Alerta de seguridad enviada a {self.alert_email}")
            else:
                logger.info("ℹ️ No hay eventos importantes para notificar")
                
        except Exception as e:
            logger.error(f"❌ Error enviando notificación: {e}")

    def _send_completion_notification(self, video: SecurityVideo):
        """Envía notificación cuando el procesamiento finaliza exitosamente"""
        try:
            video_data = {
                'id': video.id,
                'nombre_camara': video.nombre_camara,
                'ubicacion': video.ubicacion,
                'fecha_grabacion': video.fecha_grabacion,
                'duracion_segundos': video.duracion_segundos,
                'tiempo_procesamiento_segundos': video.tiempo_procesamiento_segundos,
            }
            
            self.notification_service.send_security_processing_complete(
                to_email=self.alert_email,
                video_data=video_data,
                estadisticas=video.estadisticas or {}
            )
            logger.info(f"📧 Notificación de completado enviada a {self.alert_email}")
            
        except Exception as e:
            logger.error(f"❌ Error enviando notificación de completado: {e}")

    def _send_error_notification(self, video: SecurityVideo, error_message: str):
        """Envía notificación cuando hay un error en el procesamiento"""
        try:
            video_data = {
                'id': video.id,
                'nombre_camara': video.nombre_camara,
                'ubicacion': video.ubicacion,
                'fecha_grabacion': video.fecha_grabacion,
            }
            
            self.notification_service.send_security_error(
                to_email=self.alert_email,
                video_data=video_data,
                error_message=error_message
            )
            logger.info(f"📧 Notificación de error enviada a {self.alert_email}")
            
        except Exception as e:
            logger.error(f"❌ Error enviando notificación de error: {e}")
