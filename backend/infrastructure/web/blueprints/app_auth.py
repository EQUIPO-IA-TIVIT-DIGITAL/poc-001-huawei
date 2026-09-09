"""
Blueprint de Autenticación - AccessFan
Maneja el login, logout y registro de usuarios
"""

from flask import (
    Blueprint,
    request,
    render_template,
    jsonify,
    session,
    redirect,
    url_for,
    flash,
)
from datetime import datetime

from domain.entities import Usuario, RolUsuario, ReglaNegocioException
from infrastructure.dependencies import get_user_repository
from infrastructure.rate_limiter import (
    limiter,
    LOGIN_LIMIT,
    REGISTRO_LIMIT,
    POLLING_LIMIT,
)
from infrastructure.services.logging_service import get_logger
import uuid
from cachetools import TTLCache
import threading
import time
import os

# ===== Account Lockout =====
# Use TTLCache to auto-evict entries after LOCKOUT_DURATION_SECONDS (prevents memory leak)
MAX_FAILED_ATTEMPTS = int(os.getenv("AUTH_MAX_FAILED_ATTEMPTS", "5"))
LOCKOUT_WINDOW_SECONDS = int(os.getenv("AUTH_LOCKOUT_WINDOW_SECONDS", "300"))  # 5 minutes
LOCKOUT_DURATION_SECONDS = int(os.getenv("AUTH_LOCKOUT_DURATION_SECONDS", "900"))  # 15 minutes
_failed_logins = TTLCache(maxsize=10000, ttl=LOCKOUT_DURATION_SECONDS)  # username -> [timestamps]
_lockout_lock = threading.Lock()
logger = get_logger(__name__)


def _normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _mask_identifier(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[0]}***{value[-1]}"


def _client_ip() -> str:
    # FIX: usar remote_addr tras ProxyFix (evita IP spoof via X-Forwarded-For inyectado)
    return request.remote_addr or "127.0.0.1"


def _lockout_key(username: str) -> str:
    return f"auth:failed_login:{_normalize_username(username)}"


def _redis_failed_attempts_count(username: str) -> int:
    """Count failed attempts in a sliding window using Redis sorted set."""
    try:
        from infrastructure.services.job_queue import get_redis_connection

        redis_conn = get_redis_connection()
        key = _lockout_key(username)
        now = int(time.time())

        pipe = redis_conn.pipeline()
        pipe.zremrangebyscore(key, 0, now - LOCKOUT_WINDOW_SECONDS)
        pipe.zcard(key)
        _, count = pipe.execute()
        return int(count or 0)
    except Exception:
        return -1


def _record_failed_login_redis(username: str) -> bool:
    """Record failed attempt with Redis if available."""
    try:
        from infrastructure.services.job_queue import get_redis_connection

        redis_conn = get_redis_connection()
        key = _lockout_key(username)
        now = int(time.time())
        token = f"{now}:{uuid.uuid4().hex[:10]}"

        pipe = redis_conn.pipeline()
        pipe.zadd(key, {token: now})
        pipe.zremrangebyscore(key, 0, now - LOCKOUT_WINDOW_SECONDS)
        pipe.expire(key, LOCKOUT_DURATION_SECONDS)
        pipe.execute()
        return True
    except Exception:
        return False


def _login_rate_limit_key() -> str:
    username = ""
    if request.method == "POST":
        if request.is_json:
            data = request.get_json(silent=True) or {}
            username = _normalize_username(data.get("username", ""))
        else:
            username = _normalize_username(request.form.get("username", ""))
    return f"{_client_ip()}:{username or 'unknown'}"


def _register_rate_limit_key() -> str:
    email = ""
    if request.method == "POST":
        if request.is_json:
            data = request.get_json(silent=True) or {}
            email = _normalize_email(data.get("email", ""))
        else:
            email = _normalize_email(request.form.get("email", ""))
    return f"{_client_ip()}:{email or 'unknown'}"


def _check_account_lockout(username: str) -> bool:
    """Check if account is locked due to too many failed login attempts"""
    redis_count = _redis_failed_attempts_count(username)
    if redis_count >= 0:
        return redis_count >= MAX_FAILED_ATTEMPTS

    with _lockout_lock:
        now = datetime.now()
        normalized = _normalize_username(username)
        timestamps = _failed_logins.get(normalized, [])
        # Check recent attempts within the lockout window
        recent = [
            t for t in timestamps
            if (now - t).total_seconds() < LOCKOUT_WINDOW_SECONDS
        ]
        return len(recent) >= MAX_FAILED_ATTEMPTS


