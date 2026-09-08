"""
Rate Limiter compartido - AccessFan
Configuración centralizada de rate limiting para protección contra ataques
"""

import os
from flask import request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def get_rate_limit_key():
    """
    Función personalizada para obtener la clave de rate limiting.
    Retorna una clave segura y no vacía por petición.
    """
    # Exentar peticiones OPTIONS (preflight CORS) en request_filter.
    if request.method == "OPTIONS":
        return "preflight"

    # Obtener dirección remota de forma segura
    try:
        # Si hay usuario autenticado, priorizar clave por identidad de sesión
        user_id = session.get("usuario_id") if session else None
        if user_id:
            return f"user:{user_id}"

        remote_addr = get_remote_address()
        # Fallback directo a remote_addr — NO leer X-Forwarded-For manualmente:
        # ProxyFix(x_for=1) ya procesa ese header de forma segura.
        # Leerlo aquí directamente permitiría IP spoofing si ProxyFix no opera.
        if not remote_addr or remote_addr.strip() == "":
            remote_addr = request.remote_addr or "127.0.0.1"

        return remote_addr
    except Exception:
        # Fallback en caso de error
        return "127.0.0.1"




# Determinar storage backend según entorno
# En producción usar Redis para consistencia entre workers
_REDIS_URL_CACHE: str | None = None

def get_storage_uri():
    """Obtiene la URI de storage para rate limiting — lazy para no congelar env vacío al importar."""
    import os
    redis_url = os.environ.get('REDIS_URL', '')
    if redis_url:
        return redis_url
    if os.getenv("FLASK_ENV") == "production" or os.getenv("APP_ENV") == "local":
        import logging
        logging.getLogger(__name__).warning("REDIS_URL vacío — rate limiting en memory:// (no seguro en multi-worker). Define REDIS_URL.")
    return "memory://"


def _get_limiter_storage_uri():
    global _REDIS_URL_CACHE
    if _REDIS_URL_CACHE is None:
        _REDIS_URL_CACHE = get_storage_uri()
        # si env cambió después de importar, re-evaluar
        env_now = os.environ.get('REDIS_URL', '')
        if env_now and env_now != _REDIS_URL_CACHE:
            _REDIS_URL_CACHE = env_now
    return _REDIS_URL_CACHE


# Limiter global que será inicializado en main.py — storage_uri lazy
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=[
        os.environ.get("RATE_LIMIT_DEFAULT_DAY", "10000 per day"),
        os.environ.get("RATE_LIMIT_DEFAULT_HOUR", "1000 per hour"),
        os.environ.get("RATE_LIMIT_DEFAULT_MINUTE", "100 per minute"),
    ],
    storage_uri=_get_limiter_storage_uri,
    strategy="fixed-window",
)


@limiter.request_filter
def _skip_rate_limit() -> bool:
    """Evita rate limiting para preflight CORS."""
    return request.method == "OPTIONS"

# Límites específicos para endpoints sensibles
LOGIN_LIMIT = os.environ.get("LOGIN_LIMIT", "10 per minute")
REGISTRO_LIMIT = os.environ.get("REGISTRO_LIMIT", "20 per hour")
UPLOAD_LIMIT = os.environ.get("UPLOAD_LIMIT", "20 per hour")
API_LIMIT = os.environ.get("API_LIMIT", "60 per minute")
ADMIN_API_LIMIT = os.environ.get("ADMIN_API_LIMIT", "100 per minute")
ADMIN_ACTION_LIMIT = os.environ.get("ADMIN_ACTION_LIMIT", "30 per minute")

# Límite específico para endpoints que llaman a Gemini (chat IA)
# Más restrictivo que API_LIMIT porque cada request genera tokens Gemini
# 15/min por IP = suficiente para uso legítimo, protege contra abuso de cuota
AI_CHAT_LIMIT = os.environ.get("AI_CHAT_LIMIT", "15 per minute")

# Límites para polling (endpoint de status)
# AUMENTADO para soportar múltiples usuarios concurrentes
# 3000/min permite ~50 req/s, suficiente para 20-30 usuarios activos simultáneos
POLLING_LIMIT = os.environ.get("POLLING_LIMIT", "3000 per minute")
STATUS_LIMIT = os.environ.get("STATUS_LIMIT", "10000 per hour")
VIDEO_DETAILS_LIMIT = os.environ.get("VIDEO_DETAILS_LIMIT", "120 per minute")
