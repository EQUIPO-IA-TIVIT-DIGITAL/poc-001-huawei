"""
TIVIT Video - Punto de Entrada Principal
Microservicios de Carga y Administración de Videos con Clean Architecture + Stack Local

Este archivo configura y ejecuta la aplicación Flask completa con:
- Microservicio de Carga (app_socio): Formulario de subida de videos
- Microservicio de Admin (app_admin): Panel de administración
- Stack 100% local (PostgreSQL, MinIO, vLLM 32B, Whisper, Redis + RQ)
- Repositorio SQLAlchemy (Postgres/SQLite)
"""

import os
import hmac
import json
import time
import uuid
from pathlib import Path
from datetime import timedelta
from urllib.parse import urlparse
from flask import Flask, redirect, url_for, jsonify, session, request, g
from flask_cors import CORS
from flask_compress import Compress
from werkzeug.middleware.proxy_fix import ProxyFix

# Logging centralizado (PRIMERO)
from infrastructure.services.logging_service import (
    setup_logging,
    get_logger,
    set_request_id,
    clear_request_context,
)

setup_logging("tivit-video")
logger = get_logger(__name__)


# Rate limiter compartido
from infrastructure.rate_limiter import limiter

# Módulo de inyección de dependencias
from infrastructure.dependencies import init_dependencies

# Importar Blueprints de los microservicios
from infrastructure.web.blueprints.app_socio import socio_bp
from infrastructure.web.blueprints.app_auth import auth_bp
from infrastructure.web.blueprints.api_v1 import api_v1_bp
from infrastructure.web.blueprints.app_workspaces import workspace_bp
from infrastructure.web.blueprints.app_workspace_chat import workspace_chat_bp
from infrastructure.web.blueprints.app_upload import upload_bp
from infrastructure.web.blueprints.app_security import (
    app_security,
)  # NUEVO: Análisis de seguridad
from infrastructure.web.blueprints.app_operational import app_operational  # Análisis operativo
from infrastructure.web.blueprints.app_audio import app_audio  # Análisis de audio

# Inicializar compresión gzip
compress = Compress()