def _record_failed_login(username: str):
    """Record a failed login attempt"""
    if _record_failed_login_redis(username):
        return

    with _lockout_lock:
        normalized = _normalize_username(username)
        timestamps = _failed_logins.get(normalized, [])
        timestamps.append(datetime.now())
        _failed_logins[normalized] = timestamps


def _clear_failed_logins(username: str):
    """Clear failed login attempts after successful login"""
    try:
        from infrastructure.services.job_queue import get_redis_connection

        redis_conn = get_redis_connection()
        redis_conn.delete(_lockout_key(username))
    except Exception:
        pass

    with _lockout_lock:
        _failed_logins.pop(_normalize_username(username), None)


# Crear Blueprint
auth_bp = Blueprint("auth", __name__, template_folder="../ui/templates")

# Handler global para OPTIONS en todos los endpoints de este blueprint
@auth_bp.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.status_code = 200
        return response


@auth_bp.route("/login", methods=["GET", "POST", "OPTIONS"])
@limiter.limit(
    LOGIN_LIMIT,
    methods=["POST"],
    key_func=_login_rate_limit_key,
)  # Solo limitar POST (intentos de login)
def login():
    """
    Login unificado - acepta JSON desde frontend React

    Si es GET: retorna la página de login (para SSR fallback)
    Si es POST:
        - Espera JSON con {username, password}
        - Retorna JSON con {success, user} o error
    """
    # Si ya está autenticado y es GET
    if request.method == "GET" and "usuario_id" in session:
        usuario = get_user_repository().obtener_por_id(session["usuario_id"])
        if usuario:
            # Si es request JSON (desde React), retornar JSON
            if request.headers.get("Accept") == "application/json":
                return jsonify(
                    {
                        "authenticated": True,
                        "user": {
                            "id": usuario.id,
                            "username": usuario.username,
                            "rol": usuario.rol.value,
                            "nombre_completo": usuario.nombre_completo,
                        },
                    }
                ), 200
            # Si es request HTML (fallback SSR), redirigir
            return redirect(url_for("socio.index"))

    # GET sin autenticación - retorna página HTML (fallback)
    if request.method == "GET":
        return render_template("login.html")

    # POST - manejo de login
    if request.method == "POST":
        # Determinar si es JSON o form-data
        is_json = request.is_json

        if is_json:
            data = request.get_json() or {}
            username = _normalize_username(data.get("username", ""))
            password = data.get("password", "")
        else:
            username = _normalize_username(request.form.get("username", ""))
            password = request.form.get("password", "")

        if not username or not password:
            response_data = {
                "success": False,
                "error": "Username y contraseña son obligatorios",
            }
            if is_json:
                return jsonify(response_data), 400
            flash("Username y contraseña son obligatorios", "danger")
            return render_template("login.html")

        # Verificar lockout de cuenta
        if _check_account_lockout(username):
            logger.warning(
                "Lockout activo para usuario=%s ip=%s",
                _mask_identifier(username),
                _client_ip(),
            )
            response_data = {
                "success": False,
                "error": "Cuenta bloqueada temporalmente por demasiados intentos fallidos.",
            }
            if is_json:
                return jsonify(response_data), 429
            flash(response_data["error"], "danger")
            return render_template("login.html")

        # Autenticar usuario
        usuario = get_user_repository().autenticar(username, password)

        if not usuario:
            _record_failed_login(username)
            logger.warning(
                "Login fallido usuario=%s ip=%s",
                _mask_identifier(username),
                _client_ip(),
            )
            response_data = {"success": False, "error": "Credenciales incorrectas"}
            if is_json:
                return jsonify(response_data), 401
            flash("Credenciales incorrectas", "danger")
            return render_template("login.html")

        # Login exitoso - limpiar intentos fallidos
        _clear_failed_logins(username)
        logger.info(
            "Login exitoso usuario=%s ip=%s",
            _mask_identifier(username),
            _client_ip(),
        )

        # Actualizar último acceso
        usuario.ultimo_acceso = datetime.now().isoformat()
        get_user_repository().guardar(usuario)

        # Crear sesión completa
        session.clear()  # Evita session fixation
        session.permanent = True  # Hacer la sesión permanente
        session["usuario_id"] = usuario.id
        session["username"] = usuario.username
        session["rol"] = usuario.rol.value
        session["nombre_completo"] = usuario.nombre_completo
        session["auth_time"] = datetime.now().isoformat()

        # Si es JSON (React), retorna user data
        if is_json:
            return jsonify(
                {
                    "success": True,
                    "user": {
                        "id": usuario.id,
                        "username": usuario.username,
                        "rol": usuario.rol.value,
                        "nombre_completo": usuario.nombre_completo,
                    },
                }
            ), 200

        # Si es form-data (SSR fallback), redirige
        flash(f"¡Bienvenido {usuario.nombre_completo}!", "success")
        if usuario.es_socio():
            return redirect(url_for("socio.index"))
        return redirect(url_for("auth.login"))


