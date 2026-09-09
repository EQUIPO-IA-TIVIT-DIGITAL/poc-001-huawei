"""
Procesador Completo de Videos de Seguridad v3.0
Orquestador de Pipeline Refactorizado para SRP.
"""

import logging
import os
import tempfile
import time
from datetime import datetime
from typing import Optional, Dict, List, Any

from domain.entities import SecurityVideo, EventoSeguridad, EstadoSecurityVideo
from infrastructure.repositories.security_video_repository import SecurityVideoRepository
from infrastructure.services.optimized_video_processor import OptimizedVideoProcessor
# Módulos especializados
from use_cases.security.downloader import SecurityVideoDownloader
from use_cases.security.scanner import SecurityVideoScanner
from use_cases.security.analyzer import SecurityVideoGeminiAnalyzer
from use_cases.security.reporter import SecurityVideoReportGenerator

logger = logging.getLogger(__name__)

class CompleteSecurityVideoProcessor:
    ANALYSIS_RESOLUTION = (640, 480)
    MOTION_THRESHOLD = 0.008

    def __init__(self, max_parallel_workers: int = 4):
        self.repository = SecurityVideoRepository()
        self.optimized_processor = OptimizedVideoProcessor(
            target_resolution=self.ANALYSIS_RESOLUTION,
            frame_skip_rate=3,
            motion_threshold=self.MOTION_THRESHOLD
        )
        self.max_parallel_workers = max_parallel_workers
        self._temp_dir = None

        self.downloader = SecurityVideoDownloader(self.optimized_processor)
        self.scanner = SecurityVideoScanner()
        
        self.gemini_adapter = None
        self.storage_adapter = None
        self.analyzer = None
        self.reporter = None

    def _init_lazy_dependencies(self):
        if self.gemini_adapter is None:
            from infrastructure.adapters.ai_gateway import get_ai_gateway
            self.gemini_adapter = get_ai_gateway()
        if self.storage_adapter is None:
            from config.app_config import AppConfig
            backend = getattr(AppConfig, "STORAGE_BACKEND", "filesystem")
            if backend == "minio":
                from infrastructure.adapters.minio_storage_adapter import MinioStorageAdapter
                self.storage_adapter = MinioStorageAdapter(AppConfig)
            else:
                from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
                self.storage_adapter = FilesystemStorageAdapter()
        
        if self.analyzer is None:
            self.analyzer = SecurityVideoGeminiAnalyzer(
                gemini_adapter=self.gemini_adapter,
                storage_adapter=self.storage_adapter,
                optimized_processor=self.optimized_processor,
                get_temp_dir_func=self._get_temp_dir,
                update_progress_func=self._update_progress
            )
        if self.reporter is None:
            self.reporter = SecurityVideoReportGenerator(
                storage_adapter=self.storage_adapter,
                repository=self.repository
            )

    def _get_temp_dir(self) -> str:
        if self._temp_dir is None or not os.path.exists(self._temp_dir):
            self._temp_dir = tempfile.mkdtemp(prefix='security_analysis_')
        return self._temp_dir

    def _cleanup_temp(self):
        if self._temp_dir and os.path.exists(self._temp_dir):
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def _update_progress(self, video: SecurityVideo, message: str, progress_pct: int = 0, fase: str = None, paso_actual: int = None, total_pasos: int = None):
        try:
            progreso_anterior = video.metadata_tecnico.get('progreso_analisis', {})
            timestamp_anterior = progreso_anterior.get('timestamp')
            
            eta_segundos = 0
            if timestamp_anterior and progress_pct > 0 and progress_pct < 100:
                try:
                    tiempo_anterior = datetime.fromisoformat(timestamp_anterior)
                    elapsed = (datetime.utcnow() - tiempo_anterior).total_seconds()
                    progreso_anterior_pct = progreso_anterior.get('porcentaje', 0)
                    if progreso_anterior_pct < progress_pct:
                        progreso_delta = progress_pct - progreso_anterior_pct
                        if progreso_delta > 0:
                            eta_segundos = int((elapsed / progreso_delta) * (100 - progress_pct))
                except Exception: pass
            
            progreso = {
                'fase': fase or progreso_anterior.get('fase', 'inicio'),
                'mensaje': message, 'porcentaje': progress_pct,
                'eta_segundos': eta_segundos,
                'timestamp': datetime.utcnow().isoformat()
            }
            if paso_actual is not None and total_pasos is not None:
                progreso['paso_actual'] = paso_actual
                progreso['total_pasos'] = total_pasos
            
            video.metadata_tecnico['progreso_analisis'] = progreso
            self.repository.guardar_video(video)
        except Exception: pass

    def _get_video_metadata(self, video_path: str) -> Optional[Dict]:
        try:
            from infrastructure.adapters.video_segmentation import VideoSegmentationAdapter
            segmentation = VideoSegmentationAdapter()
            if segmentation.is_available():
                return segmentation.get_video_metadata(video_path)
        except Exception:
            pass
        return None

    def process_video_complete(self, video_id: str):
        start_time = time.time()
        vid = video_id[:8]
        phase_timings = {}
        
        try:
            logger.info(f"[{vid}] 🚀 PIPELINE ORQUESTADOR v3.1 - Video: {video_id}")
            
            video = self.repository.obtener_video(video_id)
            if not video:
                raise ValueError(f"Video no encontrado: {video_id}")
            
            video.actualizar_estado(EstadoSecurityVideo.MOTION_DETECTING)
            self.repository.guardar_video(video)
            
            # FASE 1: Descarga
            self._update_progress(video, "Descargando video...", 5, fase='descarga')
            local_video_path = self.downloader.download_or_get_cached(video_id, video.storage_path)
            logger.info(f"[{vid}] 📥 Video cacheado/descargado en {local_video_path}")
            
            try:
                self._update_progress(video, "Metadata del video...", 10, fase='descarga')
                video_metadata = self._get_video_metadata(local_video_path)
                if video_metadata:
                    video.metadata_tecnico.update(video_metadata)
                    self.repository.guardar_video(video)
                
                # FASE 2: Escaneo Denso
                pre_duration = video.duracion_segundos or video_metadata.get('duration_seconds', 0) if video_metadata else video.duracion_segundos or 0
                adapt_interval = self.scanner.get_adaptive_scan_interval(pre_duration)
                
                self.scanner.init_dense_scanner(adapt_interval)
                scan_start = time.time()
                frame_analyses = self.scanner.dense_scanner.scan_video(local_video_path, video_id)
                phase_timings['fase1_scan'] = time.time() - scan_start
                
                self._update_progress(video, "Clasificando eventos...", 22, fase='scan')
                video_duration = video.duracion_segundos or video_metadata.get('duration_seconds', 0) if video_metadata else video.duracion_segundos or 0
                detected_events = self.scanner.dense_scanner.classify_events(frame_analyses, video_duration, video_id)
                
                max_segs = self.scanner.calculate_max_segments(video_duration)
                motion_segments = self.scanner.dense_scanner.events_to_segments(
                    detected_events, video_duration, max_segment_duration=30.0, max_segments=max_segs, video_id=video_id
                )

                if not motion_segments:
                    video.actualizar_estado(EstadoSecurityVideo.COMPLETED)
                    video.fecha_procesamiento = datetime.utcnow().isoformat()
                    self.repository.guardar_video(video)
                    return
                
                video.actualizar_estado(EstadoSecurityVideo.MOTION_DETECTED)
                self.repository.guardar_video(video)
                
                # FASE 3: Análisis Gemini
                self._init_lazy_dependencies()
                self._update_progress(video, f"Analizando {len(motion_segments)} clips...", 30, fase='analisis')
                video.actualizar_estado(EstadoSecurityVideo.ANALYZING)
                self.repository.guardar_video(video)
                
                # Pasar eventos_map al analyzer
                self.analyzer.events_map = {}
                for ev in detected_events:
                    for seg in motion_segments:
                        if (ev.start_second <= seg.start_second <= ev.end_second or ev.start_second <= seg.end_second <= ev.end_second):
                            self.analyzer.events_map[seg.start_second] = ev

                analyze_start = time.time()
                all_events = self.analyzer.analyze_all_segments(video_id, local_video_path, motion_segments, video)
                phase_timings['fase2_gemini'] = time.time() - analyze_start
                
                # FASE 4: Cross Análisis
                self._update_progress(video, "Análisis cruzado...", 80, fase='cross')
                cross_start = time.time()
                cross_analysis = self.analyzer.perform_cross_analysis(video, all_events)
                phase_timings['fase3_cross'] = time.time() - cross_start
                
                # Guardar eventos
                self._save_all_events(video_id, all_events)
                self._update_video_statistics(video, all_events, cross_analysis)
                
                # FASE 5: Reportes
                self._update_progress(video, "Generando reportes...", 90, fase='reportes')
                video.actualizar_estado(EstadoSecurityVideo.GENERATING_REPORT)
                self.repository.guardar_video(video)
                
                report_start = time.time()
                self.reporter.generate_complete_report(video, all_events, cross_analysis)
                phase_timings['fase4_reports'] = time.time() - report_start
                
                video.actualizar_estado(EstadoSecurityVideo.COMPLETED)
                video.tiempo_procesamiento_segundos = time.time() - start_time
                video.fecha_procesamiento = datetime.utcnow().isoformat()
                self.repository.guardar_video(video)
                
                self.reporter.notify_analysis_complete(video, all_events, cross_analysis)
                self.downloader.clear_video_cache(video_id)
                
            finally:
                if os.path.exists(local_video_path) and not self.downloader.get_cached_video_path(video_id):
                    try: os.remove(local_video_path)
                    except: pass
                self._cleanup_temp()
                
        except Exception as e:
            logger.error(f"[{vid}] ❌ Error pipeline: {e}", exc_info=True)
            try:
                v = self.repository.obtener_video(video_id)
                if v:
                    v.actualizar_estado(EstadoSecurityVideo.ERROR)
                    v.metadata_tecnico['error'] = str(e)
                    self.repository.guardar_video(v)
            except: pass
            raise

    def _save_all_events(self, video_id: str, events: List[Dict]):
        if not events: return
        eventos_obj = []
        for ev in events:
            try:
                eventos_obj.append(EventoSeguridad(
                    id=ev['id'],
                    security_video_id=video_id,
                    timestamp_inicio=ev.get('timestamp_inicio', 0.0),
                    timestamp_fin=ev.get('timestamp_fin', 0.0),
                    duracion=ev.get('duracion', 0.1),
                    objetos_detectados=ev.get('objetos_detectados', []),
                    acciones_detectadas=ev.get('acciones_detectadas', []),
                    personas_count=ev.get('personas_count', 0),
                    vehiculos_count=ev.get('vehiculos_count', 0),
                    descripcion=ev.get('descripcion', ''),
                    confianza=ev.get('confianza', 0.0),
                    analisis_detallado=ev.get('analisis_detallado', {}),
                    frames_urls=ev.get('frames_urls', []),
                    metadata=ev.get('metadata', {})
                ))
            except Exception: pass
        self.repository.guardar_eventos_batch(video_id, eventos_obj)

    def _update_video_statistics(self, video: SecurityVideo, events: List[Dict], cross_analysis: Dict):
        try:
            riesgos = {'BAJO': 0, 'MEDIO': 0, 'ALTO': 0, 'CRITICO': 0}
            for ev in events:
                riesgos[ev.get('nivel_riesgo', 'BAJO')] = riesgos.get(ev.get('nivel_riesgo', 'BAJO'), 0) + 1
            
            dist_horas = {}
            for ev in events:
                h = str(int(ev['timestamp_inicio'] // 3600))
                dist_horas[h] = dist_horas.get(h, 0) + 1
                
            video.estadisticas = {
                'total_eventos': len(events),
                'duracion_analizada_segundos': sum(e.get('duracion', 0.0) for e in events),
                'total_personas_detectadas': sum(e.get('personas_count', 0) for e in events),
                'total_vehiculos_detectados': sum(e.get('vehiculos_count', 0) for e in events),
                'eventos_por_riesgo': riesgos,
                'nivel_riesgo_global': cross_analysis.get('nivel_riesgo_global', 'BAJO'),
                'resumen_ejecutivo': cross_analysis.get('resumen_ejecutivo', ''),
                'patrones_detectados': cross_analysis.get('patrones_detectados', []),
                'eventos_por_hora': dist_horas,
                'fecha_analisis': datetime.utcnow().isoformat(),
                'version_pipeline': '3.1_Orchestrated'
            }
            self.repository.guardar_video(video)
        except Exception: pass
