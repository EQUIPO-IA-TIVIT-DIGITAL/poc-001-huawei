"""
Blueprint de API v1 - TIVIT Video
Endpoints de API REST con versionado

Este blueprint centraliza todos los endpoints de API con versionado /api/v1/
para garantizar compatibilidad hacia atrás en cambios futuros.

Uso:
    GET  /api/v1/auth/check
    GET  /api/v1/videos
    POST /api/v1/videos/upload
    GET  /api/v1/admin/videos
    etc.

Versionado:
    - v1: Versión actual estable
    - Futuras versiones: /api/v2/, /api/v3/ etc.
"""

from flask import Blueprint, jsonify, request, session
from functools import wraps
import logging

from infrastructure.dependencies import get_video_repository, get_user_repository
from infrastructure.web.auth_decorators import socio_requerido, api_admin_requerido

logger = logging.getLogger(__name__)


# Crear Blueprint con prefijo de versión
api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

# Handler global para OPTIONS en todos los endpoints de este blueprint
@api_v1_bp.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.status_code = 200
        return response


# ========== UTILIDADES ==========


def api_response(success: bool, data=None, error=None, status_code=200):
    """Formato estándar de respuesta API"""
    response = {"success": success, "version": "v1"}
    if data is not None:
        response["data"] = data
    if error is not None:
        response["error"] = error
    return jsonify(response), status_code


def _foto_url_firmada(foto_url: str) -> str:
    """Convierte una URI de almacenamiento (s3://, file:// o gs:// legacy) en una URL local."""
    if not foto_url:
        return ""
    if foto_url.startswith(("http://", "https://")):
        # URL http(s) externa no gestionada: se devuelve tal cual.
        return foto_url
    from infrastructure.dependencies import get_storage_adapter

    storage = get_storage_adapter()
    if not storage or not storage.is_available():
        return ""
    signed = None
    if hasattr(storage, "generate_signed_url_from_storage_uri"):
        signed = storage.generate_signed_url_from_storage_uri(foto_url, expiration_minutes=60)
    elif hasattr(storage, "generate_signed_url"):
        key = foto_url
        if "://" in foto_url:
            parts = foto_url.split("://", 1)[1]
            key = parts.split("/", 1)[1] if "/" in parts else parts
        signed = storage.generate_signed_url(key, 60)
    return signed or ""


# ========== ENDPOINTS DE AUTENTICACIÓN ==========


@api_v1_bp.route("/auth/check", methods=["GET"])
def check_auth():
    """
    Verificar estado de autenticación del usuario

    Returns:
        JSON: {success, authenticated, user}
    """
    if "usuario_id" not in session:
        return api_response(True, {"authenticated": False, "user": None})

    usuario = get_user_repository().obtener_por_id(session["usuario_id"])

    if not usuario:
        session.clear()
        return api_response(True, {"authenticated": False, "user": None})

    # Generar URL de acceso si foto_url es una URI de almacenamiento local/legacy
    foto_url = usuario.foto_url or ""
    if foto_url:
        foto_url = _foto_url_firmada(foto_url)
    
    return api_response(
        True,
        {
            "authenticated": True,
            "user": {
                "id": usuario.id,
                "username": usuario.username,
                "email": usuario.email,
                "rol": usuario.rol.value,
                "nombre_completo": usuario.nombre_completo,
                "foto_url": foto_url,
            },
        },
    )


@api_v1_bp.route("/auth/me", methods=["GET"])
@socio_requerido
def get_current_user():
    """
    Obtener información del usuario actual

    Returns:
        JSON: Datos del usuario autenticado
    """
    usuario = get_user_repository().obtener_por_id(session["usuario_id"])

    if not usuario:
        return api_response(False, error="Usuario no encontrado", status_code=404)

    # Generar URL de acceso si foto_url es una URI de almacenamiento local/legacy
    foto_url = usuario.foto_url or ""
    if foto_url:
        foto_url = _foto_url_firmada(foto_url)

    return api_response(
        True,
        {
            "user": {
                "id": usuario.id,
                "username": usuario.username,
                "email": usuario.email,
                "rol": usuario.rol.value,
                "nombre_completo": usuario.nombre_completo,
                "activo": usuario.activo,
                "foto_url": foto_url,
            }
        },
    )