@auth_bp.route("/api/check-auth", methods=["GET", "OPTIONS"])
@limiter.limit(POLLING_LIMIT)
def check_auth():
    """
    Endpoint para que React verifique si el usuario está logueado

    Retorna:
        JSON con {authenticated: boolean, user: {...}}
    """
    if "usuario_id" not in session:
        return jsonify({"authenticated": False, "user": None}), 200

    usuario = get_user_repository().obtener_por_id(session["usuario_id"])

    if not usuario:
        session.clear()
        return jsonify({"authenticated": False, "user": None}), 200

    # Construir URL de foto de perfil como data URL (funciona con <img> sin CORS)
    foto_url = usuario.foto_url or ""
    if foto_url.startswith(("s3://", "file://")):
        try:
            import base64
            import tempfile
            from pathlib import Path
            from infrastructure.dependencies import get_storage_adapter
            storage = get_storage_adapter()

            blob_path = None
            if foto_url.startswith("s3://"):
                parts = foto_url.split("/", 3)
                blob_path = parts[3] if len(parts) > 3 else parts[-1]
            else:
                blob_path = foto_url.removeprefix("file://")

            if blob_path:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    storage.descargar_archivo(blob_path, tmp_path)
                    image_bytes = Path(tmp_path).read_bytes()
                finally:
                    try:
                        Path(tmp_path).unlink(missing_ok=True)
                    except Exception:
                        pass
                encoded = base64.b64encode(image_bytes).decode("utf-8")
                foto_url = f"data:image/jpeg;base64,{encoded}"
            else:
                foto_url = ""
        except Exception as e:
            logger.warning(f"Error cargando foto de perfil: {e}")
            foto_url = ""
    
    return jsonify(
        {
            "authenticated": True,
            "user": {
                "id": usuario.id,
                "username": usuario.username,
                "rol": usuario.rol.value,
                "nombre": usuario.nombre_completo,
                "nombre_completo": usuario.nombre_completo,
                "email": usuario.email,
                "foto_url": foto_url,
            },
        }
    ), 200


