"""
Pipeline de Análisis Operativo v2.0 (Pipeline Pattern Refactor)

Mismo nivel de profundidad que CompleteSecurityVideoProcessor:
- Fase 0: Descarga del video de GCS
- Fase 1: Escaneo denso multinivel (Dense Scanner — 5 capas, cada 0.5s)
- Fase 2: Análisis con Gemini 2.5 Flash (prompts especializados por tipo)
- Fase 3: Meta-análisis cruzado y consolidación (deduplicación inteligente)
- Fase 4: Guardado + Generación de reporte operativo (PDF)

Modularizado en `use_cases/operational/`.
"""

import os
import json
import time
import logging
import tempfile
import shutil
from datetime import datetime

from domain.entities import (
    OperationalAnalysis, OperationalEvent,
    EstadoOperationalAnalysis, OPERATIONAL_ANALYSIS_TYPES
)
from infrastructure.repositories.operational_analysis_repository import OperationalAnalysisRepository
from infrastructure.services.dense_scanner import DenseVideoScanner
from infrastructure.services.optimized_video_processor import OptimizedVideoProcessor

from use_cases.operational.downloader import OperationalDownloader
from use_cases.operational.scanner import OperationalScanner
from use_cases.operational.segment_analyzer import OperationalSegmentAnalyzer
from use_cases.operational.cross_analyzer import OperationalCrossAnalyzer
from use_cases.operational.reporter import OperationalReporter
from infrastructure.services.log_utils import sanitize_context_for_log as _sanitize_context_for_log


logger = logging.getLogger(__name__)