@api_v1_bp.route("/auth/profile", methods=["PUT", "OPTIONS"])
@socio_requerido
def update_profile():
    """
    Actualizar perfil del usuario autenticado

    Body JSON:
        - nombre_completo: Nuevo nombre completo
        - email: Nuevo email
        - foto_url: URL de la foto de perfil (opcional)

    Returns:
        JSON: {success, message}
    """
    data = request.get_json() or {}
    nombre_completo = data.get("nombre_completo", "").strip()
    email = data.get("email", "").strip()
    foto_url = data.get("foto_url", "").strip()

    if not nombre_completo or len(nombre_completo) < 3:
        return api_response(
            False, {"error": "El nombre debe tener al menos 3 caracteres"}
        ), 400

    if not email or "@" not in email:
        return api_response(False, {"error": "Email inválido"}), 400

    user_repo = get_user_repository()
    usuario = user_repo.obtener_por_id(session["usuario_id"])

    if not usuario:
        return api_response(False, {"error": "Usuario no encontrado"}), 404

    # Check if email is already in use by another user
    existing_user = user_repo.obtener_por_email(email)
    if existing_user and existing_user.id != usuario.id:
        return api_response(
            False, {"error": "El email ya está en uso por otro usuario"}
        ), 400

    # Update user
    usuario.nombre_completo = nombre_completo
    usuario.email = email
    if foto_url:
        usuario.foto_url = foto_url
    user_repo.guardar(usuario)

    # Update session
    session["nombre_completo"] = nombre_completo

    return api_response(True, {"message": "Perfil actualizado correctamente"})


@api_v1_bp.route("/auth/change-password", methods=["POST", "OPTIONS"])
@socio_requerido
def change_password():
    """
    Cambiar contraseña del usuario autenticado

    Body JSON:
        - current_password: Contraseña actual
        - new_password: Nueva contraseña

    Returns:
        JSON: {success, message}
    """
    data = request.get_json() or {}
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")

    if not current_password:
        return api_response(
            False, {"error": "Debes ingresar tu contraseña actual"}
        ), 400

    if len(new_password) < 8:
        return api_response(
            False, {"error": "La nueva contraseña debe tener al menos 8 caracteres"}
        ), 400

    user_repo = get_user_repository()
    usuario = user_repo.obtener_por_id(session["usuario_id"])

    if not usuario:
        return api_response(False, {"error": "Usuario no encontrado"}), 404

    # Verify current password
    if not usuario.verificar_password(current_password):
        logger.warning(
            "audit: cambio-contraseña FALLIDO usuario=%s ip=%s",
            session.get("username", ""),
            request.remote_addr,
        )
        return api_response(False, {"error": "La contraseña actual es incorrecta"}), 401

    # Update password
    from domain.entities import Usuario

    usuario.password_hash = Usuario.hash_password(new_password)
    user_repo.guardar(usuario)

    logger.warning(
        "audit: cambio-contraseña EXITOSO usuario=%s ip=%s",
        session.get("username", ""),
        request.remote_addr,
    )
    return api_response(True, {"message": "Contraseña cambiada correctamente"})


