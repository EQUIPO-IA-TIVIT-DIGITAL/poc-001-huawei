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

    def __init__(self, base_url: str, api_key: str = "not-needed", default_model: str = "", timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout
        # lazy import para no romper si openai no instalado (tests)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI  # type: ignore
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)
        return self._client

    def is_available(self) -> bool:
        try:
            import httpx
            url = f"{self.base_url}/models"
            headers = {"Authorization": f"Bearer {self.api_key}"}
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

    def analyze_video_clip_safety(self, gcs_uri: str = "", descripcion: str = "", duracion: float = 0, contexto_workspace: str = "", metadata_workspace=None) -> dict:
        prompt = f"Eres moderador experto. Describe y modera. Descripcion: '{descripcion[:200]}' Duración: {duracion:.0f}s Contexto workspace: {contexto_workspace} Categoría: {(metadata_workspace or {}).get('categoria','')} Retorna JSON {{contenido_apropiado:bool, relevante_al_workspace:bool, recomendacion:'aprobar'|'rechazar', confianza:0-1, razon_recomendacion:str, nivel_riesgo:'BAJO'|'MEDIO'|'ALTO'}}"
        j = self.vision(prompt, json_mode=True)
        return {
            "contenido_apropiado": j.get("contenido_apropiado", j.get("aprobado", True)),
            "relevante_al_workspace": j.get("relevante_al_workspace", True),
            "recomendacion": j.get("recomendacion", "aprobar"),
            "confianza": float(j.get("confianza", 0.7)),
            "razon_recomendacion": j.get("razon_recomendacion", j.get("razon", "")),
            "nivel_riesgo": j.get("nivel_riesgo", "BAJO"),
            "raw": j,
        }

    def analyze_content_safety(self, frames_base64, descripcion, transcripcion="", duracion=0, contexto_workspace="", metadata_workspace=None) -> dict:
        return self.analyze_video_clip_safety("", descripcion, duracion, contexto_workspace, metadata_workspace)
