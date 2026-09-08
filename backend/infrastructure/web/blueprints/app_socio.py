"""
Blueprint del Microservicio de Carga - AccessFan
Maneja la subida y procesamiento de videos de los socios
"""

import os
import json
import uuid
from pathlib import Path
from flask import (
    Blueprint,
    request,
    render_template,
    jsonify,
    current_app,
    session,
    Response,
)

import logging
logger = logging.getLogger(__name__)

from werkzeug.utils import secure_filename
from domain.entities import Video, EstadoVideo, ReglaNegocioException
from infrastructure.dependencies import (
    get_video_repository,
    get_video_processor,
    get_storage_adapter,
)
from infrastructure.web.auth_decorators import socio_requerido, api_socio_requerido
from infrastructure.rate_limiter import (
    limiter,
    UPLOAD_LIMIT,
    POLLING_LIMIT,
    VIDEO_DETAILS_LIMIT,
)
from infrastructure.repositories.workspace_repository import WorkspaceRepositoryFirestore
from infrastructure.services.workspace_stats_service import recalculate_workspace_stats
from use_cases.socio_video_service import SocioVideoService

# Diccionario para controlar cancelaciones {video_id: bool}
_CANCELLATION_TOKENS = {}

# Crear Blueprint
socio_bp = Blueprint("socio", __name__, template_folder="../ui/templates")

# Handler global para OPTIONS en todos los endpoints de este blueprint
@socio_bp.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.status_code = 200
        return response


@socio_bp.route("/video/<video_id>/cancel", methods=["POST", "OPTIONS"])
@api_socio_requerido
def cancel_processing_endpoint(video_id):
    """
    Endpoint para cancelar el procesamiento activo de un video.
    Reemplaza al evento de socket 'cancel_processing'.
    """
    if not video_id:
        return jsonify({"success": False, "error": "Video ID requerido"}), 400

    # Verificar que el video pertenece al usuario autenticado (prevenir IDOR)
    video = get_video_repository().obtener_por_id(video_id)
    if not video:
        return jsonify({"success": False, "error": "Video no encontrado"}), 404
    if video.usuario != session.get("username"):
        return jsonify({"success": False, "error": "Acceso denegado"}), 403

    _CANCELLATION_TOKENS[video_id] = True
    current_app.logger.info(
        f"🛑 CANCELANDO video {video_id} a solicitud del usuario (HTTP)..."
    )
    return jsonify(
        {"success": True, "message": "Solicitud de cancelación recibida"}
    ), 200


@socio_bp.route("/video/<video_id>/status", methods=["GET", "OPTIONS"])
@api_socio_requerido
@limiter.limit(POLLING_LIMIT)
def get_video_processing_status(video_id):
    """
    Endpoint para polling del estado de procesamiento.
    Devuelve el estado actual leido directamente de la BD (persistencia).
    """
    video = get_video_repository().obtener_por_id(video_id)
    if not video:
        return jsonify({"status": "error", "message": "Video no encontrado"}), 404

    # Verificar ownership (prevenir IDOR)
    if video.usuario != session.get("username"):
        return jsonify({"status": "error", "message": "Acceso denegado"}), 403

    # Estado final
    if video.estado in [EstadoVideo.COMPLETADO, EstadoVideo.APROBADO, EstadoVideo.RECHAZADO]:
        return jsonify(
            {
                "status": "completed",
                "step": 8,
                "message": "Procesamiento finalizado",
                "final_result": {
                    "video": {
                        "id": video.id,
                        "titulo": video.metadatos_ia.get("titulo", "Video Procesado"),
                        "resultado": video.metadatos_ia.get("resultado_ia"),
                        "confianza": video.metadatos_ia.get("confianza_ia", 0),
                        "analisis": video.metadatos_ia.get("analisis_ia", ""),
                        "razon": video.metadatos_ia.get("razon_decision")
                        or video.metadatos_ia.get("razon_rechazo"),
                        "video_url": f"/socio/media/{video.id}",  # URL proxy
                        "duracion_segundos": video.metadatos_ia.get(
                            "duracion_segundos"
                        ),
                    },
                    "finalStatus": (
                        "approved"
                        if video.metadatos_ia.get("resultado_ia") == "APROBADO"
                        else "rejected"
                        if video.metadatos_ia.get("resultado_ia") == "RECHAZADO"
                        else "review"
                        if video.metadatos_ia.get("resultado_ia") == "REQUIERE_REVISION"
                        else "unknown"
                    ),
                },
            }
        )
    elif video.estado == EstadoVideo.ERROR:
        return jsonify(
            {
                "status": "error",
                "step": 0,
                "message": video.metadatos_ia.get(
                    "error_procesamiento", "Error desconocido"
                ),
                "error": {
                    "message": video.metadatos_ia.get("error_procesamiento", "Error"),
                    "errorCode": "PROCESSING_ERROR",
                },
            }
        )
    elif video.estado == EstadoVideo.PENDIENTE:
        # Puede que tenga información de progreso guardada aunque esté en 'PENDIENTE' durante el loop
        progreso = video.metadatos_ia.get("progreso")
        if progreso:
            return jsonify(progreso)

        return jsonify(
            {"status": "pending", "step": 0, "message": "En cola de procesamiento..."}
        )

    # Si está procesando, devolver lo que esté en metadatos
    progreso = video.metadatos_ia.get("progreso")
    if progreso:
        return jsonify(progreso)

    # Fallback
    return jsonify(
        {
            "status": "processing",
            "step": 1,
            "message": _obtener_descripcion_estado(video.estado),
        }
    )


@socio_bp.route("/video/<video_id>/stream_status", methods=["GET"])
@api_socio_requerido
@limiter.exempt
def stream_video_status(video_id):
    """
    Server-Sent Events (SSE) endpoint para estado en tiempo real sin polling.
    """
    # Verificar ownership antes de iniciar el stream (prevenir IDOR)
    _check_video = get_video_repository().obtener_por_id(video_id)
    if not _check_video:
        return jsonify({"status": "error", "message": "Video no encontrado"}), 404
    if _check_video.usuario != session.get("username"):
        return jsonify({"status": "error", "message": "Acceso denegado"}), 403

    def generate():
        import time
        from domain.entities import EstadoVideo
        
        while True:
            # Re-obtener video de la BD cada ciclo (o eventualmente escuchar Firestore onSnapshot en backend)
            video = get_video_repository().obtener_por_id(video_id)
            if not video:
                yield "data: {\"status\": \"error\", \"message\": \"Video no encontrado\"}\n\n"
                break
            
            estado = video.estado
            payload = {}

            if estado in [EstadoVideo.COMPLETADO, EstadoVideo.APROBADO, EstadoVideo.RECHAZADO]:
                payload = {
                    "status": "completed",
                    "step": 8,
                    "finalStatus": "approved" if video.metadatos_ia.get("resultado_ia") == "APROBADO" else "rejected",
                }
                yield f"data: {json.dumps(payload)}\n\n"
                break  # Termina la conexión SSE si ya acabó
                
            elif estado == EstadoVideo.ERROR:
                payload = {
                    "status": "error",
                    "message": video.metadatos_ia.get("error_procesamiento", "Error"),
                }
                yield f"data: {json.dumps(payload)}\n\n"
                break
                
            else:
                progreso = video.metadatos_ia.get("progreso", {})
                if progreso:
                    payload = progreso
                else:
                    payload = {
                        "status": "pending" if estado == EstadoVideo.PENDIENTE else "processing",
                        "message": _obtener_descripcion_estado(estado)
                    }
                yield f"data: {json.dumps(payload)}\n\n"
            
            # Streaming check interval (en producción escalar con Redis PubSub)
            time.sleep(2)
            
    return Response(generate(), mimetype="text/event-stream")


