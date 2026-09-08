import base64
import json
import logging
from typing import Optional, Dict, Any

from domain.entities import Video

logger = logging.getLogger(__name__)

class VideoQuickScanner:
    """Paso 3: Escaneo rápido (Early Exit con 3 frames)"""

    def __init__(self, gemini_adapter, frame_extractor):
        self.gemini = gemini_adapter
        self.frame_extractor = frame_extractor

    def _is_available(self) -> bool:
        return (
            self.gemini and self.gemini.is_available() and
            self.frame_extractor and self.frame_extractor.is_available()
        )

    def scan(self, video_path: str, video: Video, duracion: int) -> Optional[Dict[str, Any]]:
        """
        Analiza 3 frames rápidamente para detección de violaciones obvias.
        Si detecta violación con >95% confianza → rechazo inmediato.
        """
        if not self._is_available():
            return None

        try:
            logger.info(f"🔍 [PASO 3] Escaneo rápido con 3 frames para {video_path}")
            
            frames = self.frame_extractor.extract_frames(video_path, 3)
            if not frames or len(frames) < 2:
                return None

            quick_prompt = (
                "Analiza estas imágenes de un video de forma RÁPIDA.\n"
                "¿Hay alguna violación OBVIA de contenido? (pornografía, violencia gráfica extrema, armas, drogas).\n\n"
                "IMPORTANTE: Solo marca como violación si es MUY OBVIO (>95% seguridad).\n"
                "Si tienes duda, responde que NO hay violación.\n\n"
                "Responde SOLO en JSON:\n"
                '{"violacion_obvia": true/false, "razon": "breve explicación", "confianza": 0.0-1.0}'
            )

            if hasattr(self.gemini, 'client') and self.gemini.client is not None:
                from google.genai import types as _genai_types
                parts = [quick_prompt]
                for frame_b64 in frames:
                    parts.append(_genai_types.Part.from_bytes(
                        data=base64.b64decode(frame_b64),
                        mime_type='image/jpeg',
                    ))

                from google.genai import types as _types
                response = self.gemini._retry_with_backoff(
                    self.gemini.client.models.generate_content,
                    model=self.gemini._model_name,
                    contents=parts,
                    config=_types.GenerateContentConfig(
                        max_output_tokens=200,
                        response_mime_type="application/json",
                        # thinking_config removido
                    ),
                )

                content = response.text
                if not content:
                    return {"rechazar": False}
                content = content.strip()
                if content.startswith("```"):
                    import re
                    match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
                    if match:
                        content = match.group(1).strip()

                result = json.loads(content)

                if result.get("violacion_obvia") and result.get("confianza", 0) >= 0.95:
                    return {
                        "rechazar": True,
                        "razon": result.get("razon", "Violación de contenido detectada"),
                        "confianza": result.get("confianza", 0.95)
                    }

            return {
                "rechazar": False
            }

        except Exception as e:
            logger.warning(f"Error en escaneo rápido (continuando con análisis completo): {e}")

        return None
