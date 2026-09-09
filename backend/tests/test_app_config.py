import importlib

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
