"""
Decoradores de Autenticación y Autorización
"""

from functools import wraps
from flask import session, redirect, url_for, flash, request, jsonify

from domain.entities import RolUsuario
from infrastructure.dependencies import get_user_repository


def login_requerido(f):
    """
    Decorador que requiere que el usuario esté autenticado

    Redirige a la página de login si no está autenticado
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión para acceder a esta página", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated_function


def socio_requerido(f):
    """
    Decorador que requiere que el usuario sea un socio autenticado

    Redirige al login apropiado si no está autenticado o no es socio
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión como socio para acceder", "warning")
            return redirect(url_for("auth.login"))

        # Verificar que el usuario es socio (usando DI)
        usuario = get_user_repository().obtener_por_id(session["usuario_id"])

        if not usuario or not usuario.es_socio():
            flash("No tienes permisos para acceder a esta página", "danger")
            return redirect(url_for("auth.login"))

        return f(*args, **kwargs)

    return decorated_function


def admin_requerido(f):
    """
    Stub: rol de administrador no disponible actualmente.
    Todas las rutas protegidas con este decorador devuelven 403.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import abort
        abort(403)

    return decorated_function


def api_admin_requerido(f):
    """
    Stub: rol de administrador no disponible actualmente.
    Todas las APIs protegidas con este decorador devuelven 403.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == "OPTIONS":
            return f(*args, **kwargs)
        return jsonify({"success": False, "error": "Función no disponible"}), 403

    return decorated_function


def api_socio_requerido(f):
    """
    Decorador para APIs que requiere que el usuario sea un socio

    Retorna JSON error si no está autenticado, inactivo o no es socio
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Permitir preflight checks de CORS sin autenticación
        if request.method == "OPTIONS":
            return "", 200

        if "usuario_id" not in session:
            return jsonify(
                {
                    "success": False,
                    "error": "No autenticado. Se requiere iniciar sesión",
                }
            ), 401

        # Verificar que el usuario es socio y está activo (usando DI)
        usuario = get_user_repository().obtener_por_id(session["usuario_id"])

        if not usuario:
            return jsonify(
                {
                    "success": False,
                    "error": "Usuario no encontrado",
                }
            ), 401

        if not usuario.activo:
            session.clear()
            return jsonify(
                {
                    "success": False,
                    "error": "Cuenta desactivada. Contacte al administrador",
                }
            ), 403

        if not usuario.es_socio():
            return jsonify(
                {
                    "success": False,
                    "error": "Acceso denegado. Se requieren permisos de socio",
                }
            ), 403

        return f(*args, **kwargs)

    return decorated_function


def obtener_usuario_actual():
    """
    Obtiene el usuario actualmente autenticado

    Returns:
        Usuario o None si no hay usuario autenticado
    """
    if "usuario_id" not in session:
        return None

    return get_user_repository().obtener_por_id(session["usuario_id"])
