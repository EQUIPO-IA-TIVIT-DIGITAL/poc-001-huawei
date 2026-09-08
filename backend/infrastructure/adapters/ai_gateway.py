"""
ai_gateway — Router híbrido ApiLLM (remota) + vLLM 32B (local)
Ambos vía API OpenAI-compat. Offline-first: local intenta primero, fallback a api solo si local falla.
"""
import logging
import os
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
        self.api_adapter: Optional[OpenAICompatAdapter] = None
        if AppConfig.AI_API_BASE_URL:
            self.api_adapter = OpenAICompatAdapter(
                base_url=AppConfig.AI_API_BASE_URL,
                api_key=AppConfig.AI_API_KEY or "not-needed",
                default_model=AppConfig.AI_API_MODEL,
            )
        self.provider = provider
        logger.info("AI Gateway init provider=%s local=%s api=%s", provider, AppConfig.AI_LOCAL_BASE_URL, AppConfig.AI_API_BASE_URL or "disabled")

    def _pick(self, prefer_local: bool = True) -> tuple[OpenAICompatAdapter, Optional[OpenAICompatAdapter]]:
        """Retorna (primary, fallback)."""
        if self.provider == "local":
            return self.local_vision, None
        if self.provider == "api":
            return (self.api_adapter or self.local_vision), None
        if self.provider == "disabled":
            raise RuntimeError("AI_PROVIDER=disabled")
        # hybrid: local primero
        return self.local_vision, self.api_adapter

    def _call_with_fallback(self, fn_name: str, *args, **kwargs):
        primary, fallback = self._pick()
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
        if self.api_adapter and self.api_adapter.is_available():
            return True
        return False

    def generar_titulo(self, *a, **kw): return self._call_with_fallback("generar_titulo", *a, **kw)
    def decidir_moderacion(self, *a, **kw): return self._call_with_fallback("decidir_moderacion", *a, **kw)
    def analyze_video_clip(self, *a, **kw): return self._call_with_fallback("analyze_video_clip", *a, **kw)
    def analyze_frames(self, *a, **kw): return self._call_with_fallback("analyze_frames", *a, **kw)
    def analyze_video_clip_safety(self, *a, **kw): return self._call_with_fallback("analyze_video_clip_safety", *a, **kw)
    def analyze_content_safety(self, *a, **kw): return self._call_with_fallback("analyze_content_safety", *a, **kw)
    # genérico
    def chat(self, *a, **kw): return self._call_with_fallback("chat", *a, **kw)
    def vision(self, *a, **kw): return self._call_with_fallback("vision", *a, **kw)
    def embed(self, *a, **kw):
        # embeddings: intenta local text
        try:
            return self.local_text.embed(*a, **kw)
        except Exception:
            if self.api_adapter:
                return self.api_adapter.embed(*a, **kw)
            raise


def get_ai_gateway() -> AIGateway:
    global _gateway
    if _gateway is None:
        _gateway = AIGateway()
    return _gateway

# Alias para compat con código legacy que importa GeminiAdapter
GeminiAdapter = AIGateway