@api_v1_bp.route("/auth/upload-profile-photo", methods=["POST", "OPTIONS"])
@socio_requerido
def upload_profile_photo():
    """
    Subir foto de perfil del usuario

    Body JSON:
        - image: Imagen en base64

    Returns:
        JSON: {success, foto_url}
    """
    import base64
    import uuid
    from infrastructure.dependencies import get_storage_adapter
    
    data = request.get_json() or {}
    image_base64 = data.get("image", "")
    
    if not image_base64:
        return api_response(False, {"error": "No se envió ninguna imagen"}), 400
    
    try:
        # Remover prefijo data:image si existe
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]
        
        # Decodificar base64
        image_data = base64.b64decode(image_base64)
        
        # Validar tamaño (máx 5MB)
        if len(image_data) > 5 * 1024 * 1024:
            return api_response(False, {"error": "La imagen no debe superar 5MB"}), 400
        
        # Obtener usuario
        usuario = get_user_repository().obtener_por_id(session["usuario_id"])
        if not usuario:
            return api_response(False, {"error": "Usuario no encontrado"}), 404
        
        # Generar nombre único para la foto
        extension = "jpg"  # Por defecto
        if image_base64.startswith("iVBORw"):
            extension = "png"
        elif image_base64.startswith("/9j/"):
            extension = "jpg"
        elif image_base64.startswith("R0lGOD"):
            extension = "gif"
        
        # Mapeo correcto de extensiones a MIME types
        mime_type_map = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif"}
        content_type = mime_type_map.get(extension, "image/jpeg")
        
        filename = f"profile_photos/{usuario.id}_{uuid.uuid4().hex[:8]}.{extension}"
        
        # Subir a almacenamiento local (MinIO / filesystem)
        storage = get_storage_adapter()
        if not storage or not storage.is_available():
            return api_response(False, {"error": "Almacenamiento no disponible"}), 503

        if hasattr(storage, "upload_from_bytes"):
            uri = storage.upload_from_bytes(image_data, filename, content_type=content_type)
        else:
            uri = storage.upload_file(image_data, filename, content_type=content_type) if False else None
        if not uri:
            return api_response(False, {"error": "Error al subir la imagen"}), 500
        
        # Guardar URI persistente en la base de datos
        usuario.foto_url = uri
        get_user_repository().guardar(usuario)
        
        # Devolver como data URL para que <img src> funcione sin CORS ni cookies adicionales
        encoded = base64.b64encode(image_data).decode("utf-8")
        foto_url_display = f"data:{content_type};base64,{encoded}"
        
        return api_response(True, {"foto_url": foto_url_display, "message": "Foto subida correctamente"})
        
    except Exception as e:
        print(f"Error uploading profile photo: {e}")
        return api_response(False, {"error": "Error al procesar la imagen"}), 500


@api_v1_bp.route("/auth/profile-photo", methods=["GET"])
def get_profile_photo():
    """
    Proxy endpoint: descarga la foto de perfil del usuario desde almacenamiento local
    y la devuelve directamente. Requiere sesión activa.

    Returns:
        Image bytes con el Content-Type correspondiente
    """
    from flask import Response
    from infrastructure.dependencies import get_storage_adapter
    from pathlib import Path
    import tempfile

    if "usuario_id" not in session:
        return api_response(False, {"error": "No autenticado"}), 401

    usuario = get_user_repository().obtener_por_id(session["usuario_id"])
    if not usuario or not usuario.foto_url:
        return api_response(False, {"error": "No hay foto de perfil"}), 404

    foto_url = usuario.foto_url

    try:
        storage = get_storage_adapter()
        if not storage or not storage.is_available():
            return api_response(False, {"error": "Almacenamiento no disponible"}), 503

        blob_path = None
        content_type = "image/jpeg"

        if foto_url.startswith("s3://"):
            parts = foto_url.split("/", 3)
            blob_path = parts[3] if len(parts) > 3 else parts[-1]
        elif foto_url.startswith("gs://"):
            if hasattr(storage, "generate_signed_url_from_storage_uri"):
                parts = foto_url.split("/", 3)
                blob_path = parts[3] if len(parts) > 3 else parts[-1]
            else:
                parts = foto_url.replace("gs://", "").split("/", 1)
                blob_path = parts[1] if len(parts) > 1 else None
        elif foto_url.startswith("file://"):
            local_path = foto_url.replace("file://", "")
            if Path(local_path).exists():
                image_data = Path(local_path).read_bytes()
                return Response(
                    image_data,
                    mimetype=content_type,
                    headers={"Cache-Control": "private, max-age=3600"},
                )
            return api_response(False, {"error": "Archivo no encontrado"}), 404
        else:
            return api_response(False, {"error": "Formato de URL de foto no soportado"}), 404

        if not blob_path:
            return api_response(False, {"error": "URI de foto inválida"}), 500

        # Descargar bytes desde MinIO/filesystem usando descargar_archivo
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            storage.descargar_archivo(blob_path, tmp_path)
            image_data = Path(tmp_path).read_bytes()
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

        return Response(
            image_data,
            mimetype=content_type,
            headers={"Cache-Control": "private, max-age=3600"},
        )
    except Exception as e:
        logger.error(f"Error descargando foto de perfil: {e}")
        return api_response(False, {"error": "Error al obtener la foto"}), 500


# ========== ENDPOINTS DE VIDEOS (SOCIO) ==========