@socio_bp.route("/video/<video_id>/details", methods=["GET", "OPTIONS"])
@api_socio_requerido
@limiter.limit(VIDEO_DETAILS_LIMIT)
def get_video_details(video_id):
    """
    Endpoint para obtener TODOS los detalles del video (para modal).
    Refactorizado usando SocioVideoService.
    """
    if request.method == "OPTIONS":
        return "", 200

    try:
        usuario_actual = session.get("username")
        service = SocioVideoService()
        video_data = service.get_formatted_video_details(video_id, usuario_actual)
        return jsonify({"success": True, "video": video_data}), 200
    except ValueError as e:
        return jsonify({"success": False, "error": "Recurso no encontrado"}), 404
    except PermissionError as e:
        return jsonify({"success": False, "error": "Acceso denegado"}), 403
    except ReglaNegocioException as e:
        return jsonify({"success": False, "error": e.mensaje}), 423
    except Exception as e:
        current_app.logger.error(f"Error getting video details: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500

def cargar_configuracion():
    """Carga la configuración desde blacklist.json"""
    config_path = Path(__file__).parent.parent.parent / "config" / "blacklist.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            return config.get("configuracion", {})
    except (FileNotFoundError, json.JSONDecodeError):
        # Valores por defecto si no se puede cargar
        return {
            "duracion_maxima_segundos": 60,
            "tamano_maximo_mb": 100,
            "formatos_permitidos": ["mp4", "avi", "mov", "mkv", "webm"],
        }


# Cargar configuración al inicio
_CONFIG = cargar_configuracion()

# Extensiones permitidas (desde configuración)
EXTENSIONES_PERMITIDAS = set(
    _CONFIG.get("formatos_permitidos", ["mp4", "avi", "mov", "mkv", "webm"])
)

# MIME types permitidos para videos (magic numbers)
MIME_TYPES_PERMITIDOS = {
    "video/mp4",
    "video/x-msvideo",  # AVI
    "video/quicktime",  # MOV
    "video/x-matroska",  # MKV
    "video/webm",
    "video/x-flv",
    "video/x-ms-wmv",
}

# Tamaño máximo en bytes
TAMANO_MAXIMO_BYTES = _CONFIG.get("tamano_maximo_mb", 100) * 1024 * 1024
MAX_VIDEOS_ANALIZANDO = 5


def _count_videos_analizando(usuario: str) -> int:
    """Cuenta videos activos en análisis para un usuario."""
    videos_usuario = get_video_repository().obtener_por_usuario(usuario)
    estados_activos = {EstadoVideo.PENDIENTE, EstadoVideo.PROCESANDO, EstadoVideo.EN_REVISION}
    return sum(1 for v in videos_usuario if v.estado in estados_activos)


def extensiones_permitidas(filename):
    """Verifica si el archivo tiene una extensión permitida"""
    return (
        "." in filename and filename.rsplit(".", 1)[1].lower() in EXTENSIONES_PERMITIDAS
    )


def validar_mime_type(archivo) -> tuple[bool, str]:
    """
    Valida el MIME type real del archivo usando magic numbers

    Args:
        archivo: Objeto FileStorage de Flask

    Returns:
        tuple: (es_valido: bool, mensaje: str)
    """
    try:
        import magic

        # Leer los primeros bytes para detectar el tipo
        header = archivo.read(2048)
        archivo.seek(0)  # Volver al inicio

        # Detectar MIME type real
        mime = magic.Magic(mime=True)
        detected_mime = mime.from_buffer(header)

        if detected_mime not in MIME_TYPES_PERMITIDOS:
            return False, f"Tipo de archivo no permitido. Detectado: {detected_mime}"

        return True, f"MIME type válido: {detected_mime}"

    except ImportError:
        # Fallback: validar por extensión si python-magic no está disponible
        import logging
        logging.getLogger(__name__).warning("python-magic no disponible, validando solo por extensión")
        return True, "Validación MIME omitida (python-magic no disponible) - validado por extensión"
    except Exception as e:
        # En caso de error, rechazar por seguridad
        return False, f"Error validando MIME type: archivo rechazado por seguridad"


def validar_tamano_archivo(archivo) -> tuple[bool, str]:
    """
    Valida el tamaño del archivo

    Returns:
        tuple: (es_valido: bool, mensaje: str)
    """
    # Obtener tamaño del archivo
    archivo.seek(0, os.SEEK_END)
    tamano = archivo.tell()
    archivo.seek(0)  # Volver al inicio para poder guardarlo después

    tamano_mb = tamano / (1024 * 1024)
    max_mb = _CONFIG.get("tamano_maximo_mb", 100)

    if tamano > TAMANO_MAXIMO_BYTES:
        return (
            False,
            f"El archivo excede el tamaño máximo permitido ({tamano_mb:.1f}MB > {max_mb}MB)",
        )

    return True, f"Tamaño válido: {tamano_mb:.1f}MB"


def obtener_estado_video(video_id: str) -> dict:
    """
    Obtiene el estado de un video por su ID

    Args:
        video_id: ID del video

    Returns:
        dict: Información del estado del video
    """
    video = get_video_repository().obtener_por_id(video_id)
    if not video:
        return None

    return {
        "id": video.id,
        "estado": video.estado.value,
        "descripcion_estado": _obtener_descripcion_estado(video.estado),
        "fecha_carga": video.metadatos_ia.get("fecha_procesamiento"),
        "resultado_ia": video.metadatos_ia.get("resultado_ia"),
        "razon_rechazo": video.metadatos_ia.get("razon_rechazo"),
    }


def _obtener_descripcion_estado(estado: EstadoVideo) -> str:
    """Retorna una descripción amigable del estado"""
    descripciones = {
        EstadoVideo.PENDIENTE: "Tu video está pendiente de procesamiento",
        EstadoVideo.PROCESANDO: "Tu video se está procesando",
        EstadoVideo.COMPLETADO: "¡Tu video ha sido aprobado!",
        EstadoVideo.ERROR: "Tu video fue rechazado por no cumplir con los estándares",
        EstadoVideo.EN_REVISION: "Tu video está siendo revisado manualmente por nuestro equipo",
        EstadoVideo.APROBADO: "¡Tu video ha sido aprobado definitivamente!",
        EstadoVideo.RECHAZADO: "Tu video ha sido rechazado tras la revisión",
    }
    return descripciones.get(estado, "Estado desconocido")


@socio_bp.route("/")
@socio_requerido
def index():
    """
    Página principal de carga de videos

    Retorna:
    - JSON si es request con Accept: application/json (React)
    - HTML si es request normal (SSR fallback)
    """
    usuario_actual = session.get("nombre_completo", session.get("username", "Usuario"))
    usuario_id = session.get("usuario_id")

    # Si es JSON request (desde React)
    if request.headers.get("Accept") == "application/json" or request.is_json:
        # Obtener videos del usuario
        todos_videos = get_video_repository().obtener_todos()
        videos_usuario = [
            v
            for v in todos_videos
            if v.usuario.lower() == session.get("username", "").lower()
        ]

        # Obtener servicio de thumbnails
        from infrastructure.services.thumbnail_service import get_thumbnail_service

        thumbnail_service = get_thumbnail_service()

        videos_response = []
        for v in videos_usuario:
            thumb_url = thumbnail_service.get_thumbnail_url(v.id)

            # Si no hay thumbnail y ya fue procesado, intentar generarlo (fallback)
            # Esto es útil para videos antiguos
            if not thumb_url and v.estado in [
                EstadoVideo.COMPLETADO,
                EstadoVideo.APROBADO,
            ]:
                # No bloqueamos, solo logueamos
                pass

            videos_response.append(
                {
                    "id": v.id,
                    "descripcion": v.descripcion,
                    "titulo": v.metadatos_ia.get("titulo", v.descripcion)
                    if v.metadatos_ia
                    else v.descripcion,
                    "estado": v.estado.value,
                    "resultado_ia": v.metadatos_ia.get("resultado_ia")
                    if v.metadatos_ia
                    else None,
                    "fecha_procesamiento": v.metadatos_ia.get("fecha_procesamiento")
                    if v.metadatos_ia
                    else None,
                    "thumbnail_url": thumb_url,
                }
            )

        return jsonify(
            {
                "success": True,
                "usuario": {
                    "nombre": usuario_actual,
                    "username": session.get("username"),
                    "id": usuario_id,
                },
                "videos": videos_response,
            }
        ), 200

    # Si es request HTML (SSR fallback)
    return render_template("upload.html", usuario=usuario_actual)


@socio_bp.route("/upload", methods=["POST", "OPTIONS"])
@api_socio_requerido
@limiter.limit(UPLOAD_LIMIT, exempt_when=lambda: request.method == "OPTIONS")
def upload_video():
    """
    Endpoint para subir UN video (Fase 1)

    Form Data:
        - video: Archivo de video

    Returns:
        JSON con video_id para iniciar procesamiento
    """
    # Manejar preflight OPTIONS
    if request.method == "OPTIONS":
        return "", 200
    
    try:
        # 1. Validar que se envió un archivo
        if "video" not in request.files:
            return jsonify(
                {"success": False, "error": "No se envió ningún archivo"}
            ), 400

        archivo = request.files["video"]

        # Validar que se seleccionó un archivo
        if archivo.filename == "":
            return jsonify(
                {"success": False, "error": "No se seleccionó ningún archivo"}
            ), 400

        # Validar extensión
        if not extensiones_permitidas(archivo.filename):
            return jsonify(
                {
                    "success": False,
                    "error": f"Formato no permitido. Extensiones válidas: {', '.join(EXTENSIONES_PERMITIDAS)}",
                }
            ), 400

        # Validar MIME type
        mime_valido, mensaje_mime = validar_mime_type(archivo)
        if not mime_valido:
            return jsonify({"success": False, "error": mensaje_mime}), 400

        # Validar tamaño
        tamano_valido, mensaje_tamano = validar_tamano_archivo(archivo)
        if not tamano_valido:
            return jsonify({"success": False, "error": mensaje_tamano}), 400

        # 2. Datos usuario
        usuario = session.get("username", "desconocido")

        videos_analizando = _count_videos_analizando(usuario)
        if videos_analizando >= MAX_VIDEOS_ANALIZANDO:
            return jsonify({
                "success": False,
                "error": "Ya tiene 5 videos analizando, espere que concluyan para enviar más",
            }), 429
        
        # 3. Obtener workspace_id (default: general)
        workspace_id = request.form.get("workspace_id", "general")
        print(f"📤 Upload: workspace_id recibido = '{workspace_id}'")
        
        # Si es "general", obtener o crear workspace General
        if workspace_id == "general":
            from infrastructure.repositories.workspace_repository import WorkspaceRepositoryFirestore
            from use_cases.socio_video_service import SocioVideoService
            workspace_repo = WorkspaceRepositoryFirestore()
            workspace_general = workspace_repo.obtener_workspace_general(usuario)
            workspace_id = workspace_general.id
            print(f"📤 Upload: workspace_id (general) resuelto a = '{workspace_id}'")

        # 4. Guardar archivo en disco
        from pathlib import Path as FilePath

        filename = secure_filename(archivo.filename)
        video_id = str(uuid.uuid4())

        # Validación segura de extensión
        file_path = FilePath(filename)
        extension = file_path.suffix.lower()
        if not extension or extension == ".":
            return jsonify({"error": "Archivo sin extensión válida"}), 400
        extension = extension[1:]
        nuevo_filename = f"{video_id}.{extension}"

        # Crear directorio
        upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
        upload_dir.mkdir(parents=True, exist_ok=True)

        ruta_archivo = upload_dir / nuevo_filename
        archivo.save(str(ruta_archivo))

        # 5. Crear entidad Video con workspace_id
        from datetime import datetime
        titulo_video = Path(filename).stem
        video = Video(
            id=video_id,
            usuario=usuario,
            ruta_archivo=str(ruta_archivo),
            descripcion=titulo_video,
            metadatos_ia={"nombre_archivo": filename, "titulo": titulo_video},
            estado=EstadoVideo.PENDIENTE,
            nombre_archivo=filename,
            workspace_id=workspace_id,
            fecha_creacion=datetime.utcnow().isoformat(),
        )

        # Guardar en repositorio
        get_video_repository().guardar(video)

        # Actualizar estadísticas del workspace por evento
        recalculate_workspace_stats(workspace_id, touch_activity=True)

        return jsonify(
            {
                "success": True,
                "message": "Video subido correctamente. Listo para procesar.",
                "video_id": video.id,
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error al subir video: {str(e)}")
        return jsonify(
            {"success": False, "error": "Error interno al subir el video"}
        ), 500


@socio_bp.route("/video/<video_id>/start_processing", methods=["POST", "OPTIONS"])
@api_socio_requerido
def start_processing(video_id):
    """
    Endpoint para INICIAR el procesamiento en segundo plano.
    El progreso se guardará en BD y consultará por polling.
    """
    video_repo = get_video_repository()
    video = video_repo.obtener_por_id(video_id)

    if not video:
        return jsonify({"error": "Video no encontrado"}), 404

    # Verificar que el video pertenezca al usuario actual (seguridad)
    usuario_actual = session.get("username")
    if video.usuario != usuario_actual:
        return jsonify({"error": "No autorizado"}), 403

    # Intentar encolar en RQ (escalable), fallback a thread local
    queue_required = False
    try:
        from infrastructure.services.job_queue import enqueue_socio_video, is_queue_required

        queue_required = is_queue_required()

        job_id = enqueue_socio_video(video_id=video_id, priority=0)
        if job_id:
            current_app.logger.info(f"Video {video_id} encolado en RQ job={job_id}")
            return jsonify({"success": True, "message": "Procesamiento en cola", "job_id": job_id}), 202
        if queue_required:
            return jsonify({
                "success": False,
                "error": "La cola de procesamiento no está disponible. Intenta nuevamente en unos minutos.",
            }), 503
    except Exception as queue_err:
        current_app.logger.warning(f"No se pudo encolar video {video_id} en RQ: {queue_err}")
        if queue_required:
            return jsonify({
                "success": False,
                "error": "La cola de procesamiento no está disponible. Intenta nuevamente en unos minutos.",
            }), 503

    # Capturar la app real para pasarla al thread (fallback)
    app = current_app._get_current_object()

    # Función de tarea en segundo plano
    def process_video_task(vid_id, username, app_context):
        # Necesitamos un contexto de aplicacion para acceder a dependencias
        with app_context.app_context():
            app_context.logger.info(
                f"--- STARTING BACKGROUND PROCESSING FOR {vid_id} ---"
            )
            try:
                # Resetear token de cancelación por si acaso
                _CANCELLATION_TOKENS[vid_id] = False

                # Callback para verificar cancelación
                def check_cancel_callback():
                    if _CANCELLATION_TOKENS.get(vid_id, False):
                        raise Exception("CANCELLED_BY_USER")

                # Re-obtener video para asegurar estado fresco
                v_repo = get_video_repository()
                vid = v_repo.obtener_por_id(vid_id)
                procesador = get_video_processor()
                blacklist_path = app_context.config["BLACKLIST_PATH"]

                # Limpiar cualquier progreso previo (5 pasos v4.0)
                vid.agregar_metadatos(
                    "progreso",
                    {
                        "step": 0,
                        "total_steps": 5,
                        "message": "Iniciando...",
                        "status": "pending",
                    },
                )
                v_repo.guardar(vid)

                progress_state = {"last_step": None, "last_status": None}

                def progress_callback(step, total, msg, status, details=None):
                    # Verificar cancelación
                    check_cancel_callback()

                    # Evitar escrituras redundantes en Firestore
                    if (
                        progress_state["last_step"] == step
                        and progress_state["last_status"] == status
                    ):
                        return
                    progress_state["last_step"] = step
                    progress_state["last_status"] = status

                    # Guardar progreso en BD (metadata)
                    # NOTA: En un sistema real de altísima concurrencia esto podría ser pesado,
                    # pero para 7 pasos por video es perfectamente escalable en Firestore.
                    vid_snap = v_repo.obtener_por_id(vid_id)  # Refrescar
                    vid_snap.agregar_metadatos(
                        "progreso",
                        {
                            "status": "processing",
                            "step": step,
                            "total_steps": total,
                            "message": msg,
                            "stepStatus": status,
                            "details": details,
                        },
                    )
                    v_repo.guardar(vid_snap)

                # Resetear estado si es necesario para permitir re-procesamiento
                if vid.estado not in [EstadoVideo.PENDIENTE, EstadoVideo.ERROR]:
                    vid.estado = EstadoVideo.PENDIENTE
                    v_repo.guardar(vid)

                # Ejecutar con soporte de cancelación
                video_procesado = procesador.ejecutar(
                    vid,
                    blacklist_path,
                    progress_callback=progress_callback,
                    check_cancel=check_cancel_callback,
                )

                # Finalizado
                # No necesitamos emitir socket, el estado COMPLETADO en la entidad es suficiente
                # para que el polling detecte el final.

                # Opcional: limpiar metadatos de progreso ahora que terminó
                # video_procesado.metadatos_ia.pop("progreso", None)
                # Pero mejor dejarlo para debugeo si se quiere.
                v_repo.guardar(video_procesado)

            except Exception as e:
                # Usar app_context.logger en lugar de current_app
                error_msg = "Error durante el procesamiento del video"

                # Re-obtener video para guardar error
                try:
                    vf = v_repo.obtener_por_id(vid_id)
                except Exception as e:
                    logger.warning(f"Could not re-fetch video {vid_id}: {e}")
                    vf = vid  # fallback

                # Manejo especial de cancelación
                if "CANCELLED_BY_USER" in error_msg:
                    friendly_msg = "Procesamiento cancelado por el usuario"
                    app_context.logger.info(f"Video {vid_id} cancelado correctamente.")

                    try:
                        vf.estado = EstadoVideo.ERROR
                        vf.agregar_metadatos(
                            "error_procesamiento", "Cancelado por el usuario"
                        )
                        vf.agregar_metadatos("razon_rechazo", "Cancelado manualmente")
                        v_repo.guardar(vf)
                    except Exception as e:
                        logger.warning(f"Could not save cancelled video state: {e}")
                    return

                app_context.logger.error(
                    f"Error processing video {vid_id}: {error_msg}"
                )

                # Mensaje amigable para errores de facturación GCP
                if (
                    "billing account" in error_msg.lower()
                    and "disabled" in error_msg.lower()
                ):
                    friendly_msg = "Error de sistema: La cuenta de facturación de Google Cloud está desactivada. Contacte al administrador."
                else:
                    friendly_msg = error_msg

                # Persistir estado de ERROR en la BD
                try:
                    vf.estado = EstadoVideo.ERROR
                    vf.agregar_metadatos("error_procesamiento", friendly_msg)
                    vf.agregar_metadatos(
                        "razon_rechazo", f"Error de sistema: {friendly_msg}"
                    )
                    v_repo.guardar(vf)
                except Exception as db_err:
                    app_context.logger.error(
                        f"Error saving error state for video {vid_id}: {db_err}"
                    )

            finally:
                # Limpiar token
                if vid_id in _CANCELLATION_TOKENS:
                    del _CANCELLATION_TOKENS[vid_id]

    # Iniciar tarea en background (usando Threading estandar para evitar dependencias de socketio context)
    import threading

    thread = threading.Thread(
        target=process_video_task, args=(video_id, usuario_actual, app)
    )
    thread.daemon = True  # Para que no bloquee el shutdown
    thread.start()

    # Log inmediato para confirmar que pasamos por aqui
    current_app.logger.info(f"Background thread started for video {video_id}")

    return jsonify({"success": True, "message": "Procesamiento iniciado"}), 202


@socio_bp.route("/video/<video_id>/clarify", methods=["POST", "OPTIONS"])
@api_socio_requerido
def submit_clarification(video_id):
    """
    Endpoint para enviar respuestas a preguntas de clarificación de la IA.
    
    JSON Body:
        - answers: Dict con respuestas {question_id: answer_text}
    
    Returns:
        JSON indicando que las respuestas fueron guardadas y el procesamiento continuará
    """
    try:
        video_repo = get_video_repository()
        video = video_repo.obtener_por_id(video_id)
        
        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404
        
        # Verificar que el video pertenezca al usuario actual
        usuario_actual = session.get("username")
        if video.usuario != usuario_actual:
            return jsonify({"success": False, "error": "No autorizado"}), 403
        
        # Obtener respuestas del body
        data = request.get_json() or {}
        answers = data.get("answers", {})
        
        if not answers:
            return jsonify({"success": False, "error": "No se proporcionaron respuestas"}), 400
        
        # Guardar respuestas en metadatos
        video.agregar_metadatos("clarification_answers", answers)
        video.agregar_metadatos("clarification_pending", False)
        
        # Combinar contexto original con las respuestas
        contexto_original = video.contexto_usuario or ""
        respuestas_text = " | ".join([f"{k}: {v}" for k, v in answers.items()])
        contexto_completo = f"{contexto_original} [Clarificación del usuario: {respuestas_text}]"
        video.contexto_usuario = contexto_completo[:1000]  # Límite extendido para incluir clarificaciones
        
        video_repo.guardar(video)
        
        current_app.logger.info(f"Clarification received for video {video_id}: {answers}")
        
        return jsonify({
            "success": True,
            "message": "Respuestas guardadas. El procesamiento continuará.",
            "video_id": video_id
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error al guardar clarificación: {str(e)}")
        return jsonify({"success": False, "error": "Error interno"}), 500


@socio_bp.route("/batch-upload", methods=["POST", "OPTIONS"])
@limiter.limit(UPLOAD_LIMIT)
@api_socio_requerido
def batch_upload_videos():
    """
    Endpoint para subir MÚLTIPLES videos con procesamiento via RQ.
    Sube todos los archivos, los encola en Redis/RQ para procesamiento paralelo.

    Form Data:
        - videos: Lista de archivos de video
        - workspace_id: ID del workspace (optional, default: 'general')

    Returns:
        JSON con batch_id y lista de video_ids para tracking
    """
    if request.method == "OPTIONS":
        return "", 200

    try:
        if "videos" not in request.files:
            return jsonify({"success": False, "error": "No se enviaron archivos"}), 400

        archivos = request.files.getlist("videos")
        if not archivos or len(archivos) == 0:
            return jsonify({"success": False, "error": "No se seleccionaron archivos"}), 400

        MAX_VIDEOS = 5
        if len(archivos) > MAX_VIDEOS:
            return jsonify({
                "success": False,
                "error": "Ya tiene 5 videos analizando, espere que concluyan para enviar más",
            }), 400

        usuario = session.get("username", "desconocido")

        videos_analizando = _count_videos_analizando(usuario)
        if videos_analizando >= MAX_VIDEOS_ANALIZANDO or (videos_analizando + len(archivos)) > MAX_VIDEOS_ANALIZANDO:
            return jsonify({
                "success": False,
                "error": "Ya tiene 5 videos analizando, espere que concluyan para enviar más",
            }), 429

        workspace_id = request.form.get("workspace_id", "general")

        # Resolver workspace general
        if workspace_id == "general":
            workspace_repo = WorkspaceRepositoryFirestore()
            workspace_general = workspace_repo.obtener_workspace_general(usuario)
            workspace_id = workspace_general.id

        batch_id = str(uuid.uuid4())
        upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
        upload_dir.mkdir(parents=True, exist_ok=True)

        videos_info = []
        errores_upload = []

        for archivo in archivos:
            try:
                if archivo.filename == "":
                    errores_upload.append({"nombre": "sin_nombre", "error": "Archivo sin nombre"})
                    continue
                if not extensiones_permitidas(archivo.filename):
                    errores_upload.append({"nombre": archivo.filename, "error": "Formato no permitido"})
                    continue
                tamano_valido, msg = validar_tamano_archivo(archivo)
                if not tamano_valido:
                    errores_upload.append({"nombre": archivo.filename, "error": msg})
                    continue

                filename = secure_filename(archivo.filename)
                video_id = str(uuid.uuid4())
                from pathlib import Path as FilePath
                file_path = FilePath(filename)
                extension = file_path.suffix.lower()
                if not extension or extension == ".":
                    errores_upload.append({"nombre": archivo.filename, "error": "Sin extensión"})
                    continue
                extension = extension[1:]
                nuevo_filename = f"{video_id}.{extension}"
                ruta_archivo = upload_dir / nuevo_filename
                archivo.save(str(ruta_archivo))

                # Calcular tamaño para priorización
                tamano_bytes = os.path.getsize(str(ruta_archivo))

                from datetime import datetime
                titulo_video = Path(filename).stem
                video = Video(
                    id=video_id,
                    usuario=usuario,
                    ruta_archivo=str(ruta_archivo),
                    descripcion=titulo_video,
                    metadatos_ia={
                        "nombre_archivo": filename,
                        "titulo": titulo_video,
                        "batch_id": batch_id,
                        "batch_total": len(archivos),
                        "tamanio_bytes": tamano_bytes,
                    },
                    estado=EstadoVideo.PENDIENTE,
                    nombre_archivo=filename,
                    workspace_id=workspace_id,
                    fecha_creacion=datetime.utcnow().isoformat(),
                )
                get_video_repository().guardar(video)

                videos_info.append({
                    "video_id": video_id,
                    "nombre": filename,
                    "tamano_bytes": tamano_bytes,
                })

            except Exception as e:
                errores_upload.append({"nombre": getattr(archivo, 'filename', '?'), "error": "Error al procesar archivo"})

        if not videos_info:
            return jsonify({"success": False, "error": "Ningún video pudo ser subido", "errores": errores_upload}), 400

        # Actualizar estadísticas del workspace una sola vez por lote
        recalculate_workspace_stats(workspace_id, touch_activity=True)

        # Encolar procesamiento en RQ (priorización: videos más pequeños primero)
        videos_ordenados = sorted(videos_info, key=lambda v: v["tamano_bytes"])
        enqueue_errors = []

        from infrastructure.services.job_queue import enqueue_socio_video, is_queue_required
        queue_required = is_queue_required()
        for idx, info in enumerate(videos_ordenados):
            try:
                job_id = enqueue_socio_video(
                    video_id=info["video_id"],
                    priority=idx,  # 0 = más prioritario (más pequeño)
                )
                if not job_id:
                    raise RuntimeError("No se pudo encolar job")
            except Exception as e:
                current_app.logger.warning(f"Error encolando {info['video_id']}: {e}")
                if queue_required:
                    enqueue_errors.append({
                        "video_id": info["video_id"],
                        "error": "Cola no disponible",
                    })
                else:
                    # Fallback en entornos no productivos
                    _procesar_video_thread(info["video_id"], usuario, current_app._get_current_object())

        if queue_required and enqueue_errors:
            return jsonify({
                "success": False,
                "error": "No se pudieron encolar todos los videos. La cola de procesamiento no está disponible.",
                "batch_id": batch_id,
                "enqueue_errors": enqueue_errors,
            }), 503

        # Guardar info del batch en Redis para tracking
        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            r = redis.Redis.from_url(redis_url)
            batch_data = json.dumps({
                "batch_id": batch_id,
                "video_ids": [v["video_id"] for v in videos_info],
                "total": len(videos_info),
                "usuario": usuario,
                "workspace_id": workspace_id,
            })
            r.setex(f"batch:{batch_id}", 86400, batch_data)  # 24h TTL
        except Exception as e:
            current_app.logger.warning(f"No se pudo guardar batch en Redis: {e}")

        return jsonify({
            "success": True,
            "batch_id": batch_id,
            "message": f"{len(videos_info)} videos en cola de procesamiento",
            "videos": videos_info,
            "errores_upload": errores_upload,
        }), 202

    except Exception as e:
        current_app.logger.error(f"Error en batch upload: {str(e)}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@socio_bp.route("/batch/<batch_id>/status", methods=["GET", "OPTIONS"])
@api_socio_requerido
@limiter.limit(POLLING_LIMIT)
def get_batch_status(batch_id):
    """
    Endpoint para consultar el estado de un batch de videos.
    Devuelve estado consolidado de todos los videos del batch.
    """
    try:
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.Redis.from_url(redis_url)
        batch_raw = r.get(f"batch:{batch_id}")

        if not batch_raw:
            return jsonify({"success": False, "error": "Batch no encontrado"}), 404

        batch_data = json.loads(batch_raw)
        video_ids = batch_data.get("video_ids", [])
        video_repo = get_video_repository()

        videos_status = []
        completados = 0
        errores = 0
        procesando = 0
        pendientes = 0

        for vid_id in video_ids:
            video = video_repo.obtener_por_id(vid_id)
            if not video:
                videos_status.append({"video_id": vid_id, "status": "not_found"})
                errores += 1
                continue

            estado = video.estado
            status_info = {
                "video_id": vid_id,
                "nombre": video.metadatos_ia.get("nombre_archivo", "?"),
                "status": estado.value,
            }

            if estado in [EstadoVideo.COMPLETADO, EstadoVideo.APROBADO, EstadoVideo.RECHAZADO]:
                completados += 1
                status_info["resultado"] = video.metadatos_ia.get("resultado_ia")
                status_info["titulo"] = video.metadatos_ia.get("titulo", video.descripcion)
                status_info["confianza"] = video.metadatos_ia.get("confianza_ia", 0)
            elif estado == EstadoVideo.ERROR:
                errores += 1
                status_info["error"] = video.metadatos_ia.get("error_procesamiento", "Error")
            elif estado == EstadoVideo.PROCESANDO:
                procesando += 1
                progreso = video.metadatos_ia.get("progreso", {})
                status_info["step"] = progreso.get("step", 0)
                status_info["total_steps"] = 5
                status_info["message"] = progreso.get("message", "Procesando...")
            else:
                pendientes += 1

            videos_status.append(status_info)

        total = len(video_ids)
        all_done = (completados + errores) >= total

        return jsonify({
            "success": True,
            "batch_id": batch_id,
            "status": "completed" if all_done else "processing",
            "resumen": {
                "total": total,
                "completados": completados,
                "errores": errores,
                "procesando": procesando,
                "pendientes": pendientes,
                "progreso_pct": round((completados + errores) / total * 100) if total > 0 else 0,
            },
            "videos": videos_status,
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error en batch status: {str(e)}")
        return jsonify({"success": False, "error": "Error consultando estado"}), 500


def _procesar_video_thread(video_id, usuario, app):
    """Fallback: procesar video en thread si RQ no está disponible"""
    import threading

    def task():
        with app.app_context():
            try:
                v_repo = get_video_repository()
                vid = v_repo.obtener_por_id(video_id)
                procesador = get_video_processor()
                blacklist_path = app.config["BLACKLIST_PATH"]

                vid.agregar_metadatos("progreso", {
                    "step": 0, "total_steps": 5,
                    "message": "Iniciando...", "status": "pending",
                })
                v_repo.guardar(vid)

                progress_state = {"last_step": None, "last_status": None}

                def progress_callback(step, total, msg, status, details=None):
                    if (
                        progress_state["last_step"] == step
                        and progress_state["last_status"] == status
                    ):
                        return
                    progress_state["last_step"] = step
                    progress_state["last_status"] = status

                    vid_snap = v_repo.obtener_por_id(video_id)
                    vid_snap.agregar_metadatos("progreso", {
                        "status": "processing", "step": step,
                        "total_steps": total, "message": msg,
                        "stepStatus": status, "details": details,
                    })
                    v_repo.guardar(vid_snap)

                if vid.estado not in [EstadoVideo.PENDIENTE, EstadoVideo.ERROR]:
                    vid.estado = EstadoVideo.PENDIENTE
                    v_repo.guardar(vid)

                video_procesado = procesador.ejecutar(
                    vid, blacklist_path, progress_callback=progress_callback
                )
                v_repo.guardar(video_procesado)

            except Exception as e:
                app.logger.error(f"Error thread processing {video_id}: {e}")
                try:
                    vf = v_repo.obtener_por_id(video_id)
                    vf.estado = EstadoVideo.ERROR
                    vf.agregar_metadatos("error_procesamiento", "Error durante el procesamiento")
                    v_repo.guardar(vf)
                except Exception as e:
                    logger.error(f"Could not save error state for video {video_id}: {e}")

    t = threading.Thread(target=task)
    t.daemon = True
    t.start()


@socio_bp.route("/upload-multiple", methods=["POST"])
@limiter.limit(UPLOAD_LIMIT)
@api_socio_requerido
def upload_multiple_videos():
    """
    DEPRECATED: Usar /batch-upload en su lugar.
    Se mantiene por compatibilidad.
    Redirige internamente al nuevo endpoint batch.
    """
    return batch_upload_videos()


# ============================================
# ENDPOINT PARA ELIMINAR VIDEO
# ============================================


@socio_bp.route("/videos/<video_id>", methods=["DELETE", "OPTIONS"])
@api_socio_requerido
def eliminar_video(video_id: str):
    """
    Permite al socio eliminar uno de sus videos

    Args:
        video_id: ID del video a eliminar

    Returns:
        JSON con resultado de la operación
    """
    # Manejar preflight CORS
    if request.method == "OPTIONS":
        return jsonify({"success": True}), 200
    
    # Verificar autenticación
    usuario_actual = session.get("username")
    if not usuario_actual:
        return jsonify({"success": False, "error": "No autenticado"}), 401

    try:
        # Obtener el video
        video_repository = get_video_repository()
        video = video_repository.obtener_por_id(video_id)

        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        # Verificar que el video pertenece al usuario
        if video.usuario != usuario_actual:
            return jsonify(
                {
                    "success": False,
                    "error": "No tienes permiso para eliminar este video",
                }
            ), 403

        # Eliminar de Cloud Storage si existe
        storage = get_storage_adapter()
        if storage and storage.is_available():
            try:
                # Obtener extensión del nombre de archivo
                extension = "mp4"
                if video.nombre_archivo:
                    ext = Path(video.nombre_archivo).suffix.lower()
                    if ext:
                        extension = ext[1:]  # Quitar el punto

                storage.delete_video(video_id, extension)
                current_app.logger.info(f"Video eliminado de GCS: {video_id}")
            except Exception as e:
                current_app.logger.warning(f"No se pudo eliminar de GCS: {e}")

        # Eliminar archivo local si existe
        if video.ruta_archivo:
            ruta_local = Path(video.ruta_archivo)
            if ruta_local.exists():
                ruta_local.unlink()
                current_app.logger.info(f"Archivo local eliminado: {ruta_local}")

        # Eliminar cache de análisis de Redis
        try:
            from infrastructure.services.video_cache import get_video_analysis_cache
            cache = get_video_analysis_cache()
            # Buscar el hash del video en los metadatos
            video_hash = None
            if hasattr(video, 'metadatos_ia') and video.metadatos_ia:
                video_hash = video.metadatos_ia.get('video_hash')
            if video_hash:
                cache.invalidate_by_video_hash(video_hash)
                current_app.logger.info(f"🗑️ Cache de análisis eliminado para video {video_id} (hash: {video_hash[:12]}...)")
            else:
                current_app.logger.info(f"ℹ️ Video {video_id} no tenía hash en metadatos, cache no afectado")
        except Exception as e:
            current_app.logger.warning(f"⚠️ No se pudo limpiar cache para video {video_id}: {e}")

        # Guardar workspace_id antes de eliminar
        workspace_id = getattr(video, 'workspace_id', None)
        
        # Eliminar del repositorio (Firestore)
        video_repository.eliminar(video_id)
        
        # Actualizar estadísticas del workspace si existe
        if workspace_id:
            recalculate_workspace_stats(workspace_id, touch_activity=True)

        current_app.logger.info(
            f"Video {video_id} eliminado por usuario {usuario_actual}"
        )

        return jsonify(
            {
                "success": True,
                "message": "Video eliminado correctamente",
                "video_id": video_id,
            }
        ), 200

    except Exception as e:
        current_app.logger.error(f"Error eliminando video {video_id}: {str(e)}")
        return jsonify({"success": False, "error": "Error al eliminar el video"}), 500


@socio_bp.route("/health", methods=["GET"])
def health_check():
    """Endpoint de health check para el microservicio"""
    return jsonify(
        {"status": "healthy", "service": "Microservicio de Carga - TIVIT Video"}
    ), 200


# ============================================
# ENDPOINTS DE NOTIFICACIÓN DE ESTADO AL SOCIO
# ============================================


@socio_bp.route("/video/<video_id>/estado", methods=["GET"])
@api_socio_requerido
def consultar_estado_video(video_id: str):
    """
    Permite al socio consultar el estado de su video

    Args:
        video_id: ID del video a consultar

    Returns:
        JSON con información del estado del video
    """
    estado_info = obtener_estado_video(video_id)

    if not estado_info:
        return jsonify({"success": False, "error": "Video no encontrado"}), 404

    return jsonify({"success": True, "video": estado_info}), 200


@socio_bp.route("/video/<video_id>/solicitar-revision", methods=["POST", "OPTIONS"])
@api_socio_requerido
def solicitar_revision_video(video_id: str):
    """
    Permite al socio solicitar revisión manual de su video

    Args:
        video_id: ID del video

    Request Body:
        motivo: Razón de la solicitud

    Returns:
        JSON con resultado de la operación
    """
    try:
        data = request.get_json() or {}
        motivo = data.get("motivo", "").strip()

        # Obtener usuario actual
        usuario_actual = session.get("username")

        # Obtener video
        video_repo = get_video_repository()
        video = video_repo.obtener_por_id(video_id)

        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        # Verificar propiedad
        if video.usuario != usuario_actual:
            return jsonify({"success": False, "error": "No autorizado"}), 403

        # Verificar si ya hay solicitud pendiente
        if video.metadatos_ia.get("solicitud_revision_manual"):
            return jsonify(
                {
                    "success": False,
                    "error": "Ya existe una solicitud de revisión pendiente para este video",
                }
            ), 400

        # Solicitar revisión (Entidad valida el estado)
        from datetime import datetime

        video.solicitar_revision_manual(motivo)

        # Actualizar fecha de solicitud aquí ya que la entidad la deja en None
        video.metadatos_ia["fecha_solicitud_revision"] = datetime.now().isoformat()

        # Guardar cambios
        video_repo.guardar(video)

        return jsonify(
            {
                "success": True,
                "message": "Solicitud de revisión enviada correctamente. Un administrador revisará tu video pronto.",
                "video": {"id": video.id, "estado": video.estado.value},
            }
        ), 200

    except ReglaNegocioException as e:
        return jsonify({"success": False, "error": "Error en la solicitud"}), 400
    except Exception as e:
        current_app.logger.error(f"Error solicitando revisión {video_id}: {str(e)}")
        return jsonify(
            {"success": False, "error": "Error interno al procesar la solicitud"}
        ), 500


@socio_bp.route("/mis-videos", methods=["GET", "OPTIONS"])
@api_socio_requerido
def listar_mis_videos():
    """
    Lista los videos del usuario.
    Refactorizado usando SocioVideoService.
    """
    if request.method == "OPTIONS":
        return "", 200
    
    usuario_sesion = session.get("username", "").strip()
    usuario_query = request.args.get("usuario", "").strip()
    usuario = usuario_query or usuario_sesion

    if not usuario:
        return jsonify({"success": False, "error": "Usuario no autenticado"}), 401

    if usuario_sesion and usuario.lower() != usuario_sesion.lower():
        return jsonify({"success": False, "error": "No autorizado para consultar este usuario"}), 403

    try:
        service = SocioVideoService()
        videos_response = service.format_user_videos_list(usuario)
        return jsonify({
            "success": True,
            "usuario": usuario,
            "cantidad": len(videos_response),
            "videos": videos_response,
        }), 200
    except Exception as e:
        current_app.logger.error(f"Error listing user videos: {e}")
        return jsonify({"success": False, "error": "Error interno"}), 500

@socio_bp.route("/estado-consulta")
@socio_requerido
def pagina_consulta_estado():
    """Página para que el socio consulte el estado de sus videos"""
    return render_template("estado_video.html")


@socio_bp.route("/preview/<video_id>")
@api_socio_requerido
def preview_video(video_id):
    """
    Obtiene la URL de previsualización del video
    Redirige a la URL firmada de Cloud Storage

    Args:
        video_id: ID del video

    Returns:
        Redirect a la URL del video o error
    """
    from flask import redirect, send_file
    from infrastructure.dependencies import get_storage_adapter

    video = get_video_repository().obtener_por_id(video_id)

    if not video:
        return jsonify({"success": False, "error": "Video no encontrado"}), 404

    # 1. Intentar usar URL firmada pre-generada si existe y es válida
    # (Nota: Por ahora regeneramos para asegurar validez, pero podríamos chequear expiración)

    # 2. Generar nueva URL firmada de Cloud Storage
    storage = get_storage_adapter()
    if storage and storage.is_available():
        gcs_uri = video.metadatos_ia.get("gcs_uri", "")
        if gcs_uri:
            import re

            # Parsear URI de GCS de forma segura: gs://bucket/path/to/blob
            # Esto corrige el error donde split('/')[-1] eliminaba el directorio padre (ej: videos/)
            match = re.match(r"gs://([^/]+)/(.+)", gcs_uri)

            if match:
                gcs_path = match.group(2)

                # Compatibilidad: verificar qué método tiene el adaptador
                # (El protocolo define get_signed_url pero la impl puede tener generate_signed_url)
                signed_url = None
                if hasattr(storage, "generate_signed_url"):
                    signed_url = storage.generate_signed_url(
                        gcs_path, expiration_minutes=60
                    )
                elif hasattr(storage, "get_signed_url"):
                    signed_url = storage.get_signed_url(gcs_path, expiration_minutes=60)

                if signed_url:
                    return redirect(signed_url)
            else:
                # Fallback para lógica antigua o formatos sin gs://
                current_app.logger.warning(f"Formato GCS URI no reconocido: {gcs_uri}")

    # 3. Fallback: servir desde archivo local
    # Primero intentar con la ruta exacta guardada en la entidad
    if video.ruta_archivo and Path(video.ruta_archivo).exists():
        return send_file(video.ruta_archivo)

    # Último recurso: intentar buscar por ID en la carpeta de uploads (legacy)
    local_path = (
        Path(current_app.config.get("UPLOAD_FOLDER", "uploads")) / f"{video_id}.mp4"
    )
    if local_path.exists():
        return send_file(local_path, mimetype="video/mp4")

    return jsonify(
        {"success": False, "error": "Video no disponible para previsualización"}
    ), 404


@socio_bp.route("/thumbnail/<video_id>")
@api_socio_requerido
def get_thumbnail(video_id):
    """
    Obtiene el thumbnail del video, generándolo si no existe
    Puede descargar desde GCS si el video no está disponible localmente

    Args:
        video_id: ID del video

    Returns:
        Imagen del thumbnail o placeholder
    """
    from flask import send_file
    from infrastructure.services.thumbnail_service import ThumbnailService
    from infrastructure.dependencies import get_storage_adapter
    import tempfile

    video = get_video_repository().obtener_por_id(video_id)

    if not video:
        return jsonify({"success": False, "error": "Video no encontrado"}), 404

    # Ruta del thumbnail esperada
    thumbnails_dir = Path(os.getenv("THUMBNAILS_DIR", "/app/thumbnails"))
    thumbnail_path = thumbnails_dir / f"{video_id}_thumb.jpg"

    # Si el thumbnail existe, devolverlo
    if thumbnail_path.exists():
        return send_file(str(thumbnail_path), mimetype="image/jpeg")

    # Intentar generar el thumbnail si el video local existe
    if video.ruta_archivo and Path(video.ruta_archivo).exists():
        try:
            thumbnail_service = ThumbnailService()
            generated_path = thumbnail_service.generate_thumbnail(
                video_path=video.ruta_archivo,
                video_id=video_id,
                timestamp=1.0,
                size=(320, 180),
            )

            if generated_path and Path(generated_path).exists():
                return send_file(str(generated_path), mimetype="image/jpeg")
        except Exception as e:
            current_app.logger.error(f"Error generando thumbnail para {video_id}: {e}")

    # Si el video no está local pero tiene GCS URI, descargar temporalmente
    gcs_uri = video.metadatos_ia.get("gcs_uri")
    if gcs_uri:
        try:
            current_app.logger.info(
                f"Descargando video desde GCS para generar thumbnail: {video_id}"
            )
            storage_adapter = get_storage_adapter()

            if storage_adapter and storage_adapter.is_available():
                # Crear archivo temporal
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".mp4"
                ) as temp_file:
                    temp_path = temp_file.name

                try:
                    # Extraer el path de GCS desde el URI
                    # gcs_uri format: gs://bucket-name/path/to/video.mp4
                    gcs_path = (
                        gcs_uri.replace("gs://", "").split("/", 1)[1]
                        if "gs://" in gcs_uri
                        else None
                    )

                    if gcs_path:
                        # Descargar desde GCS
                        from google.cloud import storage

                        bucket_name = os.getenv(
                            "GCS_BUCKET_NAME", "accessfan-videos-us-central1"
                        )
                        storage_client = storage.Client()
                        bucket = storage_client.bucket(bucket_name)
                        blob = bucket.blob(gcs_path)

                        # Descargar al archivo temporal
                        blob.download_to_filename(temp_path)

                        # Generar thumbnail
                        thumbnail_service = ThumbnailService()
                        generated_path = thumbnail_service.generate_thumbnail(
                            video_path=temp_path,
                            video_id=video_id,
                            timestamp=1.0,
                            size=(320, 180),
                        )

                        if generated_path and Path(generated_path).exists():
                            current_app.logger.info(
                                f"Thumbnail generado desde GCS: {video_id}"
                            )
                            return send_file(str(generated_path), mimetype="image/jpeg")

                finally:
                    # Limpiar archivo temporal
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

        except Exception as e:
            current_app.logger.error(
                f"Error descargando desde GCS para thumbnail {video_id}: {e}"
            )

    # Si todo falla, devolver placeholder SVG
    placeholder_svg = f"""
    <svg width="320" height="180" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style="stop-color:#1a1a2e;stop-opacity:1" />
          <stop offset="100%" style="stop-color:#16213e;stop-opacity:1" />
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#grad1)"/>
      <rect x="130" y="65" width="60" height="50" rx="8" fill="none" stroke="#ffffff" stroke-width="2" opacity="0.3"/>
      <circle cx="135" cy="75" r="3" fill="#ffffff" opacity="0.3"/>
      <polygon points="150,85 150,105 165,95" fill="#ffffff" opacity="0.3"/>
      <text x="160" y="150" font-family="Arial" font-size="11" fill="#666" text-anchor="middle">Sin preview</text>
    </svg>
    """
    from io import BytesIO

    return send_file(BytesIO(placeholder_svg.encode()), mimetype="image/svg+xml")


@socio_bp.route("/media/<video_id>")
@api_socio_requerido
def proxy_video(video_id):
    """
    Proxy de streaming para videos almacenados en GCS.
    Soporta HTTP Range requests para seeking en el player de video HTML5.
    No requiere Signed URLs — usa las credenciales ADC del servidor.
    """
    from flask import send_file
    from google.cloud import storage as gcs_lib

    video = get_video_repository().obtener_por_id(video_id)
    if not video:
        return jsonify({"success": False, "error": "Video no encontrado"}), 404

    # Verificar ownership (IDOR prevention)
    if video.usuario != session.get("username"):
        return jsonify({"success": False, "error": "Acceso denegado"}), 403

    # Intentar servir desde GCS
    gcs_uri = video.metadatos_ia.get("gcs_uri") if video.metadatos_ia else None
    if gcs_uri and "gs://" in gcs_uri:
        try:
            parts = gcs_uri.replace("gs://", "").split("/", 1)
            bucket_name = parts[0]
            blob_path = parts[1] if len(parts) > 1 else None

            if blob_path:
                storage_client = gcs_lib.Client()
                bucket = storage_client.bucket(bucket_name)
                blob = bucket.blob(blob_path)

                # Detectar Content-Type
                nombre = video.metadatos_ia.get("nombre_archivo", "video.mp4")
                ext = Path(nombre).suffix.lower().lstrip(".")
                mime_map = {
                    "mp4": "video/mp4", "mov": "video/quicktime",
                    "avi": "video/x-msvideo", "webm": "video/webm",
                    "mkv": "video/x-matroska",
                }
                content_type = mime_map.get(ext, "video/mp4")

                # Soporte Range requests
                range_header = request.headers.get("Range")
                blob_size = blob.size
                if blob_size is None:
                    blob.reload()
                    blob_size = blob.size or 0

                if range_header:
                    # Parsear "bytes=start-end"
                    range_match = range_header.replace("bytes=", "").split("-")
                    start = int(range_match[0]) if range_match[0] else 0
                    end = int(range_match[1]) if len(range_match) > 1 and range_match[1] else blob_size - 1
                    end = min(end, blob_size - 1)
                    length = end - start + 1

                    chunk = blob.download_as_bytes(start=start, end=end)

                    response = Response(
                        chunk,
                        status=206,
                        mimetype=content_type,
                        direct_passthrough=True,
                    )
                    response.headers["Content-Range"] = f"bytes {start}-{end}/{blob_size}"
                    response.headers["Accept-Ranges"] = "bytes"
                    response.headers["Content-Length"] = str(length)
                    response.headers["Cache-Control"] = "private, max-age=3600"
                    return response

                # Sin Range: streaming completo
                def generate():
                    chunk_size = 1024 * 1024  # 1 MB
                    offset = 0
                    while offset < blob_size:
                        end_byte = min(offset + chunk_size - 1, blob_size - 1)
                        chunk = blob.download_as_bytes(start=offset, end=end_byte)
                        yield chunk
                        offset += chunk_size

                response = Response(
                    generate(),
                    status=200,
                    mimetype=content_type,
                    direct_passthrough=True,
                )
                response.headers["Content-Length"] = str(blob_size)
                response.headers["Accept-Ranges"] = "bytes"
                response.headers["Cache-Control"] = "private, max-age=3600"
                return response

        except Exception as e:
            current_app.logger.warning(f"Error streaming video {video_id} desde GCS: {e}")

    # Fallback: archivo local
    ruta = video.ruta_archivo
    if ruta and Path(ruta).exists():
        return send_file(ruta, mimetype="video/mp4", conditional=True)

    upload_dir = Path(current_app.config.get("UPLOAD_FOLDER", "/app/uploads"))
    for ext in ("mp4", "mov", "avi", "webm", "mkv"):
        local = upload_dir / f"{video_id}.{ext}"
        if local.exists():
            return send_file(str(local), mimetype="video/mp4", conditional=True)

    return jsonify({"success": False, "error": "Video no disponible"}), 404
