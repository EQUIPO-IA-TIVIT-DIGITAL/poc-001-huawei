import importlib
import sys

from config import app_config
from config.app_config import AppConfig
from infrastructure.adapters.ai_gateway import AIGateway


def test_default_config_is_valid_for_development_fallbacks():
    valid, errors = AppConfig.validate_config()

    assert valid is True
    assert errors == []
    assert AppConfig.STORAGE_BACKEND in {"filesystem", "minio"}
    assert AppConfig.DB_BACKEND in {"sqlite", "postgres"}


def test_api_provider_requires_commercial_api_config(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "api")
    monkeypatch.delenv("AI_API_BASE_URL", raising=False)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    # Neutralizar dotenv a nivel de sys.modules: el reload de app_config re-ejecuta
    # "from dotenv import load_dotenv", lo que pisaría un patch sobre el atributo
    # del módulo. Sustituyendo el módulo dotenv entero, el rebind carga el stub.
    import types
    stub_dotenv = types.ModuleType("dotenv")
    stub_dotenv.load_dotenv = lambda *a, **k: False
    monkeypatch.setitem(sys.modules, "dotenv", stub_dotenv)

    reloaded = importlib.reload(app_config)
    valid, errors = reloaded.AppConfig.validate_config()

    assert valid is False
    assert "AI_API_BASE_URL requerido con AI_PROVIDER=api" in errors
    assert "AI_API_KEY requerido con AI_PROVIDER=api" in errors


def test_openrouter_headers_are_configured(monkeypatch):
    monkeypatch.setenv("AI_API_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://example.com")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "Example App")

    reloaded = importlib.reload(app_config)
    original_config = AIGateway._api_headers.__globals__["AppConfig"]
    AIGateway._api_headers.__globals__["AppConfig"] = reloaded.AppConfig
    try:
        headers = AIGateway._api_headers()
    finally:
        AIGateway._api_headers.__globals__["AppConfig"] = original_config

    assert headers == {
        "HTTP-Referer": "https://example.com",
        "X-Title": "Example App",
    }


def test_rate_limiter_storage_uri_is_resolved_string():
    from infrastructure.rate_limiter import limiter

    assert isinstance(limiter._storage_uri, str)