@api_v1_bp.route("/videos", methods=["GET"])
@socio_requerido
def listar_mis_videos():
    """
    Obtener lista de videos del usuario autenticado

    Returns:
        JSON: Lista de videos del usuario
    """
    username = session.get("username", "")
    todos_videos = get_video_repository().obtener_todos()
    videos_usuario = [v for v in todos_videos if v.usuario.lower() == username.lower()]

    videos_data = [
        {
            "id": v.id,
            "descripcion": v.descripcion,
            "estado": v.estado.value,
            "resultado_ia": v.metadatos_ia.get("resultado_ia"),
            "fecha_procesamiento": v.metadatos_ia.get("fecha_procesamiento"),
            "titulo": v.metadatos_ia.get("titulo", v.descripcion),
            "video_url": f"/socio/media/{v.id}",  # URL proxy (no requiere Signed URL)
            "thumbnail_url": f"/thumbnail/{v.id}",  # URL del thumbnail
            "duracion_segundos": v.metadatos_ia.get("duracion_segundos"),
            "storage_uri": v.metadatos_ia.get("storage_uri"),
        }
        for v in videos_usuario
    ]

    return api_response(True, {"videos": videos_data, "count": len(videos_data)})


@api_v1_bp.route("/videos/<video_id>", methods=["GET"])
@socio_requerido
def obtener_video(video_id: str):
    """
    Obtener detalles de un video específico

    Args:
        video_id: ID del video

    Returns:
        JSON: Detalles del video
    """
    video = get_video_repository().obtener_por_id(video_id)

    if not video:
        return api_response(False, error="Video no encontrado", status_code=404)

    # Verificar que el video pertenece al usuario
    username = session.get("username", "").lower()
    if video.usuario.lower() != username:
        return api_response(False, error="No autorizado", status_code=403)

    return api_response(
        True,
        {
            "video": {
                "id": video.id,
                "usuario": video.usuario,
                "descripcion": video.descripcion,
                "estado": video.estado.value,
                "metadatos_ia": video.metadatos_ia,
            }
        },
    )


# ========== ENDPOINTS DE ADMIN ==========


@api_v1_bp.route("/admin/videos", methods=["GET"])
@api_admin_requerido
def admin_listar_videos():
    """
    [ADMIN] Obtener todos los videos del sistema

    Returns:
        JSON: Lista de todos los videos con estadísticas
    """
    videos = get_video_repository().obtener_todos()
    stats = get_video_repository().obtener_estadisticas()

    videos_data = [
        {
            "id": v.id,
            "usuario": v.usuario,
            "descripcion": v.descripcion,
            "estado": v.estado.value,
            "resultado_ia": v.metadatos_ia.get("resultado_ia"),
            "fecha_procesamiento": v.metadatos_ia.get("fecha_procesamiento"),
        }
        for v in videos
    ]

    return api_response(True, {"videos": videos_data, "estadisticas": stats})


@api_v1_bp.route("/admin/estadisticas", methods=["GET"])
@api_admin_requerido
def admin_estadisticas():
    """
    [ADMIN] Obtener estadísticas del sistema

    Returns:
        JSON: Estadísticas de videos procesados
    """
    stats = get_video_repository().obtener_estadisticas()
    return api_response(True, {"estadisticas": stats})


@api_v1_bp.route("/admin/videos/<video_id>/aprobar", methods=["POST"])
@api_admin_requerido
def admin_aprobar_video(video_id: str):
    """
    [ADMIN] Aprobar un video manualmente

    Args:
        video_id: ID del video a aprobar
    """
    from domain.entities import EstadoVideo

    video = get_video_repository().obtener_por_id(video_id)
    if not video:
        return api_response(False, error="Video no encontrado", status_code=404)

    video.estado = EstadoVideo.APROBADO
    video.metadatos_ia["aprobado_por"] = session.get("username")
    video.metadatos_ia["aprobacion_manual"] = True

    get_video_repository().guardar(video)

    return api_response(True, {"message": f"Video {video_id} aprobado correctamente"})