def create_app():
    """
    Factory para crear y configurar la aplicación Flask

    Configura:
    - Blueprints de los microservicios
    - Repositorio singleton compartido
    - Directorios y rutas de configuración

    Returns:
        Flask: Aplicación Flask configurada
    """
    base_dir = Path(__file__).parent

    ui_root = base_dir / "infrastructure" / "web" / "ui"
    if not ui_root.exists():
        # Backward-compatible fallback in case legacy layout is present.
        ui_root = base_dir / "infrastructure" / "ui"

    app = Flask(
        __name__,
        template_folder=str(ui_root / "templates"),
        static_folder=str(ui_root / "static"),
    )

    # ===== CONFIGURACIÓN CORS =====
    # En producción, usar solo el origin permitido desde env
    # En desarrollo, permitir varios origins para testing
    is_production = os.environ.get("FLASK_ENV") == "production"

    if is_production:
        # En producción: solo el origin configurado
        raw = os.environ.get("CORS_ORIGIN", "http://localhost:5173")
        allowed_origins = [o.strip() for o in raw.split(",") if o.strip()]
    else:
        # En desarrollo: Lista explícita de orígenes permitidos
        allowed_origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    # Configurar CORS con manejo explícito de preflight
    cors = CORS(
        app,
        resources={r"/*": {"origins": allowed_origins}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With", "Cookie"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        expose_headers=["Content-Type", "Set-Cookie"],
        send_wildcard=False,
        max_age=3600,  # Cache preflight requests por 1 hora
    )

    # Handler adicional para asegurar que OPTIONS siempre funcione
    @app.after_request
    def after_request(response):
        origin = request.headers.get('Origin')
        if origin in allowed_origins:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With, Cookie'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        
        # Security Headers (OWASP Best Practices)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # HSTS (only in production with HTTPS)
        if is_production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        # Content Security Policy
        # - script-src: sin 'unsafe-inline'; blob: requerido por FFmpeg.wasm (worker core)
        # - connect-src: unpkg.com para descargar el core de FFmpeg (toBlobURL)
        # - Google Fonts para tipografías (style + font)
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' blob:",
            "worker-src 'self' blob:",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "img-src 'self' data: https: blob:",
            "font-src 'self' data: https://fonts.gstatic.com",
            "connect-src 'self' https://unpkg.com",
            "media-src 'self' blob:",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
            "upgrade-insecure-requests" if is_production else ""
        ]
        response.headers['Content-Security-Policy'] = '; '.join(filter(None, csp_directives))
        
        return response

    @app.before_request
    def setup_request_context():
        """Attach a request ID and start timer for every request."""
        request_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Correlation-ID")
            or uuid.uuid4().hex[:12]
        )
        g.request_id = request_id
        g.request_started_at = time.perf_counter()
        set_request_id(request_id)

    @app.after_request
    def access_log_and_sanitize_errors(response):
        """Log access data and avoid exception leakage in JSON responses."""
        request_id = getattr(g, "request_id", "-")
        response.headers["X-Request-ID"] = request_id

        if response.content_type and "application/json" in response.content_type:
            payload = response.get_json(silent=True)
            if isinstance(payload, dict) and response.status_code >= 500:
                payload["error"] = "Error interno del servidor"
                payload.pop("debug", None)
                payload.pop("stack_trace", None)  # Asegurar de remover trazas
                response.set_data(json.dumps(payload, ensure_ascii=False))
                response.headers["Content-Length"] = str(len(response.get_data()))

        elapsed_ms = 0.0
        started_at = getattr(g, "request_started_at", None)
        if started_at is not None:
            elapsed_ms = (time.perf_counter() - started_at) * 1000

        logger.info(
            "HTTP %s %s -> %s (%.1fms)",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )
        clear_request_context()
        return response

    # ===== CONFIGURACIÓN =====
    # Configuración de seguridad y sesiones
    secret_key = os.environ.get("SECRET_KEY")
    if is_production:
        # Fail-fast en producción: clave obligatoria, no conocida y >= 64 caracteres.
        if not secret_key:
            raise ValueError(
                "SECRET_KEY es OBLIGATORIO en producción. Configure la variable de entorno."
            )
        if secret_key == "dev-only-insecure-key-not-for-production":
            raise ValueError(
                "SECRET_KEY de desarrollo detectado en producción. Genere una clave segura."
            )
        if len(secret_key) < 64:
            raise ValueError(
                "SECRET_KEY debe tener al menos 64 caracteres en producción."
            )
    elif not secret_key:
        secret_key = "dev-only-insecure-key-not-for-production"
        logger.warning("Usando SECRET_KEY de desarrollo. NO usar en producción.")
    app.config["SECRET_KEY"] = secret_key

    # ===== COMPRESIÓN GZIP =====
    # Comprimir respuestas para reducir ancho de banda
    app.config["COMPRESS_MIMETYPES"] = [
        "text/html",
        "text/css",
        "text/xml",
        "application/json",
        "application/javascript",
        "text/javascript",
    ]
    app.config["COMPRESS_LEVEL"] = 6
    app.config["COMPRESS_MIN_SIZE"] = 500
    compress.init_app(app)
    logger.info("Compresión GZIP: HABILITADA")

    # HTTPS deployments retain secure cross-site cookies; HTTP development stays usable.
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    https_deployment = is_production or os.getenv("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes", "on")
    app.config["SESSION_COOKIE_SAMESITE"] = "None" if https_deployment else "Lax"
    app.config["SESSION_COOKIE_SECURE"] = https_deployment
    app.config["SESSION_COOKIE_DOMAIN"] = None
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

    # ===== PROTECCIÓN CSRF =====
    # Verificar header X-Requested-With en peticiones que modifican estado
    # Los navegadores no permiten enviar este header en requests cross-origin sin CORS
    @app.before_request
    def csrf_protect():
        """
        Protección CSRF usando header personalizado.
        Para peticiones POST/PUT/DELETE que modifican datos, verificamos que:
        1. Sea una petición JSON con el header correcto, O
        2. Sea un formulario del mismo origen (SameSite cookie ya protege esto)
        """
        from flask import request

        # Solo verificar métodos que modifican estado
        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            return None

        # Excluir rutas públicas que no requieren CSRF
        public_endpoints = ["auth.login", "auth.logout", "auth.registro_socio"]
        if request.endpoint in public_endpoints:
            return None

        # Permitir workers internos autenticados por token compartido
        if request.path in ("/api/security/process-worker", "/api/security/index-worker"):
            expected_token = os.environ.get("WORKER_INTERNAL_TOKEN", "")
            provided_token = request.headers.get("X-Internal-Worker-Token", "")
            if expected_token and provided_token and hmac.compare_digest(provided_token, expected_token):
                return None

        # Verificar Origin/Referer para mitigar CSRF también en form-data
        origin = request.headers.get("Origin", "").strip()
        referer = request.headers.get("Referer", "").strip()
        trusted = set(allowed_origins)

        def _extract_origin(url: str) -> str:
            try:
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc:
                    return f"{parsed.scheme}://{parsed.netloc}"
            except Exception:
                pass
            return ""

        request_origin = origin or _extract_origin(referer)
        # FIX CRÍTICO: Origin vacío en multipart/form-data (ej. upload) era bypass — ahora exige Origin/Referer
        if not request_origin:
            # Navegadores siempre envían Origin en POST cross-origin y Referer en form-data;
            # curl vacío se rechaza si es JSON/POST modificador y no es endpoint público
            if request.is_json or request.content_type and "multipart" in request.content_type:
                return jsonify({"error": "Origen no permitido - header Origin/Referer requerido"}), 403
        elif request_origin not in trusted:
            return jsonify({"error": "Origen no permitido"}), 403

        # Para peticiones JSON (API), verificar header X-Requested-With
        if request.is_json:
            requested_with = request.headers.get("X-Requested-With", "")
            if requested_with != "XMLHttpRequest":
                return jsonify({"error": "Petición inválida - header CSRF requerido"}), 403

        return None



    app.config["UPLOAD_FOLDER"] = base_dir / "uploads"
    app.config["BLACKLIST_PATH"] = base_dir / "config" / "blacklist.json"
    # Aumentar límite para videos de seguridad (12h+ puede ser 20-50GB)
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024 * 1024  # 10 GB máximo

    # Configuración de Flask
    app.config["JSON_AS_ASCII"] = False  # Permitir caracteres UTF-8 en JSON
    app.config["JSON_SORT_KEYS"] = False

    # ===== RATE LIMITING =====
    # Inicializar el limiter compartido con esta app
    limiter.init_app(app)
    logger.info("🛡️  Rate Limiting: HABILITADO")

    # ===== CREAR DIRECTORIOS NECESARIOS =====
    app.config["UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)

    # Verificar que existe el archivo de blacklist
    if not app.config["BLACKLIST_PATH"].exists():
        logger.warning(
            f"No se encontró el archivo de blacklist en {app.config['BLACKLIST_PATH']}"
        )
        logger.warning("   Asegúrate de crear config/blacklist.json")

    # ===== INICIALIZAR DEPENDENCIAS (INYECCIÓN CENTRALIZADA) =====
    # Todas las dependencias se crean e inyectan desde un solo lugar
    deps = init_dependencies(app)

    video_repository = deps["video_repository"]
    usuario_repository = deps["usuario_repository"]
    app_config = deps["app_config"]
    storage_adapter = deps["storage_adapter"]
    database_adapter = deps["db_adapter"]

    logger.info(
        f"Repositorio de videos inicializado - Videos: {video_repository.contar_total() if video_repository else 0}"
    )
    logger.info(
        f"Repositorio de usuarios inicializado - Usuarios: {usuario_repository.contar_total() if usuario_repository else 0}"
    )
    logger.info("Procesador de videos inyectado (DI)")
    logger.info("Stack local: SIN servicios GCP")

    # ===== AUTO-SYNC: Recuperar videos huérfanos del disco =====
    if database_adapter and database_adapter.is_available() and video_repository:
        try:
            upload_dir = app.config.get("UPLOAD_FOLDER", str(base_dir / "uploads"))

            # Obtener socios registrados desde el repositorio ya inicializado
            try:
                socios = usuario_repository.obtener_socios()
                socios_usernames = [s.username for s in socios if hasattr(s, 'username')]
            except Exception:
                socios_usernames = []

            if socios_usernames:
                # Sincronizar para el primer socio que tenga videos huérfanos
                for username in socios_usernames:
                    result = video_repository.sync_videos_from_disk(upload_dir, username)
                    if result.get("synced", 0) > 0:
                        logger.info(f"🔄 Auto-sync: {result['synced']} videos recuperados para '{username}' (workspace: {result.get('workspace_id', 'N/A')})")
                        break  # Solo asignar a un usuario
                    elif result.get("skipped", 0) > 0:
                        logger.info(f"✅ Videos ya sincronizados para '{username}': {result['skipped']} existentes")
                        break
                else:
                    logger.info("Auto-sync: No se encontraron videos huérfanos para sincronizar")
            else:
                logger.info("Auto-sync: No hay socios registrados para sincronizar videos")
        except Exception as e:
            logger.warning(f"Error en auto-sync de videos: {e}")

    # ===== REGISTRAR BLUEPRINTS (MICROSERVICIOS) =====
    # Microservicio de Autenticación
    app.register_blueprint(auth_bp)
    logger.info("Blueprint 'auth' registrado - Rutas: /login/*, /logout, /registro/*")

    # Microservicio de Carga (Socio)
    app.register_blueprint(socio_bp, url_prefix='/socio')
    logger.info("Blueprint 'socio' registrado - Rutas: /socio/ (upload), /socio/upload (POST)")

    # API v1 (versionada)
    app.register_blueprint(api_v1_bp)
    logger.info("Blueprint 'api_v1' registrado - Rutas: /api/v1/* (versionada)")
    
    # Workspaces
    app.register_blueprint(workspace_bp)
    logger.info("Blueprint 'workspaces' registrado - Rutas: /workspaces/*")
    
    # Workspace Chat IA
    app.register_blueprint(workspace_chat_bp)
    logger.info("Blueprint 'workspace_chat' registrado - Rutas: /workspaces/*/chat/*")
    
    # Upload legacy con Signed URLs (Fase 1 - Escalado)
    legacy_upload_enabled = os.environ.get("ENABLE_LEGACY_UPLOAD_API", "false").strip().lower() == "true"
    if legacy_upload_enabled:
        app.register_blueprint(upload_bp)
        logger.info("Blueprint 'upload' registrado - Rutas: /api/v1/videos/upload-url, confirm")
    else:
        logger.info("Blueprint 'upload' deshabilitado por seguridad (ENABLE_LEGACY_UPLOAD_API=false)")
    
    # Security Analysis (Videos de cámaras de seguridad)
    app.register_blueprint(app_security)
    logger.info("Blueprint 'security' registrado - Rutas: /api/security/* (análisis de seguridad)")

    # Operational Analysis (Análisis operativo contextual)
    app.register_blueprint(app_operational)
    logger.info("Blueprint 'operational' registrado - Rutas: /api/operational/* (análisis operativo)")

    # Audio Analysis (Análisis de audio de videos)
    app.register_blueprint(app_audio)
    logger.info("Blueprint 'audio' registrado - Rutas: /api/audio/* (análisis de audio)")

    # ===== SECURITY HEADERS =====
    @app.after_request
    def add_security_headers(response):
        """Agregar headers de seguridad a todas las respuestas"""
        # X-Frame-Options omitido: la CSP ya establece frame-ancestors 'none'
        # que tiene precedencia sobre X-Frame-Options en navegadores modernos.
        # Prevenir MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # XSS Protection (navegadores antiguos)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Permissions Policy (restringe APIs sensibles del navegador)
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        # HSTS solo en producción para evitar forzar HTTPS en entorno local
        if is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        # Content Security Policy
        # style-src-elem restricts <style> tags and external stylesheets (no unsafe-inline)
        # style-src-attr allows inline style attributes needed by React components
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "style-src-attr 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'"
        )
        # Cache control para respuestas con datos sensibles
        if response.content_type and "application/json" in response.content_type:
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, private"
            )
            response.headers["Pragma"] = "no-cache"
        return response

    # ===== RUTAS ADICIONALES =====
    @app.route("/home")
    def home():
        """Página de inicio que redirige al login"""
        return redirect(url_for("auth.login"))

    # Configuración de directorio de thumbnails
    thumbnails_dir = base_dir / "thumbnails"
    if not thumbnails_dir.exists():
        thumbnails_dir = Path(os.getcwd()) / "thumbnails"

    # Asegurar que existe si no estamos en producción (en prod debería estar montado)
    thumbnails_dir.mkdir(exist_ok=True)

    logger.info(f"📁 Directorio de thumbnails configurado en: {thumbnails_dir}")

    from flask import send_from_directory

    @app.route("/thumbnails/<path:filename>")
    def serve_thumbnail(filename):
        """Servir archivos de thumbnail estáticos"""
        return send_from_directory(thumbnails_dir, filename)

    @app.route("/favicon.ico")
    def favicon():
        """Devolver respuesta vacía para evitar 404 en navegadores"""
        from flask import Response
        return Response(status=204)

    # ===== SERVIR FRONTEND REACT =====
    # Servir el frontend compilado de React para todas las rutas que no son API
    frontend_build_path = base_dir / "frontend_build"

    if frontend_build_path.exists():
        logger.info(f"✅ Frontend React encontrado en: {frontend_build_path}")

        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve_react(path):
            """
            Servir el frontend React.
            Si la ruta es un archivo estático, lo sirve.
            Si no, sirve index.html (para React Router).
            """
            # Si es una ruta de API, no servir React
            if path.startswith(
                (
                    "api/",
                    "login",
                    "logout",
                    "registro",
                    "upload",
                    "admin/",
                    "health",
                    "thumbnails/",
                    "mis-videos",
                    "thumbnail/",
                )
            ):
                from flask import abort

                abort(404)

            # Si es un archivo estático (con extensión), intentar servirlo
            if path and "." in path.split("/")[-1]:
                file_path = frontend_build_path / path
                if file_path.exists():
                    return send_from_directory(frontend_build_path, path)

            # Para cualquier otra ruta, servir index.html (React Router se encarga)
            return send_from_directory(frontend_build_path, "index.html")
    else:
        logger.warning(f"⚠️  Frontend React NO encontrado en: {frontend_build_path}")

    @app.route("/health")
    @limiter.exempt
    def health_check():
        """Health check ligero - solo verifica que el servicio responde"""
        return {"status": "healthy", "service": "TIVIT Video"}, 200

    @app.route("/livez")
    @limiter.exempt
    def liveness_check():
        """Liveness probe: el proceso Flask está vivo."""
        return {"status": "alive", "service": "TIVIT Video"}, 200

    @app.route("/startupz")
    @limiter.exempt
    def startup_check():
        """Startup probe: la aplicación terminó su inicialización básica."""
        return {"status": "started", "service": "TIVIT Video"}, 200

    @app.route("/readyz")
    @limiter.exempt
    def readiness_check():
        """Readiness probe: valida dependencias críticas configuradas."""
        checks = {
            "database": database_adapter.is_available() if database_adapter and hasattr(database_adapter, "is_available") else False,
            "storage": storage_adapter.is_available() if storage_adapter and hasattr(storage_adapter, "is_available") else False,
        }
        ready = all(checks.values())
        return {"status": "ready" if ready else "not_ready", "checks": checks}, 200 if ready else 503

    @app.route("/health/full")
    @limiter.limit("10 per minute")
    def health_check_full():
        """Health check completo con estadisticas (lento, ~5-30s)"""
        # Solo usuarios autenticados pueden ver telemetría interna detallada.
        if "usuario_id" not in session:
            return jsonify({"error": "Acceso denegado"}), 403

        stats = video_repository.obtener_estadisticas() if video_repository else {}

        # Estado del stack local
        local_status = {
            "enabled": True,
            "storage": storage_adapter.is_available() if storage_adapter and hasattr(storage_adapter, "is_available") else False,
            "database": database_adapter.is_available() if database_adapter and hasattr(database_adapter, "is_available") else False,
        }

        # Extraer total de videos de la estructura correcta
        videos_total = stats.get("videos", {}).get("total", 0)

        return {
            "status": "healthy",
            "service": "TIVIT Video - Clean Architecture (stack local)",
            "microservicios": ["auth", "socio", "admin"],
            "videos_almacenados": videos_total,
            "usuarios_registrados": usuario_repository.contar_total() if usuario_repository else 0,
            "estadisticas": stats,
            "local": local_status,
            "frontend": frontend_build_path.exists(),
        }, 200

    @app.errorhandler(404)
    def not_found(e):
        """Manejador de error 404"""
        return {
            "error": "Ruta no encontrada",
            "rutas_disponibles": {
                "login": "/login (GET/POST) - Login unificado (socio y admin)",
                "registro": "/registro/socio (GET/POST) - Registro de socios",
                "logout": "/logout (GET) - Cerrar sesión",
                "socio": "/ (GET) - Formulario de carga de videos (requiere login)",
                "upload": "/upload (POST) - Procesar video (requiere login)",
                "admin": "/admin (GET) - Panel de administración (requiere login admin)",
                "api_videos": "/api/admin/videos (GET) - Listar videos (requiere login admin)",
                "health": "/health (GET) - Health check",
            },
        }, 404

    @app.errorhandler(413)
    def file_too_large(e):
        """Manejador de archivo demasiado grande"""
        return {
            "error": "El archivo es demasiado grande",
            "max_size_mb": app.config["MAX_CONTENT_LENGTH"] / (1024 * 1024),
        }, 413

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        """Manejador de rate limit excedido"""
        return jsonify(
            {
                "error": "Demasiadas solicitudes. Por favor, espera antes de intentar de nuevo.",
                "retry_after": e.description
                if hasattr(e, "description")
                else "60 seconds",
            }
        ), 429

    @app.errorhandler(500)
    def internal_error(e):
        """Manejador de errores internos - NO expone información del sistema"""
        app.logger.error(f"Error interno: {str(e)}")
        return jsonify(
            {
                "error": "Error interno del servidor",
                "message": "Ha ocurrido un error. Por favor, contacte al administrador.",
            }
        ), 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        """Manejador global de excepciones - Previene fuga de información"""
        app.logger.error(f"Excepción no manejada: {type(e).__name__}: {str(e)}")
        # En producción, nunca mostrar detalles del error
        if is_production:
            return jsonify({
                "error": "Error interno del servidor",
                "message": "Ha ocurrido un error. Por favor, contacte al administrador."
            }), 500
        else:
            # Solo en desarrollo mostrar más detalles
            return jsonify(
                {"error": "Error interno del servidor", "debug": str(e)}
            ), 500

    # Confiar solo en 1 nivel de proxy (nginx / Cloud Run / GCP LB)
    # Necesario para que X-Forwarded-For sea confiable y no falsificable
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    return app


