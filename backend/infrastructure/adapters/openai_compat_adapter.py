"""
openai_compat_adapter — Cliente OpenAI-compat para ApiLLM y vLLM 32B
Un solo SDK cubre ambos proveedores (base_url distinto).
"""
import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class OpenAICompatAdapter:
    """Adapter OpenAI-compat: chat/vision/embeddings/transcribe."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "not-needed",
        default_model: str = "",
        timeout: int = 120,
        default_headers: Optional[dict[str, str]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout
        self.default_headers = default_headers or {}
        # lazy import para no romper si openai no instalado (tests)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI  # type: ignore
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
                default_headers=self.default_headers or None,
            )
        return self._client

    def is_available(self) -> bool:
        try:
            import httpx
            url = f"{self.base_url}/models"
            headers = {"Authorization": f"Bearer {self.api_key}", **self.default_headers}
            r = httpx.get(url, headers=headers, timeout=5)
            return r.status_code < 500
        except Exception:
            # fallback: intenta chat con 1 token
            try:
                self.chat([{"role": "user", "content": "ping"}], model=self.default_model, max_tokens=1)
                return True
            except Exception as e:
                logger.debug("OpenAICompat not available %s: %s", self.base_url, e)
                return False

    # Alias compat con GeminiAdapter.disponible
    @property
    def disponible(self) -> bool:
        return self.is_available()

    def chat(self, messages: list[dict], model: Optional[str] = None, json_mode: bool = False, temperature: float = 0, max_tokens: int = 2048) -> str:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def vision(self, prompt: str, images_b64: Optional[list[str]] = None, video_path: Optional[str] = None, model: Optional[str] = None, json_mode: bool = True) -> dict:
        """Vision con imágenes base64. Si video_path se pasa, extrae 1 frame via opencv (caller debe proveer b64)."""
        content: list[dict] = [{"type": "text", "text": prompt}]
        if images_b64:
            for b64 in images_b64[:4]:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        # video_path no se envía como Part GCS; el caller debe haber extraído frames
        messages = [{"role": "user", "content": content}]
        text = self.chat(messages, model=model, json_mode=json_mode, temperature=0)
        # Parse JSON robusto
        try:
            # strip ```json
            t = text.strip()
            if "```" in t:
                import re
                m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
                if m:
                    t = m.group(1)
            return json.loads(t)
        except Exception:
            # fallback: intenta extraer primer {...}
            import re
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    return json.loads(m.group())
                except Exception:
                    pass
            return {"raw": text, "parse_error": True}

    def embed(self, texts: list[str], model: Optional[str] = None) -> list[list[float]]:
        client = self._get_client()
        resp = client.embeddings.create(model=model or self.default_model, input=texts)
        return [d.embedding for d in resp.data]

    # Compat shims para código legacy que espera GeminiAdapter
    def generar_titulo(self, nombre_archivo: str, etiquetas=None, duracion_segundos=None) -> str:
        prompt = f"Genera título corto (max 50 chars, español, sin comillas). Archivo: {nombre_archivo} Etiquetas: {etiquetas or []} Duración: {duracion_segundos}s"
        try:
            return self.chat([{"role": "user", "content": prompt}], temperature=0.7, max_tokens=60).strip().strip('"')[:60]
        except Exception:
            import re as _re
            stem = Path(nombre_archivo).stem
            return _re.sub(r"[_-\.]+", " ", stem).strip()[:50] or "Video sin título"

    def decidir_moderacion(self, analisis: dict, blacklist: Optional[dict] = None) -> dict:
        prompt = f"Eres moderador. Analiza JSON y decide. Retorna JSON {{aprobado:bool, razon:str, confianza:0-1}}. Análisis: {json.dumps(analisis, ensure_ascii=False)[:4000]} Blacklist: {json.dumps(blacklist or {}, ensure_ascii=False)[:1000]}"
        try:
            j = self.vision(prompt, json_mode=True)
            if "aprobado" in j:
                return {"aprobado": bool(j["aprobado"]), "razon": j.get("razon", ""), "confianza": float(j.get("confianza", 0.7)), "modelo": self.default_model}
        except Exception as e:
            logger.warning("decidir_moderacion fallback: %s", e)
        return {"aprobado": True, "razon": "Heurístico local: sin IA", "confianza": 0.5, "modelo": "fallback"}

    # Shims vision legacy
    def analyze_video_clip(self, clip_path: str = "", prompt: str = "", frames_base64=None) -> dict:
        frames = frames_base64 or []
        if clip_path and not frames:
            # extrae 1 frame si es ruta local
            try:
                from infrastructure.services.video_frame_extractor import VideoFrameExtractor
                fe = VideoFrameExtractor()
                b64 = fe.extract_frames_base64(clip_path, max_frames=1)
                frames = b64 or []
            except Exception:
                pass
        res = self.vision(prompt or "Describe el video", frames, json_mode=True)
        return {"success": not res.get("parse_error"), "analisis": res, "tipo_analisis": "vision", "tokens_usados": 0}

    def analyze_frames(self, prompt: str, frames_base64: list[str]) -> dict:
        return self.analyze_video_clip("", prompt, frames_base64)

    def analyze_video_clip_safety(self, storage_uri: str = "", descripcion: str = "", duracion: float = 0, contexto_workspace: str = "", metadata_workspace=None, frames_base64: Optional[list[str]] = None) -> dict:
        prompt = f"Eres moderador experto. Describe y modera. Descripcion: '{descripcion[:200]}' Duración: {duracion:.0f}s Contexto workspace: {contexto_workspace} Categoría: {(metadata_workspace or {}).get('categoria','')} Retorna JSON {{contenido_apropiado:bool, relevante_al_workspace:bool, recomendacion:'aprobar'|'rechazar', confianza:0-1, razon_recomendacion:str, nivel_riesgo:'BAJO'|'MEDIO'|'ALTO'}}"
        j = self.vision(prompt, images_b64=frames_base64, json_mode=True)
        analysis = {
            "contenido_apropiado": j.get("contenido_apropiado", j.get("aprobado", True)),
            "relevante_al_workspace": j.get("relevante_al_workspace", True),
            "recomendacion": j.get("recomendacion", "aprobar"),
            "confianza": float(j.get("confianza", 0.7)),
            "razon_recomendacion": j.get("razon_recomendacion", j.get("razon", "")),
            "nivel_riesgo": j.get("nivel_riesgo", "BAJO"),
            "raw": j,
        }
        return {"success": True, "analisis": analysis, "tipo_analisis": "vision", **analysis}

    def analyze_content_safety(self, frames_base64, descripcion, transcripcion="", duracion=0, contexto_workspace="", metadata_workspace=None) -> dict:
        return self.analyze_video_clip_safety(
            "", descripcion, duracion, contexto_workspace, metadata_workspace,
            frames_base64=frames_base64,
        )

    def analyze_text_with_thinking(self, prompt: str) -> str:
        """Compat shim GeminiAdapter: texto con razonamiento (max tokens alto, temp baja)."""
        try:
            return self.chat([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=8192)
        except Exception as e:
            logger.warning("analyze_text_with_thinking fallo: %s", e)
            return ""

    def analyze_multiple_clips_summary(self, all_events_analysis, video_metadata=None) -> dict:
        """Compat shim GeminiAdapter: correlación cruzada de eventos vía JSON mode.
        Retorna {'success': False} en fallo; el caller usa su fallback básico."""
        if not getattr(self, "disponible", False):
            return {'success': False}
        try:
            events_summary = [
                {
                    "evento": i + 1,
                    "timestamp": f"{ev.get('timestamp_inicio', 0):.0f}s - {ev.get('timestamp_fin', 0):.0f}s",
                    "descripcion": ev.get("descripcion", "")[:200],
                    "personas": ev.get("personas_count", 0),
                    "vehiculos": ev.get("vehiculos_count", 0),
                    "objetos": ev.get("objetos_detectados", [])[:10],
                    "nivel_riesgo": ev.get("nivel_riesgo", "bajo"),
                    "acciones": ev.get("acciones_detectadas", [])[:5],
                }
                for i, ev in enumerate((all_events_analysis or [])[:40])
            ]
            prompt = (
                "Eres analista de seguridad. Correlaciona los eventos de un video de vigilancia.\n"
                "Retorna ÚNICAMENTE JSON con claves: "
                "nivel_riesgo_global (BAJO/MEDIO/ALTO/CRITICO), resumen_ejecutivo (str), "
                "personas_total_estimado (int), vehiculos_total_estimado (int), "
                "patrones_detectados (list[str]), recomendaciones_seguridad (list[str]).\n"
                f"Metadatos video: {json.dumps(video_metadata or {}, ensure_ascii=False)[:500]}\n"
                f"EVENTOS:\n{json.dumps(events_summary, indent=2, ensure_ascii=False)}\n"
            )
            text = self.chat([{"role": "user", "content": prompt}], json_mode=True, temperature=0.1, max_tokens=4096)
            j = json.loads(text)
            if isinstance(j, dict) and j:
                return {"success": True, "analisis_cruzado": {
                    "nivel_riesgo_global": j.get("nivel_riesgo_global", "BAJO"),
                    "resumen_ejecutivo": j.get("resumen_ejecutivo", ""),
                    "personas_total_estimado": j.get("personas_total_estimado", 0),
                    "vehiculos_total_estimado": j.get("vehiculos_total_estimado", 0),
                    "patrones_detectados": j.get("patrones_detectados", []),
                    "recomendaciones_seguridad": j.get("recomendaciones_seguridad", []),
                }}
            return {'success': False}
        except Exception as e:
            logger.warning("analyze_multiple_clips_summary fallo: %s", e)
            return {'success': False}

    def validar_contexto(self, frames_base64: list[str], contexto_usuario: str) -> dict:
        prompt = (
            "Determina si las imágenes son relevantes al contexto indicado. "
            "Responde solo JSON con es_relevante (bool), razon (str) y confianza (0-1).\n"
            f"Contexto: {contexto_usuario}"
        )
        try:
            result = self.vision(prompt, frames_base64, json_mode=True)
            return {
                "es_relevante": bool(result.get("es_relevante", False)),
                "razon": result.get("razon", ""),
                "confianza": float(result.get("confianza", 0)),
            }
        except Exception as e:
            logger.warning("validar_contexto fallo: %s", e)
            return {"es_relevante": False, "razon": "IA no disponible", "confianza": 0}

    def analizar_escena_detallada(self, frames_base64: list[str], contexto_usuario: str) -> dict:
        prompt = (
            "Analiza detalladamente las imágenes de seguridad según el contexto indicado. "
            "Responde solo JSON con descripcion, nivel_riesgo, personas, objetos, acciones y alertas.\n"
            f"Contexto: {contexto_usuario}"
        )
        try:
            return {"success": True, "analisis": self.vision(prompt, frames_base64, json_mode=True)}
        except Exception as e:
            logger.warning("analizar_escena_detallada fallo: %s", e)
            return {"success": False, "error": str(e), "analisis": {}}
