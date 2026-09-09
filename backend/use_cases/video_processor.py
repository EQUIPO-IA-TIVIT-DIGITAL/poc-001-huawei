"""
Caso de Uso: Procesamiento de Videos con IA Optimizado v4.0 (Pipeline Pattern)
Pipeline: Compresión → Early Exit → Parallel (Visión IA + Speech condicional) → Decisor
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any, List, Protocol

from domain.entities import Video, EstadoVideo, ReglaNegocioException
from infrastructure.services.video_compressor import VideoCompressor
from infrastructure.services.video_cache import get_video_analysis_cache

from use_cases.socio_video.preparator import VideoPreparator
from use_cases.socio_video.verifier import VideoVerifier
from use_cases.socio_video.scanner import VideoQuickScanner
from use_cases.socio_video.analyzer import VideoDeepAnalyzer
from use_cases.socio_video.decider import VideoDecider

logger = logging.getLogger(__name__)


# ========== PROTOCOLOS (INTERFACES) ==========

class StorageProtocol(Protocol):
    def upload_video(self, file_path: str, video_id: str, content_type: str = None, metadata: dict = None) -> Optional[str]: ...
    def is_available(self) -> bool: ...
    def get_storage_uri(self, storage_path: str) -> str: ...
    def generate_signed_url(self, blob_name: str, expiration_minutes: int = 60) -> Optional[str]: ...


class DatabaseProtocol(Protocol):
    def save_video(self, video: Video) -> bool: ...
    def is_available(self) -> bool: ...


class GeminiVisionProtocol(Protocol):
    def analyze_content_safety(self, frames_base64: List[str], descripcion: str, transcripcion: str, duracion: float, contexto_workspace: str = "", metadata_workspace: dict = None) -> Dict: ...
    def is_available(self) -> bool: ...


class SpeechProtocol(Protocol):
    def transcribe_video(self, video_path: str, video_id: str) -> Dict: ...
    def is_available(self) -> bool: ...


class FrameExtractorProtocol(Protocol):
    def extract_frames(self, video_path: str, num_frames: int) -> Optional[List[str]]: ...
    def is_available(self) -> bool: ...


class ProcesarVideoUseCase:
    """Caso de uso orquestador para procesar videos con pipeline de IA optimizado v4.0"""

    TOTAL_STEPS = 5

    def __init__(
        self,
        api_key: str = None,
        storage_adapter: StorageProtocol = None,
        firestore_adapter: DatabaseProtocol = None,
        gemini_adapter: GeminiVisionProtocol = None,
        speech_adapter: SpeechProtocol = None,
        frame_extractor: FrameExtractorProtocol = None,
        video_intelligence_adapter=None,
    ):
        self.storage = storage_adapter
        self.firestore = firestore_adapter
        self.gemini = gemini_adapter
        self.speech = speech_adapter
        self.frame_extractor = frame_extractor
        
        self.compressor = VideoCompressor()
        self.cache = get_video_analysis_cache()
        self.blacklist_config = self._cargar_blacklist_config()
        self.adapters_available = self._check_adapters_available()

        # Initialize Pipeline components
        self.preparator = VideoPreparator(self.compressor, self.storage, self.adapters_available)
        self.verifier = VideoVerifier()
        self.scanner = VideoQuickScanner(self.gemini, self.frame_extractor)
        self.analyzer = VideoDeepAnalyzer(self.gemini, self.speech, self.frame_extractor, self.compressor)
        self.decider = VideoDecider(self.gemini, self.blacklist_config)

        if self.adapters_available:
            logger.info("✅ Procesador de Videos v4.0 OPTIMIZADO habilitado (Pipeline Pattern)")
        else:
            logger.warning("⚠️ Procesador de videos en modo local")

    def _check_adapters_available(self) -> bool:
        return self.storage is not None and self.storage.is_available()

    def _cargar_blacklist_config(self) -> Dict[str, Any]:
        try:
            blacklist_path = Path(__file__).parent.parent / "config" / "blacklist.json"
            if blacklist_path.exists():
                with open(blacklist_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ Error cargando blacklist: {e}")
        return {"palabras_prohibidas": [], "logos_competidores": [], "categorias_prohibidas": {}}

    def ejecutar(
        self,
        video: Video,
        blacklist_path: str = None,
        upload_to_storage: bool = True,
        progress_callback=None,
        check_cancel=None,
    ) -> Video:
        def report(step, msg, status="running", details=None):
            if check_cancel:
                check_cancel()
            if progress_callback:
                progress_callback(step, self.TOTAL_STEPS, msg, status, details)
            logger.info(f"[{step}/{self.TOTAL_STEPS}] {msg}")

        if video.estado not in [EstadoVideo.PENDIENTE, EstadoVideo.ERROR]:
            raise ReglaNegocioException(f"Video debe estar PENDIENTE o ERROR. Actual: {video.estado.value}")

        video.actualizar_estado(EstadoVideo.PROCESANDO)
        contexto_workspace, metadata_workspace = self._obtener_contexto_workspace(video)

        contexto_analisis = {
            "nombre_archivo": getattr(video, 'nombre_archivo', Path(video.ruta_archivo).name),
            "usuario": video.usuario,
            "descripcion_usuario": video.descripcion,
            "contexto_usuario": contexto_workspace,
            "metadata_workspace": metadata_workspace,
            "duracion_segundos": None,
            "gemini_vision": None,
            "speech_analysis": None,
            "contenido_explicito": None,
            "compresion": None,
        }

        archivo_analisis = video.ruta_archivo
        compressed_path = None

        try:
            video_hash = self.cache.compute_hash(video.ruta_archivo)
            video.agregar_metadatos("video_hash", video_hash)
            cached_result = self.cache.get_cached_analysis(video_hash)
            if cached_result:
                cached_resultado = cached_result.get("resultado_ia", "")
                cached_confianza = (cached_result.get("decision_gemini") or {}).get("confianza", 1.0)
                is_early_exit = cached_result.get("early_exit", False)
                is_error = cached_resultado.startswith("ERROR")
                is_low_confidence = not is_early_exit and cached_confianza < 0.70
                if not is_error and not is_low_confidence:
                    return self._aplicar_resultado_cacheado(video, cached_result, report)
                logger.warning(f"⚠️ Cache descartado (resultado={cached_resultado}, confianza={cached_confianza:.0%}), reprocesando...")

            # PASO 1
            report(1, "Preparando video (compresión + upload)...", "running")
            prep_res = self.preparator.process_preparation(video, archivo_analisis, contexto_analisis, upload_to_storage)
            if prep_res.get("error"):
                report(1, prep_res["msg"], "error")
                video.agregar_metadatos("resultado_ia", "ERROR_STORAGE")
                video.agregar_metadatos("razon_rechazo", prep_res["msg"])
                video.actualizar_estado(EstadoVideo.ERROR)
                self._guardar_en_db(video)
                return video
            
            compressed_path = prep_res.get("compressed_path")
            archivo_analisis = prep_res.get("archivo_analisis")
            report(1, "Video preparado", "success", {"storage_uri": prep_res.get("storage_uri")})

            # PASO 2
            report(2, "Verificando duración...", "running")
            verif_res = self.verifier.verify_duration(video, archivo_analisis, contexto_analisis)
            if verif_res.get("error"):
                report(2, verif_res["msg"], "error")
                video.agregar_metadatos("resultado_ia", "RECHAZADO_DURACION")
                video.agregar_metadatos("razon_rechazo", verif_res["msg"])
                video.actualizar_estado(EstadoVideo.ERROR)
                self._guardar_en_db(video)
                return video
            report(2, f"Duración: {verif_res['duracion_segundos']}s ✓", "success")

            # PASO 3
            report(3, "Escaneo rápido (detección de violaciones obvias)...", "running")
            scan_res = self.scanner.scan(archivo_analisis, video, verif_res["duracion_segundos"])
            if scan_res and scan_res.get("rechazar"):
                msg = scan_res.get("razon", "Contenido inapropiado detectado")
                report(3, f"⚡ Rechazo rápido: {msg}", "error")
                video.agregar_metadatos("resultado_ia", "RECHAZADO")
                video.agregar_metadatos("razon_rechazo", msg)
                video.agregar_metadatos("decision_automatica", True)
                video.agregar_metadatos("early_exit", True)
                video.actualizar_estado(EstadoVideo.RECHAZADO)
                self._guardar_en_db(video)
                self.cache.store_analysis(video_hash, {"resultado_ia": "RECHAZADO", "razon_rechazo": msg, "early_exit": True})
                return video
            report(3, "Escaneo rápido: Sin violaciones obvias", "success")

            # PASO 4
            report(4, "Análisis profundo (Visión IA + Audio en paralelo)...", "running")
            self.analyzer.analyze(archivo_analisis, video, verif_res["duracion_segundos"], contexto_analisis)
            report(4, "Análisis profundo completado", "success")

            # PASO 5
            report(5, "IA tomando decisión final...", "running")
            dec_res = self.decider.decide(video, contexto_analisis)
            
            resultado_ia = video.metadatos_ia.get("resultado_ia")
            if resultado_ia == "APROBADO":
                report(5, f"APROBADO: {dec_res.get('titulo')}", "success")
            elif resultado_ia == "RECHAZADO":
                report(5, f"RECHAZADO: {video.metadatos_ia.get('razon_rechazo')}", "error")
            else:
                report(5, f"Enviado a revisión manual", "warning")

            self._guardar_en_db(video)

            confianza_resultado = dec_res.get("confianza", 0)
            if resultado_ia not in ["ERROR_PROCESAMIENTO", "ERROR_STORAGE"] and confianza_resultado >= 0.70:
                self.cache.store_analysis(video_hash, {
                    "resultado_ia": resultado_ia,
                    "decision_gemini": dec_res.get("decision_final"),
                    "titulo": dec_res.get("titulo"),
                    "gemini_vision": contexto_analisis.get("gemini_vision"),
                    "speech_analysis": contexto_analisis.get("speech_analysis"),
                })

            self._actualizar_stats_workspace(video)

            return video

        except Exception as e:
            report(5, f"Error crítico: {str(e)}", "error")
            video.agregar_metadatos("resultado_ia", "ERROR_PROCESAMIENTO")
            video.agregar_metadatos("error", str(e))
            if video.estado not in [EstadoVideo.COMPLETADO, EstadoVideo.ERROR]:
                video.actualizar_estado(EstadoVideo.ERROR)
            self._guardar_en_db(video)
            self._actualizar_stats_workspace(video)
            raise

        finally:
            if compressed_path and os.path.exists(compressed_path):
                try:
                    os.unlink(compressed_path)
                except Exception:
                    pass

    def _obtener_contexto_workspace(self, video: Video):
        contexto_workspace = ""
        metadata_workspace = {}

        if hasattr(video, "workspace_id") and video.workspace_id:
            try:
                from infrastructure.repositories.workspace_repository import WorkspaceRepositoryFirestore
                workspace_repo = WorkspaceRepositoryFirestore()
                workspace = workspace_repo.obtener_por_id(video.workspace_id)
                if workspace:
                    partes_contexto = []
                    if workspace.contexto:
                        partes_contexto.append(workspace.contexto)
                    if hasattr(workspace, 'categoria') and workspace.categoria != 'general':
                        partes_contexto.append(f"Categoría: {workspace.categoria}")
                    if hasattr(workspace, 'tipo_contenido') and workspace.tipo_contenido:
                        partes_contexto.append(f"Tipo de contenido: {workspace.tipo_contenido}")
                    if hasattr(workspace, 'elementos_visuales') and workspace.elementos_visuales:
                        partes_contexto.append(f"Elementos visuales esperados: {workspace.elementos_visuales}")
                    if hasattr(workspace, 'nivel_tolerancia') and workspace.nivel_tolerancia:
                        nivel = workspace.nivel_tolerancia
                        if nivel == 'alto':
                            partes_contexto.append("⚠️ TOLERANCIA ALTA: contenidos intensos, deportes de contacto o acción")
                        elif nivel == 'bajo':
                            partes_contexto.append("🔒 TOLERANCIA BAJA: contenido educativo o familiar, análisis estricto")
                    contexto_workspace = ". ".join(partes_contexto)
                    metadata_workspace = {
                        'categoria': getattr(workspace, 'categoria', 'general'),
                        'nivel_tolerancia': getattr(workspace, 'nivel_tolerancia', 'medio'),
                        'tipo_contenido': getattr(workspace, 'tipo_contenido', '')
                    }
            except Exception as e:
                logger.warning(f"No se pudo obtener workspace: {e}")

        return contexto_workspace, metadata_workspace

    def _aplicar_resultado_cacheado(self, video: Video, cached: Dict, report) -> Video:
        report(1, "✅ Resultado en cache", "success")
        report(2, "Cache hit", "success")
        report(3, "Cache hit", "success")
        report(4, "Cache hit", "success")

        resultado = cached.get("resultado_ia", "APROBADO")
        video.agregar_metadatos("resultado_ia", resultado)
        video.agregar_metadatos("cached", True)
        video.agregar_metadatos("decision_gemini", cached.get("decision_gemini", {}))

        titulo = cached.get("titulo", "Video (cache)")
        video.agregar_metadatos("titulo", titulo)
        video.descripcion = titulo

        if cached.get("gemini_vision"):
            video.agregar_metadatos("gemini_vision", cached["gemini_vision"])
        if cached.get("speech_analysis"):
            video.agregar_metadatos("speech_analysis", cached["speech_analysis"])

        self.preparator._generar_thumbnail_safe(video)
        if self.adapters_available and self.storage and self.storage.is_available():
            storage_uri = self.storage.upload_video(
                file_path=video.ruta_archivo,
                video_id=video.id,
                content_type=f"video/{video.formato}",
                metadata={"cached": "true"},
            )
            if storage_uri:
                video.agregar_metadatos("storage_uri", storage_uri)
                blob_name = f"videos/{video.id}.{video.formato}"
                signed_url = self.storage.generate_signed_url(blob_name, expiration_minutes=1440)
                if signed_url:
                    video.agregar_metadatos("video_url", signed_url)

        if resultado == "APROBADO":
            video.actualizar_estado(EstadoVideo.APROBADO)
        elif resultado == "RECHAZADO":
            video.actualizar_estado(EstadoVideo.RECHAZADO)
            video.agregar_metadatos("razon_rechazo", cached.get("razon_rechazo", "Rechazado (cache)"))
        else:
            video.actualizar_estado(EstadoVideo.EN_REVISION)

        self._guardar_en_db(video)
        report(5, f"Resultado (cache): {resultado}", "success")
        return video

    def _guardar_en_db(self, video: Video) -> bool:
        if self.adapters_available and self.firestore and self.firestore.is_available():
            try:
                return self.firestore.save_video(video)
            except Exception as e:
                logger.warning(f"Error guardando en la base de datos: {e}")
        return False

    def _actualizar_stats_workspace(self, video: Video):
        if hasattr(video, 'workspace_id') and video.workspace_id:
            try:
                from infrastructure.services.workspace_stats_service import recalculate_workspace_stats
                recalculate_workspace_stats(video.workspace_id, touch_activity=True)
            except Exception:
                pass