def main():
    """
    Función principal para ejecutar la aplicación

    Levanta el servidor Flask en modo desarrollo
    """
    # Crear aplicación
    app = create_app()

    # Banner de inicio
    logger.info("\n" + "=" * 70)
    logger.info("🎬 TIVIT Video - Clean Architecture (Stack Local)")
    logger.info("=" * 70)
    logger.info("📦 Arquitectura:")
    logger.info("   • Domain: Entidades puras sin dependencias")
    logger.info("   • Use Cases: Lógica de aplicación (ProcesarVideoUseCase)")
    logger.info("   • Infrastructure: Flask, Repositorios, UI, Autenticación, Stack propio")
    logger.info("\n🔧 Microservicios:")
    logger.info("   • Auth: Sistema de login y registro")
    logger.info("   • Socio (Carga): Formulario de subida de videos")
    logger.info("   • Admin: Panel de administración y estadísticas")

    # Obtener configuración
    app_config = app.extensions.get("app_config")
    storage_adapter = app.extensions.get("storage_adapter")
    database_adapter = app.extensions.get("db_adapter")
    video_repo = app.extensions.get("video_repository")
    user_repo = app.extensions.get("usuario_repository")

    logger.info("\n💾 Persistencia:")
    logger.info("   • Stack Local: SIN servicios GCP")
    logger.info(f"   • Storage: {'✓' if storage_adapter and storage_adapter.is_available() else '✗'}")
    logger.info(
        f"   • Base de Datos: {'✓' if database_adapter and database_adapter.is_available() else '✗'}"
    )
    logger.info(f"   • Videos almacenados: {video_repo.contar_total() if video_repo else 0}")
    logger.info(f"   • Usuarios registrados: {user_repo.contar_total() if user_repo else 0}")
    logger.info("\n📁 Configuración:")
    logger.info(f"   • Directorio uploads: {app.config['UPLOAD_FOLDER']}")
    logger.info(f"   • Archivo blacklist: {app.config['BLACKLIST_PATH']}")
    logger.info(
        f"   • Tamaño máximo: {app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024):.0f} MB"
    )
    logger.info("\n🔐 Usuarios por defecto: admin, socio (ver variables de entorno para contraseñas)")
    logger.info("\n🌐 URLs Disponibles:")

    # DEBUG: Imprimir todas las rutas registradas con sus reglas
    logger.info("\n🔍 DEBUG: Rutas registradas en Flask (url_map):")
    for rule in app.url_map.iter_rules():
        logger.info(f"   • {rule.endpoint}: {rule}")
    logger.info("-" * 50 + "\n")

    logger.info(f"   • Frontend (React):    http://127.0.0.1:5173")
    logger.info("   • Login:               http://127.0.0.1:5173/login")
    logger.info("   • Registro:            http://127.0.0.1:5173/register")
    logger.info("   • Dashboard Socio:     http://127.0.0.1:5173/dashboard")
    logger.info("   • Subir Video:         http://127.0.0.1:5173/upload")
    logger.info("   • Dashboard Admin:     http://127.0.0.1:5173/admin/dashboard")
    logger.info("   • API Backend:         http://127.0.0.1:5000")
    logger.info("   • Health Check:        http://127.0.0.1:5000/health")
    logger.info("=" * 70)
    logger.info("🚀 Servidor iniciando...\n")

    # Ejecutar aplicación
    # use_reloader=False para mantener el repositorio en memoria entre requests
    # socketio.run reemplaza app.run para soportar websockets
    # Ejecutar aplicación con servidor estándar Flask (Threaded)
    # use_reloader=False recomendado en Docker salvo que se monte volumen
    port = int(os.environ.get("PORT", 5000))
    is_dev = os.environ.get("FLASK_ENV") != "production"
    app.run(
        host="0.0.0.0",
        port=port,
        debug=is_dev,  # SEGURIDAD: Solo debug en desarrollo, nunca en producción
        threaded=True,  # CRÍTICO: Permitir múltiples hilos para evitar bloqueo por video processing
        use_reloader=is_dev,  # Solo reloader en desarrollo
    )


if __name__ == "__main__":
    main()