@api_v1_bp.route("/admin/videos/<video_id>/rechazar", methods=["POST"])
@api_admin_requerido
def admin_rechazar_video(video_id: str):
    """
    [ADMIN] Rechazar un video manualmente

    Args:
        video_id: ID del video a rechazar
    """
    from domain.entities import EstadoVideo

    data = request.get_json() or {}
    razon = data.get("razon", "Rechazado por administrador")

    video = get_video_repository().obtener_por_id(video_id)
    if not video:
        return api_response(False, error="Video no encontrado", status_code=404)

    video.estado = EstadoVideo.RECHAZADO
    video.metadatos_ia["rechazado_por"] = session.get("username")
    video.metadatos_ia["razon_rechazo_manual"] = razon

    get_video_repository().guardar(video)

    return api_response(True, {"message": f"Video {video_id} rechazado correctamente"})


# ========== ENDPOINT DE VERSIÓN ==========


@api_v1_bp.route("/version", methods=["GET"])
def api_version():
    """Información de la versión de la API"""
    return api_response(
        True, {"api_version": "v1", "app_name": "TIVIT Video", "status": "stable"}
    )


# ========== ENDPOINTS DE ESTADO LOCAL ==========


@api_v1_bp.route("/status/local", methods=["GET"])
@api_admin_requerido
def local_status():
    """
    [ADMIN] Obtener estado de los servicios de infraestructura local

    Returns:
        JSON con el estado de cada servicio
    """
    try:
        from infrastructure.dependencies import (
            get_storage_adapter,
            verificar_conexion_local,
        )

        health = verificar_conexion_local()

        return api_response(True, {
            "local": {
                "enabled": True,
                "services": {
                    "storage": health["storage"],
                    "database": health["database"],
                    "video_analysis": health["video_intelligence"],
                    "task_queue": health["task_queue"],
                    "ai_gateway": health["ai_gateway"],
                },
            }
        })

    except Exception as e:
        return api_response(False, error="Error interno del servidor", status_code=500)


@api_v1_bp.route("/status/ai", methods=["GET"])
@api_admin_requerido
def ai_status():
    """
    [ADMIN] Obtener estado de los servicios de IA

    Returns:
        JSON con el estado de Gemini
    """
    try:
        from infrastructure.adapters.ai_service import get_ai_service

        ai_service = get_ai_service()

        try:
            from infrastructure.services.job_queue import get_redis_connection
            get_redis_connection().ping()
            tasks_available = True
        except Exception:
            tasks_available = False

        tasks = {
            "available": tasks_available,
            "queue": "video_processing" if tasks_available else None,
            "service": "Redis + RQ",
        }

        return api_response(
            True, {"ai": ai_service.get_status(), "tasks": tasks}
        )

    except Exception as e:
        return api_response(False, error="Error interno del servidor", status_code=500)


@api_v1_bp.route("/storage/videos", methods=["GET"])
@api_admin_requerido
def list_storage_videos():
    """
    [ADMIN] Listar videos en Cloud Storage

    Returns:
        JSON con lista de videos en el bucket
    """
    try:
        from infrastructure.dependencies import get_storage_adapter

        storage = get_storage_adapter()

        if not storage or not storage.is_available():
            return api_response(
                False, error="Cloud Storage no disponible", status_code=503
            )

        videos = storage.list_videos()

        return api_response(
            True,
            {
                "count": len(videos),
                "videos": videos[:100],  # Limitar a 100
            },
        )

    except Exception as e:
        return api_response(False, error="Error interno del servidor", status_code=500)


@api_v1_bp.route("/storage/video/<video_id>/url", methods=["GET"])
@socio_requerido
def get_video_signed_url(video_id: str):
    """
    Devuelve la URL del proxy de streaming para un video.
    Reemplaza la Signed URL — no requiere Service Account key.
    """
    try:
        video = get_video_repository().obtener_por_id(video_id)
        if not video:
            return api_response(False, error="Video no encontrado", status_code=404)

        username = session.get("username", "").lower()
        if video.usuario.lower() != username:
            return api_response(False, error="No autorizado", status_code=403)

        proxy_url = f"/socio/media/{video_id}"
        return api_response(True, {"signed_url": proxy_url, "expires_in_minutes": 9999})

    except Exception as e:
        return api_response(False, error="Error interno del servidor", status_code=500)


# ========== ENDPOINTS DE SEGURIDAD CONTEXTUAL ==========


