"""
ai_gateway — Router híbrido ApiLLM (remota) + vLLM 32B (local)
Ambos vía API OpenAI-compat. Offline-first: local intenta primero, fallback a api solo si local falla.
"""
import logging
from typing import Optional

from config.app_config import AppConfig

from .openai_compat_adapter import OpenAICompatAdapter

logger = logging.getLogger(__name__)

# Singleton cache
_gateway: Optional["AIGateway"] = None


class AIGateway:
    """Gateway híbrido. Expone misma interfaz que GeminiAdapter para compat."""

    def __init__(self):
        provider = AppConfig.AI_PROVIDER
        api_headers = self._api_headers()
        # Local (obligatorio offline)
        self.local_vision = OpenAICompatAdapter(
            base_url=AppConfig.AI_LOCAL_BASE_URL,
            api_key="not-needed",
            default_model=AppConfig.AI_LOCAL_MODEL,
        )
        self.local_text = OpenAICompatAdapter(
            base_url=AppConfig.AI_LOCAL_TEXT_BASE_URL,
            api_key="not-needed",
            default_model=AppConfig.AI_LOCAL_TEXT_MODEL,
        )
        self.whisper_base = AppConfig.WHISPER_BASE_URL
        # Remota (opcional)
        self.api_vision: Optional[OpenAICompatAdapter] = None
        self.api_text: Optional[OpenAICompatAdapter] = None
        self.api_embedding: Optional[OpenAICompatAdapter] = None
        if AppConfig.AI_API_BASE_URL and AppConfig.AI_API_KEY:
            self.api_vision = OpenAICompatAdapter(
                base_url=AppConfig.AI_API_BASE_URL,
                api_key=AppConfig.AI_API_KEY,
                default_model=AppConfig.AI_API_VISION_MODEL,
                default_headers=api_headers,
            )
            self.api_text = OpenAICompatAdapter(
                base_url=AppConfig.AI_API_BASE_URL,
                api_key=AppConfig.AI_API_KEY,
                default_model=AppConfig.AI_API_TEXT_MODEL,
                default_headers=api_headers,
            )
            if AppConfig.AI_API_EMBEDDING_MODEL:
                self.api_embedding = OpenAICompatAdapter(
                    base_url=AppConfig.AI_API_BASE_URL,
                    api_key=AppConfig.AI_API_KEY,
                    default_model=AppConfig.AI_API_EMBEDDING_MODEL,
                    default_headers=api_headers,
                )
        self.provider = provider
        logger.info("AI Gateway init provider=%s local=%s api=%s", provider, AppConfig.AI_LOCAL_BASE_URL, AppConfig.AI_API_BASE_URL or "disabled")

    @staticmethod
    def _api_headers() -> dict[str, str]:
        if AppConfig.AI_API_PROVIDER != "openrouter":
            return {}
        return {
            "HTTP-Referer": AppConfig.OPENROUTER_SITE_URL,
            "X-Title": AppConfig.OPENROUTER_APP_NAME,
        }

    def _api_for_kind(self, kind: str) -> Optional[OpenAICompatAdapter]:
        if kind == "text":
            return self.api_text
        if kind == "embedding":
            return self.api_embedding
        return self.api_vision

    def _local_for_kind(self, kind: str) -> OpenAICompatAdapter:
        if kind in ("text", "embedding"):
            return self.local_text
        return self.local_vision

    def _pick(self, kind: str = "vision") -> tuple[OpenAICompatAdapter, Optional[OpenAICompatAdapter]]:
        """Retorna (primary, fallback)."""
        local = self._local_for_kind(kind)
        api = self._api_for_kind(kind)
        if self.provider == "local":
            return local, None
        if self.provider == "api":
            if api is None:
                raise RuntimeError("AI_PROVIDER=api requiere AI_API_BASE_URL y AI_API_KEY")
            return api, None
        if self.provider == "disabled":
            raise RuntimeError("AI_PROVIDER=disabled")
        # hybrid: local primero
        return local, api

    def _call_with_fallback(self, fn_name: str, *args, kind: str = "vision", **kwargs):
        primary, fallback = self._pick(kind)
        try:
            fn = getattr(primary, fn_name)
            return fn(*args, **kwargs)
        except Exception as e:
            logger.warning("AI primary %s fallo %s: %s", primary.base_url, fn_name, e)
            if fallback:
                try:
                    fn2 = getattr(fallback, fn_name)
                    logger.info("AI fallback a %s", fallback.base_url)
                    return fn2(*args, **kwargs)
                except Exception as e2:
                    logger.error("AI fallback también falló: %s", e2)
                    raise
            raise

    # ---- Compat Gemini / AIService ----
    @property
    def disponible(self) -> bool:
        return self.is_available()

    def is_available(self) -> bool:
        if self.provider == "disabled":
            return False
        # hybrid: basta uno disponible (local primero)
        if self.local_vision.is_available():
            return True
        if self.api_vision and self.api_vision.is_available():
            return True
        return False

    def generar_titulo(self, *a, **kw): return self._call_with_fallback("generar_titulo", *a, **kw)
    def decidir_moderacion(self, *a, **kw): return self._call_with_fallback("decidir_moderacion", *a, **kw)
    def analyze_video_clip(self, *a, **kw): return self._call_with_fallback("analyze_video_clip", *a, **kw)
    def analyze_frames(self, *a, **kw): return self._call_with_fallback("analyze_frames", *a, **kw)
    def analyze_text_with_thinking(self, *a, **kw): return self._call_with_fallback("analyze_text_with_thinking", *a, **kw)
    def analyze_multiple_clips_summary(self, *a, **kw): return self._call_with_fallback("analyze_multiple_clips_summary", *a, **kw)
    def validar_contexto(self, *a, **kw): return self._call_with_fallback("validar_contexto", *a, **kw)
    def analizar_escena_detallada(self, *a, **kw): return self._call_with_fallback("analizar_escena_detallada", *a, **kw)
    def analyze_video_clip_safety(self, *a, **kw): return self._call_with_fallback("analyze_video_clip_safety", *a, **kw)
    def analyze_content_safety(self, *a, **kw): return self._call_with_fallback("analyze_content_safety", *a, **kw)
    # genérico
    def chat(self, *a, **kw): return self._call_with_fallback("chat", *a, kind="text", **kw)
    def vision(self, *a, **kw): return self._call_with_fallback("vision", *a, kind="vision", **kw)
    def embed(self, *a, **kw):
        # embeddings: intenta local text
        try:
            return self.local_text.embed(*a, **kw)
        except Exception:
            if self.api_embedding:
                return self.api_embedding.embed(*a, **kw)
            raise

    def get_model_name(self, kind: str = "vision") -> str:
        primary, _fallback = self._pick(kind)
        return primary.default_model


def get_ai_gateway() -> AIGateway:
    global _gateway
    if _gateway is None:
        _gateway = AIGateway()
    return _gateway

# Alias para compat con código legacy que importa GeminiAdapter
GeminiAdapter = AIGateway