@auth_bp.route("/logout", methods=["GET", "POST", "OPTIONS"])
def logout():
    """
    Cierra la sesión del usuario actual

    Si es JSON request, retorna JSON.
    Si es form request, redirige.
    """
    session.clear()

    # Si es JSON request (desde React)
    if request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify(
            {"success": True, "message": "Has cerrado sesión exitosamente"}
        ), 200

    # Si es request HTML (SSR fallback)
    flash("Has cerrado sesión exitosamente", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/registro/socio", methods=["GET", "POST", "OPTIONS"])
@limiter.limit(
    REGISTRO_LIMIT,
    methods=["POST"],
    key_func=_register_rate_limit_key,
)  # Limitar registros
def registro_socio():
    """
    Registro de nuevos usuarios socios

    Acepta JSON desde React o form-data desde SSR
    """
    if request.method == "POST":
        is_json = request.is_json

        if is_json:
            data = request.get_json() or {}
            username = _normalize_username(data.get("username", ""))
            password = data.get("password", "")
            password_confirm = data.get("password_confirm", "")
            nombre_completo = data.get("nombre_completo", "").strip()
            email = _normalize_email(data.get("email", ""))
        else:
            username = _normalize_username(request.form.get("username", ""))
            password = request.form.get("password", "")
            password_confirm = request.form.get("password_confirm", "")
            nombre_completo = request.form.get("nombre_completo", "").strip()
            email = _normalize_email(request.form.get("email", ""))

        # Importar validador
        from infrastructure.validators import UserValidator
        
        # Validaciones básicas
        if not all([username, password, password_confirm, nombre_completo, email]):
            error_msg = "Todos los campos son obligatorios"
            if is_json:
                return jsonify({"success": False, "error": error_msg}), 400
            flash(error_msg, "danger")
            return render_template("registro_socio.html")

        if password != password_confirm:
            error_msg = "Las contraseñas no coinciden"
            if is_json:
                return jsonify({"success": False, "error": error_msg}), 400
            flash(error_msg, "danger")
            return render_template("registro_socio.html")

        # Validar todos los campos con el nuevo validador robusto
        is_valid, validation_errors = UserValidator.validate_all_for_registration(
            username=username,
            email=email,
            password=password,
            nombre_completo=nombre_completo
        )
        
        if not is_valid:
            # Tomar el primer error
            first_error = validation_errors[0]
            error_msg = first_error.error_message
            
            if is_json:
                return jsonify({
                    "success": False, 
                    "error": error_msg,
                    "field": first_error.field,
                    "errors": [{"field": e.field, "message": e.error_message} for e in validation_errors]
                }), 400
            
            flash(error_msg, "danger")
            return render_template("registro_socio.html")

        try:
            # Crear nuevo usuario
            nuevo_usuario = Usuario(
                id=str(uuid.uuid4()),
                username=UserValidator.normalize_username(username),
                password_hash=Usuario.hash_password(password),
                nombre_completo=nombre_completo,
                email=UserValidator.normalize_email(email),
                rol=RolUsuario.SOCIO,
                fecha_creacion=datetime.now().isoformat(),
                ultimo_acceso=datetime.now().isoformat()
            )

            # Guardar usuario usando método atómico para prevenir duplicados
            success, error_msg, usuario_guardado = get_user_repository().guardar_atomic(nuevo_usuario)
            
            if not success:
                logger.warning(
                    "❌ Registro fallido usuario=%s error=%s ip=%s",
                    _mask_identifier(username),
                    error_msg,
                    _client_ip(),
                )
                if is_json:
                    return jsonify({"success": False, "error": error_msg}), 400
                flash(error_msg, "danger")
                return render_template("registro_socio.html")
            
            logger.info(
                "✅ Registro exitoso usuario=%s ip=%s",
                _mask_identifier(username),
                _client_ip(),
            )

            msg_success = "¡Registro exitoso! Ahora puedes iniciar sesión"
            if is_json:
                return jsonify({"success": True, "message": msg_success}), 201
            flash(msg_success, "success")
            return redirect(url_for("auth.login"))

        except ReglaNegocioException as e:
            error_msg = f"Error en el registro: {e.mensaje}"
            if is_json:
                return jsonify({"success": False, "error": error_msg}), 400
            flash(error_msg, "danger")
            return render_template("registro_socio.html")
        except Exception as e:
            logger.error(f"❌ Error inesperado en registro: {e}")
            error_msg = "Error al procesar el registro. Por favor, inténtalo de nuevo."
            if is_json:
                return jsonify({"success": False, "error": error_msg}), 500
            flash(error_msg, "danger")
            return render_template("registro_socio.html")

    return render_template("registro_socio.html")


@auth_bp.route("/perfil")
def perfil():
    """
    Muestra el perfil del usuario actual
    """
    if "usuario_id" not in session:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for("auth.login"))

    usuario = get_user_repository().obtener_por_id(session["usuario_id"])

    if not usuario:
        session.clear()
        flash("Usuario no encontrado", "danger")
        return redirect(url_for("auth.login"))

    if request.headers.get("Accept") == "application/json":
        return jsonify({
            "success": True,
            "user": {
                "id": usuario.id,
                "username": usuario.username,
                "rol": usuario.rol.value,
                "nombre_completo": usuario.nombre_completo,
                "email": usuario.email,
            },
        }), 200

    return redirect("/perfil")