@api_v1_bp.route("/security/analyze-context", methods=["POST", "OPTIONS"])
@socio_requerido
def analyze_security_context():
    """
    Iniciar análisis contextual de un video de seguridad
    
    Body JSON:
        - video_id: ID del video a analizar
        - contexto: Pregunta/contexto del usuario (ej: "cuántas personas salieron")
        - modo: "ESTANDAR" o "PROFUNDO" (opcional, default: ESTANDAR)
    
    Returns:
        JSON: {success, analysis_id, message}
    """
    import uuid
    from datetime import datetime
    
    data = request.get_json() or {}
    video_id = data.get("video_id", "").strip()
    contexto = data.get("contexto", "").strip()
    modo = data.get("modo", "ESTANDAR").upper()
    
    # Validaciones
    if not video_id:
        return api_response(False, error="video_id es requerido", status_code=400)
    
    if not contexto:
        return api_response(False, error="contexto es requerido", status_code=400)
    
    if len(contexto) < 5:
        return api_response(False, error="El contexto debe tener al menos 5 caracteres", status_code=400)
    
    if modo not in ["ESTANDAR", "PROFUNDO"]:
        return api_response(False, error="modo debe ser ESTANDAR o PROFUNDO", status_code=400)
    
    # Generar ID de análisis
    analysis_id = str(uuid.uuid4())
    
    try:
        from infrastructure.repositories.security_video_repository import SecurityVideoRepository

        video = SecurityVideoRepository().obtener_video(video_id)
        if not video:
            return api_response(False, error="Video de seguridad no encontrado", status_code=404)
        if session.get("rol") != "admin" and video.usuario != session.get("username"):
            return api_response(False, error="No autorizado", status_code=403)

        # Almacenar análisis pendiente en SQLAlchemy
        from infrastructure.db.session import SessionLocal
        from infrastructure.db.models import SecurityAnalysisModel

        session_db = SessionLocal()
        try:
            model = SecurityAnalysisModel(
                id=analysis_id,
                video_id=video_id,
                contexto=contexto,
                modo=modo,
                estado="PENDIENTE",
                usuario_id=session.get("usuario_id", ""),
                username=session.get("username", ""),
                fecha_solicitud=datetime.utcnow().isoformat(),
                resultado={},
            )
            session_db.add(model)
            session_db.commit()
        finally:
            session_db.close()

        from infrastructure.services.job_queue import (
            enqueue_contextual_security_analysis,
            is_queue_required,
            is_redis_available,
        )

        if is_redis_available():
            job_id = enqueue_contextual_security_analysis(analysis_id, video_id, contexto, modo)
            if not job_id:
                s = SessionLocal()
                try:
                    m = s.get(SecurityAnalysisModel, analysis_id)
                    if m:
                        m.estado = "error"
                        m.resultado = {"error": "No se pudo encolar el análisis"}
                        s.commit()
                finally:
                    s.close()
                return api_response(False, error="No se pudo encolar el análisis", status_code=503)
        elif is_queue_required():
            s = SessionLocal()
            try:
                m = s.get(SecurityAnalysisModel, analysis_id)
                if m:
                    m.estado = "error"
                    m.resultado = {"error": "Cola asíncrona no disponible"}
                    s.commit()
            finally:
                s.close()
            return api_response(False, error="Cola asíncrona no disponible", status_code=503)
        else:
            # The development fallback uses the same function so it persists success/failure.
            import threading
            from worker import process_contextual_security_analysis

            thread = threading.Thread(
                target=process_contextual_security_analysis,
                args=(analysis_id, video_id, contexto, modo),
                daemon=True,
            )
            thread.start()
            job_id = None
        
        return api_response(True, {
            "analysis_id": analysis_id,
            "message": "Análisis iniciado correctamente",
            "modo": modo,
            "tiempo_estimado_minutos": 15 if modo == "ESTANDAR" else 25
        })
        
    except Exception as e:
        import logging
        logging.error(f"Error iniciando análisis contextual: {e}")
        return api_response(False, error="Error interno del servidor", status_code=500)


