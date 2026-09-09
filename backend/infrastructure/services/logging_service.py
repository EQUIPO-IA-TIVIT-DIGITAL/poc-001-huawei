"""
Servicio de Logging Centralizado - TIVIT Video
Consola con colores en desarrollo, JSON en producción.
Reemplaza todos los print() del proyecto.
"""
import logging
import sys
import os
import json
import builtins
import contextvars
from datetime import datetime
from typing import Optional
from logging.handlers import RotatingFileHandler


_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
_original_print = builtins.print
_print_redirect_installed = False


def set_request_id(request_id: str) -> None:
    """Set request ID for current execution context."""
    _request_id_ctx.set(request_id or "-")


def get_request_id() -> str:
    """Get request ID for current execution context."""
    return _request_id_ctx.get()


def clear_request_context() -> None:
    """Clear request context after request/job completion."""
    _request_id_ctx.set("-")


class RequestContextFilter(logging.Filter):
    """Inject request_id into all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter for production logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class ColoredFormatter(logging.Formatter):
    """Formatter con colores ANSI para consola en desarrollo"""

    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        original_levelname = record.levelname

        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            color = self.COLORS.get(record.levelname, '')
            record.levelname = f"{color}{record.levelname}{self.RESET}"

        result = super().format(record)
        record.levelname = original_levelname
        return result


def _install_print_redirect() -> None:
    """Redirect print() to logger for stdout/stderr consistency."""
    global _print_redirect_installed
    if _print_redirect_installed:
        return

    def _print_proxy(*args, **kwargs):
        file_obj = kwargs.get("file", sys.stdout)
        if file_obj not in (sys.stdout, sys.stderr):
            return _original_print(*args, **kwargs)

        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        message = sep.join(str(a) for a in args)
        if end and end != "\n":
            message = f"{message}{end}"
        message = message.rstrip("\n")

        logger = logging.getLogger("stdout")
        logger.info(message)

        if kwargs.get("flush"):
            for handler in logging.getLogger().handlers:
                try:
                    handler.flush()
                except Exception:
                    pass

    builtins.print = _print_proxy
    _print_redirect_installed = True


def setup_logging(app_name: str = "tivit-video") -> logging.Logger:
    """
    Configura logging centralizado.
    
    - Producción: JSON a archivo + consola
    - Desarrollo: Consola con colores + archivo local
    
    Args:
        app_name: Nombre de la aplicación para identificar logs
        
    Returns:
        Logger raíz configurado
    """
    env = os.getenv('FLASK_ENV', 'development')
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_file = os.getenv('LOG_FILE', '')
    max_bytes = int(os.getenv('LOG_MAX_BYTES', str(10 * 1024 * 1024)))
    backup_count = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    redirect_prints = os.getenv('LOG_REDIRECT_PRINTS', 'true').lower() == 'true'
    
    # Crear logger raíz
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Limpiar handlers existentes
    logger.handlers = []
    
    # Formato para archivo
    file_format = '%(asctime)s | %(levelname)-8s | req=%(request_id)s | %(name)s | %(message)s'
    console_format = '%(asctime)s | %(levelname)-8s | req=%(request_id)s | %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    context_filter = RequestContextFilter()
    
    # === Handler de Consola (siempre) ===
    console_handler = logging.StreamHandler(sys.stdout)
    if env == 'production':
        console_handler.setFormatter(JsonFormatter())
    else:
        console_handler.setFormatter(ColoredFormatter(console_format, date_format))
    console_handler.setLevel(logging.DEBUG)
    console_handler.addFilter(context_filter)
    logger.addHandler(console_handler)
    
    # === Handler de Archivo (si está configurado) ===
    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8',
            )
            if env == 'production':
                file_handler.setFormatter(JsonFormatter())
            else:
                file_handler.setFormatter(logging.Formatter(file_format, date_format))
            file_handler.setLevel(logging.DEBUG)
            file_handler.addFilter(context_filter)
            logger.addHandler(file_handler)
            
        except Exception as e:
            logger.warning(f"No se pudo crear archivo de log: {e}")
    
    # Reducir ruido de librerias externas
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.INFO)

    # Log inicial
    logger.info(
        "%s startup | env=%s log_level=%s",
        app_name, env, log_level,
    )

    if redirect_prints:
        _install_print_redirect()
        logger.debug("print() redirect: enabled")
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger con nombre específico.
    
    Args:
        name: Nombre del módulo/componente
        
    Returns:
        Logger configurado
        
    Uso:
        logger = get_logger(__name__)
        logger.info("Mensaje")
    """
    return logging.getLogger(name)


# ============================================
# Funciones de conveniencia para migrar print()
# ============================================

_default_logger: Optional[logging.Logger] = None

def _get_default_logger() -> logging.Logger:
    """Obtiene o crea el logger por defecto"""
    global _default_logger
    if _default_logger is None:
        _default_logger = get_logger('tivit')
    return _default_logger


def log_info(message: str, *args):
    """Reemplazo para print() - nivel INFO"""
    _get_default_logger().info(message, *args)


def log_warning(message: str, *args):
    """Reemplazo para print() - nivel WARNING"""
    _get_default_logger().warning(message, *args)


def log_error(message: str, *args):
    """Reemplazo para print() - nivel ERROR"""
    _get_default_logger().error(message, *args)


def log_debug(message: str, *args):
    """Reemplazo para print() - nivel DEBUG"""
    _get_default_logger().debug(message, *args)