class OperationalAnalyzer:
    """
    Pipeline completo de análisis operativo v2.0 ORQUESTADOR.
    Modularizado usando Pipeline Pattern.
    """

    MOTION_THRESHOLD = 0.008
    DENSE_SCAN_INTERVAL = 0.5
    REFERENCE_INTERVAL = 30.0

    def __init__(self):
        self.repo = OperationalAnalysisRepository()
        self.optimized_processor = OptimizedVideoProcessor(
            target_resolution=(640, 480),
            frame_skip_rate=3,
            motion_threshold=self.MOTION_THRESHOLD
        )
        
        # Lazy init
        self.dense_scanner = None
        self.gemini_adapter = None
        self.storage_adapter = None
        self._temp_dir = None
        
        self.downloader = OperationalDownloader(self.optimized_processor)

    def _init_dense_scanner(self):
        if self.dense_scanner is None:
            self.dense_scanner = DenseVideoScanner(
                sample_interval=self.DENSE_SCAN_INTERVAL,
                motion_threshold=self.MOTION_THRESHOLD,
                reference_interval=self.REFERENCE_INTERVAL
            )

    def _init_gemini(self):
        if self.gemini_adapter is None:
            from infrastructure.adapters.ai_gateway import get_ai_gateway
            self.gemini_adapter = get_ai_gateway()

    def _init_storage(self):
        if self.storage_adapter is None:
            from config.app_config import AppConfig
            backend = getattr(AppConfig, "STORAGE_BACKEND", "filesystem")
            if backend == "minio":
                from infrastructure.adapters.minio_storage_adapter import MinioStorageAdapter
                self.storage_adapter = MinioStorageAdapter(AppConfig)
            else:
                from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
                self.storage_adapter = FilesystemStorageAdapter()

    def _get_temp_dir(self) -> str:
        if self._temp_dir is None or not os.path.exists(self._temp_dir):
            # Directorio base configurable: OPERATIONAL_TMP_DIR > /tmp
            # En Cloud Run /tmp está limitado a 512 MB; montar un volumen y
            # apuntar OPERATIONAL_TMP_DIR a él para videos largos.
            base_tmp = os.environ.get("OPERATIONAL_TMP_DIR") or tempfile.gettempdir()
            os.makedirs(base_tmp, exist_ok=True)
            self._temp_dir = tempfile.mkdtemp(prefix="op_analysis_", dir=base_tmp)
            logger.info(f"Directorio temporal operativo: {self._temp_dir}")
        return self._temp_dir

    def _build_heatmap(self, events: list, video_duration: float) -> dict:
        if not events or not video_duration or video_duration <= 0:
            return {}

        bucket_size = max(30, int(video_duration / 20))
        num_buckets = max(1, int(video_duration / bucket_size) + 1)
        buckets = [0] * num_buckets

        for ev in events:
            ts = float(getattr(ev, 'timestamp_start', 0) or 0)
            idx = min(int(ts / bucket_size), num_buckets - 1)
            buckets[idx] += 1

        return {
            'buckets': buckets,
            'bucket_size': bucket_size,
            'max_count': max(buckets) if buckets else 1,
            'total_events': len(events),
            'video_duration': video_duration,
            'materialized': True,
        }

    def _cleanup_temp(self):
        if self._temp_dir and os.path.exists(self._temp_dir):
            try:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"No se pudo limpiar directorio temporal {self._temp_dir}: {e}")
            self._temp_dir = None

    def _check_cancelled(self, analysis_id: str) -> bool:
        try:
            a = self.repo.obtener_analisis(analysis_id)
            if a and a.estado == EstadoOperationalAnalysis.CANCELLED:
                logger.info(f"[{analysis_id[:8]}] ⚠️ Análisis CANCELADO por el usuario")
                return True
        except Exception as e:
            logger.warning(f"[{analysis_id[:8]}] ⚠️ No se pudo verificar estado de cancelación: {e}")
        return False

    def process(self, analysis_id: str, video_path: str = ""):
        vid = analysis_id[:8]
        pipeline_start = time.time()
        phase_timings = {}
        local_video_path = video_path
        _redis_lock_conn = None
        _redis_lock_key = None

        logger.info(f"[{vid}] ╔══════════════════════════════════════════════════════╗")
        logger.info(f"[{vid}] ║     PIPELINE ANÁLISIS OPERATIVO — INICIO            ║")
        logger.info(f"[{vid}] ╚══════════════════════════════════════════════════════╝")

        try:
            analysis = self.repo.obtener_analisis(analysis_id)
            if not analysis:
                raise ValueError(f"Análisis no encontrado: {analysis_id}")

            if analysis.estado == EstadoOperationalAnalysis.CANCELLED:
                logger.info(f"[{vid}] ⚠️ Análisis cancelado, abortando pipeline")
                return

            type_info = OPERATIONAL_ANALYSIS_TYPES.get(analysis.analysis_type, {})
            logger.info(f"[{vid}] 📋 Tipo: {type_info.get('icon', '📊')} {type_info.get('name', analysis.analysis_type)}")
            safe_context = _sanitize_context_for_log(analysis.custom_context)
            logger.info(f"[{vid}] 📋 Contexto: {safe_context or '(sin contexto adicional)'}")
            logger.info(f"[{vid}] 📋 Video: {analysis.video_filename}")

            analysis.started_at = datetime.utcnow().isoformat()
            analysis.actualizar_estado(EstadoOperationalAnalysis.DOWNLOADING, 'Descargando video...', 2)
            self.repo.guardar_analisis(analysis)

            # FASE 0: DESCARGAR VIDEO
            dl_res = self.downloader.download_and_get_metadata(analysis, vid, local_video_path)
            local_video_path = dl_res['local_video_path']
            video_duration = dl_res['duration_seconds']
            file_size_mb = dl_res['file_size_mb']
            dur_str = f"{video_duration/3600:.1f}h" if video_duration > 3600 else f"{video_duration/60:.1f}min"
            
            analysis.video_duration = video_duration
            analysis.video_size_mb = file_size_mb

            # DEDUP: Verificar cache de contenido por hash del video
            _vcache = None
            _cache_key = None
            try:
                from infrastructure.services.video_cache import get_video_analysis_cache
                from infrastructure.services.job_queue import get_redis_connection
                _vcache = get_video_analysis_cache()
                _video_hash = _vcache.compute_hash(local_video_path)
                import hashlib
                _ctx_str = (analysis.custom_context or "").strip().lower()
                _ctx_hash = hashlib.sha256(_ctx_str.encode('utf-8')).hexdigest()[:8]
                _cache_key = f"op:{_video_hash}:{analysis.analysis_type}:{_ctx_hash}"
                _cached = _vcache.get_cached_analysis(_cache_key)
                if _cached and _cached.get("original_analysis_id"):
                    orig_id = _cached["original_analysis_id"]
                    logger.info(f"[{vid}] ♻️ Cache hit — reutilizando análisis {orig_id[:8]}")
                    try:
                        orig_events = self.repo.obtener_eventos(orig_id)
                        expected_events = _cached.get("scan_stats", {}).get("total_events_detected", 0)
                        
                        if expected_events > 0 and len(orig_events) == 0:
                            _vcache.invalidate_by_video_hash(_video_hash)
                            raise Exception(f"Eventos no encontrados en DB para {orig_id}. Cache invalidado.")
                            
                        if orig_events:
                            import copy, uuid as _uuid
                            # Clonar eventos: nuevo id + nuevo analysis_id para que las
                            # queries por analysis_id del nuevo análisis los encuentren.
                            cloned = []
                            for ev in orig_events:
                                cloned_ev = copy.copy(ev)
                                cloned_ev.id = f"op_ev_{_uuid.uuid4().hex[:12]}"
                                cloned_ev.analysis_id = analysis_id
                                cloned.append(cloned_ev)
                            self.repo.guardar_eventos_batch(cloned, analysis_id)
                    except Exception as ev_err:
                        logger.warning(f"[{vid}] ⚠️ No se pudieron copiar eventos: {ev_err}")
                    analysis.summary = _cached.get("summary", {})
                    analysis.report_pdf_url = _cached.get("report_pdf_url", "")
                    analysis.scan_stats = _cached.get("scan_stats", {})
                    total_time = round(time.time() - pipeline_start, 2)
                    analysis.completed_at = datetime.utcnow().isoformat()
                    analysis.tiempo_procesamiento_segundos = total_time
                    analysis.actualizar_estado(EstadoOperationalAnalysis.COMPLETED, 'Completado (cache)', 100)
                    self.repo.guardar_analisis(analysis)
                    self._send_completion_notification(analysis, vid, success=True)
                    logger.info(f"[{vid}] ✅ Completado desde cache en {total_time:.1f}s")
                    return

                # Acquire a Redis lock to prevent two workers running the same pipeline
                # concurrently for the same video+type combination.
                # Using SET NX (atomic set-if-not-exists) — TTL = 2 hours (max pipeline time).
                _redis_lock_key = f"op_lock:{_cache_key}"
                _redis_lock_conn = get_redis_connection()
                lock_acquired = bool(
                    _redis_lock_conn.set(_redis_lock_key, analysis_id, nx=True, ex=7200)
                )
                if not lock_acquired:
                    logger.warning(
                        f"[{vid}] ⚠️ Otro worker ya está procesando este video/tipo "
                        f"(lock {_redis_lock_key[:30]}...) — continuando sin lock exclusivo"
                    )
                    _redis_lock_conn = None  # do NOT release a lock we don't own

            except Exception as cache_err:
                logger.warning(f"[{vid}] ⚠️ Error en cache de video, procesando normalmente: {cache_err}")

            # FASE 1: ESCANEO DENSO
            analysis.actualizar_estado(EstadoOperationalAnalysis.SCANNING, 'Fase 1: Escaneo denso', 10)
            self.repo.guardar_analisis(analysis)

            self._init_dense_scanner()
            scanner = OperationalScanner(self.dense_scanner)
            
            scan_start = time.time()
            scan_res = scanner.scan(local_video_path, video_duration, analysis_id, vid)
            scan_elapsed = time.time() - scan_start
            phase_timings['fase1_scan'] = scan_elapsed

            motion_segments = scan_res['motion_segments']
            detected_events = scan_res['detected_events']
            analysis.scan_stats = scan_res['stats']
            analysis.scan_stats['scan_time_s'] = round(scan_elapsed, 1)

            analysis.actualizar_estado(EstadoOperationalAnalysis.SCANNING, 'Escaneo completado', 20)
            self.repo.guardar_analisis(analysis)

            if not motion_segments:
                logger.warning(f"[{vid}] ⚠️ No se detectó actividad en el video")
                analysis.actualizar_estado(EstadoOperationalAnalysis.COMPLETED, 'Completado — sin actividad', 100)
                analysis.summary = {'message': 'No se detectó actividad en el video'}
                analysis.completed_at = datetime.utcnow().isoformat()
                analysis.tiempo_procesamiento_segundos = time.time() - pipeline_start
                self.repo.guardar_analisis(analysis)
                return

            # FASE 2: ANÁLISIS CON GEMINI
            analysis.actualizar_estado(EstadoOperationalAnalysis.ANALYZING, 'Fase 2: Análisis Gemini', 25)
            self.repo.guardar_analisis(analysis)

            self._init_gemini()
            self._init_storage()

            def progress_cb(completed, total):
                progress = 25 + (55 * completed / total)
                analysis.progress = progress
                analysis.current_phase = f'Segmento {completed}/{total}'
                self.repo.guardar_analisis(analysis)

            seg_analyzer = OperationalSegmentAnalyzer(self.gemini_adapter, self.storage_adapter, self._get_temp_dir())
            
            analyze_start = time.time()
            operational_events, segment_results = seg_analyzer.analyze_segments(
                analysis, vid, local_video_path, motion_segments, scan_res['detected_events_map'],
                progress_callback=progress_cb, check_cancelled=self._check_cancelled
            )
            analyze_elapsed = time.time() - analyze_start
            phase_timings['fase2_gemini'] = analyze_elapsed

            logger.info(f"[{vid}] ✅ Fase 2 completada: {len(operational_events)} eventos en {analyze_elapsed:.1f}s")


            # FASE 3: META-ANÁLISIS CRUZADO
            logger.info(f"[{vid}] \n[{vid}] 🧠 Fase 3: Meta-análisis cruzado (consolidación)")
            analysis.actualizar_estado(EstadoOperationalAnalysis.CROSS_ANALYZING, 'Fase 3: Análisis cruzado', 80)
            self.repo.guardar_analisis(analysis)

            cross_analyzer = OperationalCrossAnalyzer(self.gemini_adapter)
            cross_start = time.time()
            summary = cross_analyzer.cross_analyze(segment_results, analysis, video_duration, vid)
            cross_elapsed = time.time() - cross_start
            phase_timings['fase3_cross'] = cross_elapsed

            logger.info(f"[{vid}] ✅ Fase 3 completada en {cross_elapsed:.1f}s")


            # GUARDAR EVENTOS EN FIRESTORE
            save_start = time.time()
            logger.info(f"[{vid}] 💾 Guardando {len(operational_events)} eventos...")
            saved = self.repo.guardar_eventos_batch(operational_events, analysis_id)
            save_elapsed = time.time() - save_start
            phase_timings['save_firestore'] = save_elapsed
            
            # Truncate summary to avoid oversized document rows in the database
            if isinstance(summary, dict):
                analysis.summary = {
                    k: (str(v)[:500] if not isinstance(v, (dict, list)) else v)
                    for k, v in list(summary.items())[:40]
                }
            else:
                analysis.summary = {'raw': str(summary)[:2000]}
            analysis.scan_stats['heatmap'] = self._build_heatmap(operational_events, video_duration)
            analysis.scan_stats['total_events'] = len(operational_events)

            # FASE 4: REPORTES
            logger.info(f"[{vid}] \n[{vid}] 📄 Fase 4: Generando reportes operativos")
            analysis.actualizar_estado(EstadoOperationalAnalysis.GENERATING_REPORT, 'Fase 4: Reportes', 90)
            self.repo.guardar_analisis(analysis)

            reporter = OperationalReporter(self.storage_adapter, self._get_temp_dir())
            report_start = time.time()
            report_urls = reporter.generate_reports(analysis, operational_events, summary, vid)
            report_elapsed = time.time() - report_start
            phase_timings['fase4_reports'] = report_elapsed

            analysis.report_pdf_url = report_urls.get('pdf', '')


            # FINALIZAR
            total_time = time.time() - pipeline_start
            analysis.phase_timings = phase_timings
            analysis.completed_at = datetime.utcnow().isoformat()
            analysis.tiempo_procesamiento_segundos = total_time
            analysis.actualizar_estado(EstadoOperationalAnalysis.COMPLETED, 'Completado', 100)
            self.repo.guardar_analisis(analysis)

            # Guardar en cache para futura dedup de contenido idéntico
            if _vcache is not None and _cache_key is not None:
                try:
                    _vcache.store_analysis(_cache_key, {
                        "original_analysis_id": analysis_id,
                        "summary": analysis.summary or {},
                        "report_pdf_url": analysis.report_pdf_url or "",
                        "scan_stats": analysis.scan_stats or {},
                        "video_duration": analysis.video_duration,
                        "video_size_mb": analysis.video_size_mb,
                    })
                except Exception:
                    pass

            # Release the processing lock now that cache has been populated
            # (also released in the finally block on error paths)
            if _redis_lock_conn is not None and _redis_lock_key is not None:
                try:
                    _redis_lock_conn.delete(_redis_lock_key)
                    _redis_lock_conn = None  # prevent double-delete in finally
                except Exception as lock_err:
                    logger.warning(f"[{vid}] ⚠️ No se pudo liberar lock de cache: {lock_err}")

            self._log_dashboard(vid, analysis, phase_timings, total_time,
                                dur_str, file_size_mb, scan_res['stats']['total_samples'],
                                detected_events, motion_segments,
                                operational_events, summary, type_info)

            self._send_completion_notification(analysis, vid, success=True)
            self._invalidate_cache(analysis_id)

        except Exception as e:
            elapsed_err = time.time() - pipeline_start
            logger.error(f"[{vid}] ❌ PIPELINE ERROR tras {elapsed_err:.1f}s: {e}", exc_info=True)
            try:
                analysis = self.repo.obtener_analisis(analysis_id)
                if analysis:
                    analysis.actualizar_estado(EstadoOperationalAnalysis.ERROR, f'Error: {str(e)[:200]}')
                    analysis.error_message = str(e)
                    analysis.phase_timings = phase_timings
                    self.repo.guardar_analisis(analysis)
                    self._send_completion_notification(analysis, vid, success=False, error_msg=str(e))
            except Exception:
                pass
            raise
        finally:
            # Always release the processing lock, even on error
            if _redis_lock_conn is not None and _redis_lock_key is not None:
                try:
                    _redis_lock_conn.delete(_redis_lock_key)
                except Exception:
                    pass
            self._cleanup_temp()
            if local_video_path and local_video_path != video_path:
                try:
                    if os.path.exists(local_video_path):
                        os.remove(local_video_path)
                except Exception:
                    pass

    def _send_completion_notification(self, analysis: OperationalAnalysis, vid: str, success: bool = True, error_msg: str = ""):
        try:
            from infrastructure.services.notification_service import NotificationService
            notifier = NotificationService()
            type_info = OPERATIONAL_ANALYSIS_TYPES.get(analysis.analysis_type, {})
            type_name = type_info.get('name', analysis.analysis_type)

            if success:
                dur_str = f"{analysis.video_duration/3600:.1f}h" if analysis.video_duration > 3600 else f"{analysis.video_duration/60:.1f}min"
                subject = f"✅ Análisis Operativo Completado: {type_name}"
                body = (f"Análisis operativo completado exitosamente.\n\n"
                        f"Tipo: {type_name}\nVideo: {analysis.video_filename}\nDuración: {dur_str}\n"
                        f"Tiempo de procesamiento: {analysis.tiempo_procesamiento_segundos/60:.1f} min\n"
                        f"Eventos detectados: {len(analysis.eventos)}\n\nID: {analysis.id}\n")
            else:
                subject = f"❌ Error en Análisis Operativo: {type_name}"
                body = (f"El análisis operativo falló.\n\nTipo: {type_name}\nVideo: {analysis.video_filename}\n"
                        f"Error: {error_msg[:500]}\n\nID: {analysis.id}\n")

            html_body = body.replace('\n', '<br>')
            html_content = f"<div style='font-family:Arial,sans-serif;padding:20px;'><h2>{subject}</h2><p>{html_body}</p></div>"
            notifier._send_email(to_email=analysis.usuario, subject=subject, html_content=html_content)
        except Exception as e:
            logger.warning(f"[{vid}]    ⚠️ No se pudo enviar notificación: {e}")

    def _invalidate_cache(self, analysis_id: str):
        try:
            from infrastructure.services.redis_cache import get_cache_instance
            cache = get_cache_instance()
            if cache:
                cache.delete(f"op_analysis:{analysis_id}")
                cache.delete(f"op_events:{analysis_id}")
        except Exception:
            pass

    def _log_dashboard(self, vid, analysis, phase_timings, total_time, dur_str, file_size_mb, total_samples, detected_events, motion_segments, operational_events, summary, type_info):
        event_types = {}
        for ev in detected_events:
            event_types[ev.event_type] = event_types.get(ev.event_type, 0) + 1

        logger.info(f"[{vid}] ")
        logger.info(f"[{vid}] ╔══════════════════════════════════════════════════════╗")
        logger.info(f"[{vid}] ║   ANÁLISIS OPERATIVO COMPLETADO — DASHBOARD FINAL   ║")
        logger.info(f"[{vid}] ╠══════════════════════════════════════════════════════╣")
        logger.info(f"[{vid}] ║ Tipo: {type_info.get('icon', '')} {type_info.get('name', analysis.analysis_type)}")
        logger.info(f"[{vid}] ║ Video: {dur_str} | {file_size_mb:.1f} MB")
        logger.info(f"[{vid}] ║ Contexto: {_sanitize_context_for_log(analysis.custom_context)}")
        logger.info(f"[{vid}] ╠══════════════════════════════════════════════════════╣")
        logger.info(f"[{vid}] ║ ⏱️  TIEMPOS:")
        for fase, t in phase_timings.items():
            logger.info(f"[{vid}] ║   {fase}: {t:>8.1f}s")
        logger.info(f"[{vid}] ║   TOTAL: {total_time:>8.1f}s ({total_time/60:.1f}min)")
        logger.info(f"[{vid}] ╠══════════════════════════════════════════════════════╣")
        logger.info(f"[{vid}] ║ 📊 PIPELINE:")
        logger.info(f"[{vid}] ║   Muestras escaneadas: {total_samples:,}")
        logger.info(f"[{vid}] ║   Eventos scanner: {len(detected_events)} → Segmentos: {len(motion_segments)}")
        logger.info(f"[{vid}] ║   Eventos operativos: {len(operational_events)}")
        logger.info(f"[{vid}] ║   Tipos: {event_types}")
        if isinstance(summary, dict):
            entries = summary.get('total_unique_entries', 'N/A')
            exits = summary.get('total_unique_exits', 'N/A')
            compliance = summary.get('fotcheck_compliance_pct', 'N/A')
            logger.info(f"[{vid}] ╠══════════════════════════════════════════════════════╣")
            logger.info(f"[{vid}] ║ 📋 RESUMEN:")
            logger.info(f"[{vid}] ║   Entradas: {entries} | Salidas: {exits}")
            if compliance != 'N/A':
                logger.info(f"[{vid}] ║   Cumplimiento fotcheck: {compliance}%")
        logger.info(f"[{vid}] ╚══════════════════════════════════════════════════════╝")