@api_v1_bp.route("/security/analyses", methods=["GET"])
@socio_requerido
def list_security_analyses():
    """
    Listar análisis de seguridad del usuario
    
    Returns:
        JSON: Lista de análisis con su estado
    """
    try:
        from infrastructure.db.session import SessionLocal
        from infrastructure.db.models import SecurityAnalysisModel

        username = session.get("username")

        s = SessionLocal()
        try:
            rows = (
                s.query(SecurityAnalysisModel)
                .filter_by(username=username)
                .order_by(SecurityAnalysisModel.created_at.desc())
                .limit(20)
                .all()
            )
            analyses = [
                {
                    "id": r.id,
                    "video_id": r.video_id,
                    "contexto": r.contexto,
                    "modo": r.modo,
                    "estado": r.estado,
                    "usuario_id": r.usuario_id,
                    "username": r.username,
                    "fecha_solicitud": r.fecha_solicitud,
                    "resultado": r.resultado,
                }
                for r in rows
            ]
        finally:
            s.close()

        return api_response(True, {
            "analyses": analyses,
            "count": len(analyses),
        })
        
    except Exception as e:
        return api_response(False, error="Error interno del servidor", status_code=500)


@api_v1_bp.route("/security/analyses/<analysis_id>", methods=["GET"])
@socio_requerido
def get_security_analysis(analysis_id: str):
    """
    Obtener detalles de un análisis específico
    
    Args:
        analysis_id: ID del análisis
    
    Returns:
        JSON: Detalles del análisis
    """
    try:
        from infrastructure.db.session import SessionLocal
        from infrastructure.db.models import SecurityAnalysisModel

        s = SessionLocal()
        try:
            r = s.query(SecurityAnalysisModel).filter_by(id=analysis_id).first()
        finally:
            s.close()
        
        if not r:
            return api_response(False, error="Análisis no encontrado", status_code=404)
        
        username = session.get("username")
        if r.username != username:
            return api_response(False, error="No autorizado", status_code=403)
        
        analysis = {
            "id": r.id,
            "video_id": r.video_id,
            "contexto": r.contexto,
            "modo": r.modo,
            "estado": r.estado,
            "usuario_id": r.usuario_id,
            "username": r.username,
            "fecha_solicitud": r.fecha_solicitud,
            "resultado": r.resultado,
        }

        return api_response(True, {"analysis": analysis})
        
    except Exception as e:
        return api_response(False, error="Error interno del servidor", status_code=500)


@api_v1_bp.route("/security/analyses/<analysis_id>/report", methods=["GET"])
@socio_requerido
def download_security_report(analysis_id: str):
    """
    Descargar reporte de un análisis
    
    Args:
        analysis_id: ID del análisis
        formato: pdf, json, txt (query param)
    
    Returns:
        Archivo del reporte
    """
    from flask import send_file
    import os

    formato = request.args.get("formato", "pdf").lower()

    if formato not in ["pdf", "json", "txt"]:
        return api_response(False, error="Formato no válido (pdf, json, txt)", status_code=400)

    try:
        from infrastructure.db.session import SessionLocal
        from infrastructure.db.models import SecurityAnalysisModel

        s = SessionLocal()
        try:
            r = s.query(SecurityAnalysisModel).filter_by(id=analysis_id).first()
        finally:
            s.close()

        if not r:
            return api_response(False, error="Análisis no encontrado", status_code=404)

        # Verificar autorización
        username = session.get("username")
        if r.username != username:
            return api_response(False, error="No autorizado", status_code=403)

        analysis = {
            "id": r.id,
            "video_id": r.video_id,
            "contexto": r.contexto,
            "modo": r.modo,
            "estado": r.estado,
            "usuario_id": r.usuario_id,
            "username": r.username,
            "fecha_solicitud": r.fecha_solicitud,
            "resultado": r.resultado,
        }

        # Obtener path del reporte
        resultado = r.resultado or {}
        report_path = resultado.get(f"report_path_{formato}") or resultado.get("report_path")
        
        if not report_path or not os.path.exists(report_path):
            # Generar reporte on-demand
            from infrastructure.services.enhanced_report_generator import EnhancedReportGenerator
            
            generator = EnhancedReportGenerator()
            report_path = generator.generate_contextual_report(
                analysis_data=analysis,
                formato=formato
            )
        
        if report_path and os.path.exists(report_path):
            return send_file(
                report_path,
                as_attachment=True,
                download_name=f"reporte_seguridad_{analysis_id[:8]}.{formato}"
            )
        else:
            return api_response(False, error="Reporte no disponible", status_code=404)
        
    except Exception as e:
        import logging
        logging.error(f"Error descargando reporte: {e}")
        return api_response(False, error="Error interno del servidor", status_code=500)
