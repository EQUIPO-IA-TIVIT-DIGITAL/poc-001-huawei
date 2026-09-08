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

    # Generar URL firmada si foto_url es una URI gs:// o URL pública de GCS
    foto_url = usuario.foto_url or ""
    if foto_url.startswith("gs://") or foto_url.startswith("https://storage.googleapis.com/"):
        from infrastructure.adapters.gcp_storage import GCPStorage
        gcs = GCPStorage()
        if foto_url.startswith("https://storage.googleapis.com/"):
            path_part = foto_url.replace("https://storage.googleapis.com/", "")
            foto_url = f"gs://{path_part}"
        foto_url = gcs.generate_signed_url_from_gcs_uri(foto_url, expiration_minutes=60) or ""
    
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

    # Generar URL firmada si foto_url es una URI gs:// o URL pública de GCS
    foto_url = usuario.foto_url or ""
    if foto_url.startswith("gs://") or foto_url.startswith("https://storage.googleapis.com/"):
        from infrastructure.adapters.gcp_storage import GCPStorage as _GCS
        _gcs = _GCS()
        if foto_url.startswith("https://storage.googleapis.com/"):
            path_part = foto_url.replace("https://storage.googleapis.com/", "")
            foto_url = f"gs://{path_part}"
        foto_url = _gcs.generate_signed_url_from_gcs_uri(foto_url, expiration_minutes=60) or ""

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
    from io import BytesIO
    from infrastructure.adapters.gcp_storage import GCPStorage
    
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
        
        # Subir a GCS
        gcs_storage = GCPStorage()
        gcs_uri = gcs_storage.upload_from_bytes(
            image_data,
            filename,
            content_type=content_type
        )
        
        if not gcs_uri:
            return api_response(False, {"error": "Error al subir la imagen"}), 500
        
        # Guardar URI gs:// en Firestore (persistente)
        usuario.foto_url = gcs_uri
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
    Proxy endpoint: descarga la foto de perfil del usuario desde GCS
    y la devuelve directamente. Requiere sesión activa.

    Returns:
        Image bytes con el Content-Type correspondiente
    """
    from infrastructure.adapters.gcp_storage import GCPStorage
    from flask import Response

    if "usuario_id" not in session:
        return api_response(False, {"error": "No autenticado"}), 401

    usuario = get_user_repository().obtener_por_id(session["usuario_id"])
    if not usuario or not usuario.foto_url:
        return api_response(False, {"error": "No hay foto de perfil"}), 404

    foto_url = usuario.foto_url
    if not foto_url.startswith("gs://"):
        return api_response(False, {"error": "Formato de URL de foto no soportado"}), 404

    try:
        gcs = GCPStorage()
        # Extraer el blob path de la URI gs://bucket/path/to/blob
        path_without_scheme = foto_url[5:]  # Remove "gs://"
        parts = path_without_scheme.split("/", 1)
        if len(parts) < 2:
            return api_response(False, {"error": "URI de foto inválida"}), 500

        blob_path = parts[1]
        blob = gcs.bucket.blob(blob_path)
        image_data = blob.download_as_bytes()
        content_type = blob.content_type or "image/jpeg"

        return Response(
            image_data,
            mimetype=content_type,
            headers={
                "Cache-Control": "private, max-age=3600",
            }
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
            "gcs_uri": v.metadatos_ia.get("gcs_uri"),
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


# ========== ENDPOINTS DE ESTADO GCP ==========


@api_v1_bp.route("/status/gcp", methods=["GET"])
@api_admin_requerido
def gcp_status():
    """
    [ADMIN] Obtener estado de los servicios de Google Cloud Platform

    Returns:
        JSON con el estado de cada servicio GCP
    """
    try:
        from infrastructure.dependencies import (
            get_gcp_config,
            get_storage_adapter,
            get_firestore_adapter,
            get_video_intelligence_adapter,
        )

        gcp_config = get_gcp_config()
        storage = get_storage_adapter()
        firestore = get_firestore_adapter()
        video_intelligence = get_video_intelligence_adapter()

        status = {
            "gcp_enabled": gcp_config.is_gcp_enabled() if gcp_config else False,
            "project_id": gcp_config.PROJECT_ID if gcp_config else None,
            "region": gcp_config.REGION if gcp_config else None,
            "services": {
                "cloud_storage": {
                    "available": storage.is_available() if storage else False,
                    "bucket_name": gcp_config.BUCKET_NAME if gcp_config else None,
                },
                "firestore": {
                    "available": firestore.is_available() if firestore else False
                },
                "video_intelligence": {
                    "available": video_intelligence.is_available()
                    if video_intelligence
                    else False
                },
            },
        }

        # Agregar estadísticas de storage si está disponible
        if storage and storage.is_available():
            status["services"]["cloud_storage"]["stats"] = storage.get_storage_stats()

        return api_response(True, {"gcp": status})

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
        from infrastructure.adapters.cloud_tasks_adapter import get_cloud_tasks

        ai_service = get_ai_service()
        cloud_tasks = get_cloud_tasks()

        return api_response(
            True, {"ai": ai_service.get_status(), "tasks": cloud_tasks.get_status()}
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
        # Almacenar análisis pendiente
        from infrastructure.dependencies import get_firestore_adapter
        firestore = get_firestore_adapter()
        
        analysis_data = {
            "id": analysis_id,
            "video_id": video_id,
            "contexto": contexto,
            "modo": modo,
            "estado": "pendiente",
            "usuario_id": session.get("usuario_id"),
            "username": session.get("username"),
            "fecha_solicitud": datetime.utcnow().isoformat(),
            "resultado": None
        }
        
        if firestore and firestore.is_available():
            firestore.guardar("security_analyses", analysis_id, analysis_data)
        
        # Iniciar procesamiento en background (Cloud Tasks si disponible)
        from infrastructure.adapters.cloud_tasks_adapter import get_cloud_tasks
        cloud_tasks = get_cloud_tasks()
        
        if cloud_tasks and cloud_tasks.is_available():
            # Encolar tarea
            cloud_tasks.encolar_analisis_contextual(
                analysis_id=analysis_id,
                video_id=video_id,
                contexto=contexto,
                modo=modo
            )
        else:
            # Ejecutar síncronicamente (para desarrollo local)
            from use_cases.security_video_processor import SecurityVideoProcessor
            import threading
            
            def run_analysis():
                processor = SecurityVideoProcessor()
                resultado = processor.process_with_context(video_id, contexto, modo)
                
                # Actualizar en Firestore
                if firestore and firestore.is_available():
                    analysis_data["estado"] = resultado.get("estado", "completado")
                    analysis_data["resultado"] = resultado
                    firestore.guardar("security_analyses", analysis_id, analysis_data)
            
            # Ejecutar en thread separado
            thread = threading.Thread(target=run_analysis)
            thread.start()
        
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
        from infrastructure.dependencies import get_firestore_adapter
        firestore = get_firestore_adapter()
        
        if not firestore or not firestore.is_available():
            return api_response(True, {"analyses": [], "count": 0})
        
        username = session.get("username")
        
        # Obtener análisis del usuario
        all_analyses = firestore.obtener_coleccion("security_analyses")
        user_analyses = [
            a for a in all_analyses 
            if a.get("username") == username
        ]
        
        # Ordenar por fecha (más reciente primero)
        user_analyses.sort(
            key=lambda x: x.get("fecha_solicitud", ""), 
            reverse=True
        )
        
        return api_response(True, {
            "analyses": user_analyses[:20],  # Limitar a 20
            "count": len(user_analyses)
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
        from infrastructure.dependencies import get_firestore_adapter
        firestore = get_firestore_adapter()
        
        if not firestore or not firestore.is_available():
            return api_response(False, error="Firestore no disponible", status_code=503)
        
        analysis = firestore.obtener("security_analyses", analysis_id)
        
        if not analysis:
            return api_response(False, error="Análisis no encontrado", status_code=404)
        
        # Verificar que pertenece al usuario
        username = session.get("username")
        if analysis.get("username") != username:
            return api_response(False, error="No autorizado", status_code=403)
        
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
        from infrastructure.dependencies import get_firestore_adapter
        firestore = get_firestore_adapter()
        
        if not firestore or not firestore.is_available():
            return api_response(False, error="Firestore no disponible", status_code=503)
        
        analysis = firestore.obtener("security_analyses", analysis_id)
        
        if not analysis:
            return api_response(False, error="Análisis no encontrado", status_code=404)
        
        # Verificar autorización
        username = session.get("username")
        if analysis.get("username") != username:
            return api_response(False, error="No autorizado", status_code=403)
        
        # Obtener path del reporte
        resultado = analysis.get("resultado", {})
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
