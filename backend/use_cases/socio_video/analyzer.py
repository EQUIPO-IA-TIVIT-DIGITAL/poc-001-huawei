import logging
from typing import Dict, Any

from domain.entities import Video

logger = logging.getLogger(__name__)

class VideoDeepAnalyzer:
    """Paso 4: Análisis profundo — Gemini procesa el video completo (visual + audio)"""

    def __init__(self, gemini_adapter, speech_adapter, frame_extractor, compressor):
        self.gemini = gemini_adapter
        self.speech = speech_adapter        # mantenido por compatibilidad, no se usa
        self.frame_extractor = frame_extractor
        self.compressor = compressor

    def _analizar_video_completo(
        self, gcs_uri: str, video: Video, duracion: int,
        contexto_workspace: str = "", metadata_workspace: dict = None
    ) -> Dict[str, Any]:
        """Análisis con video completo desde GCS — Gemini procesa visual + audio nativamente."""
        result = self.gemini.analyze_video_clip_safety(
            gcs_uri=gcs_uri,
            descripcion=video.descripcion or "",
            duracion=duracion,
            contexto_workspace=contexto_workspace,
            metadata_workspace=metadata_workspace,
        )
        if result and result.get('success'):
            analisis = result.get('analisis', {})
            logger.info(
                f"🎬 Gemini Video resultado: apropiado={analisis.get('contenido_apropiado')}, "
                f"confianza={analisis.get('confianza')}%, audio_analizado={analisis.get('audio_analizado', False)}"
            )
        return result or {"success": False}

    def _analizar_con_frames(
        self, video_path: str, video: Video, duracion: int,
        contexto_workspace: str = "", metadata_workspace: dict = None
    ) -> Dict[str, Any]:
        """Fallback: análisis con 5 frames cuando no hay GCS URI."""
        try:
            frames = self.frame_extractor.extract_frames(video_path, 5)
            if not frames:
                return {"success": False, "error": "No frames extraídos"}

            logger.info(f"🎥 Fallback frames: analizando {len(frames)} frames con Gemini Vision")
            return self.gemini.analyze_content_safety(
                frames_base64=frames,
                descripcion=video.descripcion or "",
                duracion=duracion,
                contexto_workspace=contexto_workspace,
                metadata_workspace=metadata_workspace,
            )
        except Exception as e:
            logger.error(f"Error en análisis por frames: {e}")
            return {"success": False, "error": str(e)}

    def analyze(self, video_path: str, video: Video, duracion: int, contexto_analisis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Análisis profundo: usa el video completo en GCS (visual + audio nativamente via Gemini).
        Fallback a frames si el GCS URI no está disponible.
        """
        logger.info(f"🔬 [PASO 4] Análisis profundo para {video.id}")

        contexto_workspace = contexto_analisis.get("contexto_usuario", "")
        metadata_workspace = contexto_analisis.get("metadata_workspace", {})

        gcs_uri = video.metadatos_ia.get("gcs_uri") if hasattr(video, 'metadatos_ia') else None
        gemini_result = None

        if gcs_uri and self.gemini and self.gemini.is_available():
            logger.info(f"🎬 Usando video completo GCS para análisis (audio + visual)")
            gemini_result = self._analizar_video_completo(
                gcs_uri, video, duracion, contexto_workspace, metadata_workspace
            )

        # Fallback a frames si el video completo no está disponible o falló
        if (not gemini_result or not gemini_result.get("success")):
            if self.frame_extractor and self.frame_extractor.is_available():
                logger.info("🔄 Fallback: analizando con frames estáticos")
                gemini_result = self._analizar_con_frames(
                    video_path, video, duracion, contexto_workspace, metadata_workspace
                )

        # Guardar resultado en contexto
        if gemini_result and gemini_result.get("success"):
            gemini_analysis = gemini_result.get("analisis", {})
            contexto_analisis["gemini_vision"] = gemini_analysis
            video.agregar_metadatos("gemini_vision", gemini_analysis)
            tipo = gemini_result.get("tipo_analisis", "frames")
            logger.info(f"✅ [PASO 4] Completado via {tipo}")
        else:
            logger.warning("⚠️ [PASO 4] Análisis de contenido no disponible")

        return {"vision": gemini_result, "context_updated": True}

