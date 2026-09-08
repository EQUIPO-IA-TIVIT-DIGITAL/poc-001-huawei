"""
API Endpoints para Análisis de Videos de Seguridad
Maneja videos largos de cámaras de seguridad (12h+)

TRAZABILIDAD:
- Cada endpoint loguea inicio/fin con timestamps
- Errores se registran con stack trace completo
- El procesamiento tiene su propio logger especializado
"""

from flask import Blueprint, request, jsonify, session
import logging
from datetime import datetime
import uuid
import traceback
import time
import os
import hmac
import re

from infrastructure.repositories.security_video_repository import SecurityVideoRepository
from infrastructure.services.resumable_upload_service import ResumableUploadService
from infrastructure.services.multipart_upload_service import MultipartUploadService
from infrastructure.services.security_logger import get_security_logger
from infrastructure.web.auth_decorators import api_socio_requerido
from infrastructure.rate_limiter import limiter, UPLOAD_LIMIT, API_LIMIT
from domain.entities import SecurityVideo, EstadoSecurityVideo

logger = logging.getLogger(__name__)
sec_logger = get_security_logger()


def _is_admin_session() -> bool:
    """Compat: rol SOCIO único — admin eliminado, siempre False."""
    return False

# Blueprint para la sección de seguridad
app_security = Blueprint("security", __name__, url_prefix="/api/security")

# Lazy init de servicios (evitar conexiones GCP al importar)
_security_repo = None
_upload_service = None
_multipart_service = None

def _get_security_repo():
    global _security_repo
    if _security_repo is None:
        _security_repo = SecurityVideoRepository()
    return _security_repo

def _get_upload_service():
    global _upload_service
    if _upload_service is None:
        _upload_service = ResumableUploadService()
    return _upload_service

def _get_multipart_service():
    global _multipart_service
    if _multipart_service is None:
        _multipart_service = MultipartUploadService()
    return _multipart_service


def _has_video_access(video) -> bool:
    current_user = session.get("username")
    return video and video.usuario == current_user


def _validate_worker_request() -> tuple[bool, object]:
    """Validate internal worker request using required shared token.

    Cloud Tasks requests must include X-Internal-Worker-Token configured via env.
    """
    expected_token = os.environ.get("WORKER_INTERNAL_TOKEN", "")
    provided_token = request.headers.get("X-Internal-Worker-Token", "")

    if not expected_token:
        logger.error("❌ ERROR CRÍTICO: WORKER_INTERNAL_TOKEN no está configurado.")
        return False, (jsonify({"error": "Configuration error"}), 500)

    if not provided_token or not hmac.compare_digest(provided_token, expected_token):
        logger.warning(
            "⚠️ Intento de acceso no autorizado a worker endpoint desde %s",
            request.remote_addr,
        )
        return False, (jsonify({"error": "Unauthorized"}), 401)

    return True, None


# ========== ENDPOINTS DE UPLOAD ==========


@app_security.route("/upload/init", methods=["POST"])
@api_socio_requerido
@limiter.limit(UPLOAD_LIMIT)
def iniciar_upload():
    """
    Inicia un upload resumable y crea el registro del video de seguridad

    Body:
        {
            "nombre_camara": "ENTRADA_PRINCIPAL_CAM_01",
            "ubicacion": "Edificio Central - Piso 1",
            "fecha_grabacion": "2026-02-04T06:00:00",
            "filename": "video_12h.mp4",
            "content_type": "video/mp4"
        }

    Returns:
        {
            "success": true,
            "video_id": "sec_video_xxx",
            "upload_url": "https://storage.googleapis.com/...",
            "gcs_path": "gs://bucket/path",
            "expiration_hours": 24
        }
    """
    request_start = time.perf_counter()
    trace_id = uuid.uuid4().hex[:8]

    try:
        data = request.get_json() or {}

        # Validar campos requeridos
        required_fields = ["filename"]
        for field in required_fields:
            if field not in data:
                return jsonify({"success": False, "error": f"Campo requerido: {field}"}), 400

        nombre_camara = data.get("nombre_camara") or "SIN_CAMARA"
        ubicacion = data.get("ubicacion") or "Sin ubicacion"
        fecha_grabacion = data.get("fecha_grabacion") or datetime.utcnow().isoformat()

        # Obtener usuario autenticado desde la sesión
        usuario = session.get("username", "unknown")

        # Generar URL de upload resumable
        upload_data = _get_upload_service().generar_resumable_upload_url(
            filename=data["filename"],
            content_type=data.get("content_type", "video/mp4"),
            metadata={
                "nombre_camara": nombre_camara,
                "ubicacion": ubicacion,
                "fecha_grabacion": fecha_grabacion,
            },
        )

        if not upload_data:
            return (
                jsonify(
                    {"success": False, "error": "No se pudo generar URL de upload"}
                ),
                500,
            )

        # Crear registro del video de seguridad
        video_id = f"sec_video_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # Log inicio de upload
        sec_logger.set_context(video_id, "UPLOAD_INIT")
        sec_logger.info(f"📤 UPLOAD INICIADO [trace={trace_id}]")
        sec_logger.info(f"   Cámara: {nombre_camara}")
        sec_logger.info(f"   Ubicación: {ubicacion}")
        sec_logger.info(f"   Archivo: {data['filename']}")
        sec_logger.info(f"   GCS Path: {upload_data['gcs_path']}")

        security_video = SecurityVideo(
            id=video_id,
            usuario=usuario,
            nombre_camara=nombre_camara,
            ubicacion=ubicacion,
            fecha_grabacion=fecha_grabacion,
            duracion_segundos=0,  # Se actualizará después del upload
            ruta_gcs=upload_data["gcs_path"],
            estado=EstadoSecurityVideo.UPLOADING,
            metadata_tecnico={
                "filename_original": data["filename"],
                "content_type": data.get("content_type", "video/mp4"),
            },
            fecha_creacion=datetime.utcnow().isoformat(),
        )

        # Guardar en repositorio
        _get_security_repo().guardar_video(security_video)

        sec_logger.info(f"✅ Video registrado en Firestore: {video_id}")
        logger.info(f"✅ Upload iniciado: {video_id}")

        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.info(f"✅ Upload init OK [trace={trace_id}] {elapsed_ms:.0f}ms")

        return (
            jsonify(
                {
                    "success": True,
                    "video_id": video_id,
                    "upload_url": upload_data["upload_url"],
                    "gcs_path": upload_data["gcs_path"],
                    "bucket": upload_data["bucket"],
                    "blob_name": upload_data["blob_name"],
                    "expiration_hours": upload_data["expiration_hours"],
                }
            ),
            200,
        )

    except Exception as e:
        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.error(f"❌ Upload init error [trace={trace_id}] {elapsed_ms:.0f}ms")
        sec_logger.error(f"❌ Error iniciando upload: {e}")
        sec_logger.error(f"   Traceback: {traceback.format_exc()}")
        logger.error(f"❌ Error iniciando upload: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_security.route("/upload/stream", methods=["POST"])
@api_socio_requerido
@limiter.limit(UPLOAD_LIMIT)
def subir_video_stream():
    """
    Sube un video directamente al backend (proxy para evitar CORS)
    El backend recibe el archivo y lo sube a GCS

    Body: multipart/form-data
        - video_id: ID del video de seguridad
        - file: archivo de video

    Returns:
        {
            "success": true,
            "video_id": "sec_video_xxx",
            "bytes_uploaded": 123456
        }
    """
    request_start = time.perf_counter()
    trace_id = uuid.uuid4().hex[:8]

    try:
        # Obtener video_id
        video_id = request.form.get("video_id")
        if not video_id:
            return jsonify({"success": False, "error": "video_id es requerido"}), 400

        logger.info(f"📥 Upload stream iniciado [trace={trace_id}] video_id={video_id}")

        # Obtener archivo
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No se encontró archivo"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "Archivo vacío"}), 400

        # Obtener video de repositorio
        video = _get_security_repo().obtener_video(video_id)
        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        # Log info del archivo
        logger.info(f"📦 Archivo recibido: {file.filename}")
        logger.info(f"   Content-Type: {file.content_type}")
        logger.info(f"   Destino GCS: {video.ruta_gcs}")

        # Detectar tamaño del archivo
        # Intentar obtener Content-Length, si no, seekear al final
        file_size = None
        try:
            file_size = request.content_length
        except Exception as e:
            logger.debug(f"Could not get content length: {e}")
        
        if not file_size:
            # Seekear para obtener tamaño
            file.stream.seek(0, 2)  # Ir al final
            file_size = file.stream.tell()
            file.stream.seek(0)  # Volver al inicio
        
        mb_size = file_size / (1024 * 1024) if file_size else 0
        logger.info(f"   Tamaño: {mb_size:.1f} MB")

        # Decidir estrategia de upload
        # Usar multipart para archivos >100MB
        USE_MULTIPART_THRESHOLD = 100 * 1024 * 1024  # 100MB
        use_multipart = file_size and file_size > USE_MULTIPART_THRESHOLD

        if use_multipart:
            logger.info(f"📤 Usando MULTIPART UPLOAD (archivo grande: {mb_size:.1f} MB)")
            upload_start = time.perf_counter()
            
            result = _get_multipart_service().subir_archivo_multipart(
                file_stream=file.stream,
                gcs_path=video.ruta_gcs,
                content_type=file.content_type or "video/mp4",
                chunk_size=50 * 1024 * 1024,  # 50MB chunks
                max_workers=5,  # 5 uploads paralelos
            )
            
            bytes_uploaded = result['bytes_uploaded']
            chunks_count = result['chunks_count']
            upload_time = result['elapsed_seconds']
            avg_speed = result['avg_speed_mbps']
            
            logger.info(
                f"✅ MULTIPART UPLOAD COMPLETADO: {mb_size:.1f} MB en {upload_time:.1f}s "
                f"({chunks_count} chunks, {avg_speed:.2f} MB/s) [trace={trace_id}]"
            )
        else:
            logger.info(f"📤 Usando upload simple (archivo: {mb_size:.1f} MB)")
            upload_start = time.perf_counter()
            
            bytes_uploaded = _get_upload_service().subir_archivo_directo(
                file_stream=file.stream,
                gcs_path=video.ruta_gcs,
                content_type=file.content_type or "video/mp4",
            )

            upload_time = time.perf_counter() - upload_start
            logger.info(
                f"✅ UPLOAD COMPLETADO: {mb_size:.1f} MB en {upload_time:.1f}s "
                f"[trace={trace_id}]"
            )

        # Actualizar estado
        video.actualizar_estado(EstadoSecurityVideo.UPLOADED)
        
        # Obtener metadata del archivo
        metadata = _get_upload_service().obtener_metadata_archivo(video.ruta_gcs)
        if metadata:
            video.metadata_tecnico.update(metadata)
            if "duracion_segundos" in metadata:
                video.duracion_segundos = metadata["duracion_segundos"]
        
        _get_security_repo().guardar_video(video)

        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.info(f"✅ Upload stream OK [trace={trace_id}] {elapsed_ms:.0f}ms")

        return (
            jsonify(
                {
                    "success": True,
                    "video_id": video_id,
                    "bytes_uploaded": bytes_uploaded,
                    "status": video.estado.value,
                }
            ),
            200,
        )

    except Exception as e:
        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.error(f"❌ Error subiendo archivo [trace={trace_id}] {elapsed_ms:.0f}ms: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_security.route("/upload/complete", methods=["POST"])
@api_socio_requerido
@limiter.limit(UPLOAD_LIMIT)
def completar_upload():
    """
    Marca un upload como completado, extrae metadata y 
    INICIA ANÁLISIS AUTOMÁTICAMENTE
    
    Body:
        {
            "video_id": "sec_video_xxx",
            "notify_email": "usuario@empresa.com",  // opcional
            "auto_process": true  // default: true
        }

    Returns:
        {
            "success": true,
            "video_id": "sec_video_xxx",
            "status": "processing",
            "message": "Análisis iniciado. Te notificaremos al completar.",
            "estimated_time_minutes": 25
        }
    """
    request_start = time.perf_counter()
    trace_id = uuid.uuid4().hex[:8]

    try:
        data = request.get_json() or {}
        video_id = data.get("video_id")
        notify_email = data.get("notify_email")
        auto_process = data.get("auto_process", True)  # Por defecto: procesar automáticamente

        if not video_id:
            return jsonify({"success": False, "error": "video_id es requerido"}), 400

        if notify_email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(notify_email)):
            return jsonify({"success": False, "error": "notify_email inválido"}), 400

        sec_logger.set_context(video_id, "UPLOAD_COMPLETE")
        sec_logger.info(f"📥 COMPLETANDO UPLOAD para video: {video_id} [trace={trace_id}]")

        # Obtener video
        video = _get_security_repo().obtener_video(video_id)
        if not video:
            sec_logger.error(f"Video no encontrado: {video_id}")
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        sec_logger.info(f"   GCS Path: {video.ruta_gcs}")

        # Verificar que el upload esté completo
        if not _get_upload_service().verificar_upload_completo(video.ruta_gcs):
            sec_logger.error(f"Archivo no completamente subido en GCS")
            return (
                jsonify(
                    {"success": False, "error": "El archivo no se ha subido completamente"}
                ),
                400,
            )

        sec_logger.info(f"   ✅ Archivo verificado en GCS")

        # Obtener metadata del archivo
        metadata = _get_upload_service().obtener_metadata_archivo(video.ruta_gcs)
        if metadata:
            video.metadata_tecnico.update(metadata)
            sec_logger.info(f"   Tamaño: {metadata.get('size_bytes', 0) / (1024*1024):.2f} MB")
            sec_logger.info(f"   Duración: {metadata.get('duracion_segundos', 0):.1f}s")

        # Guardar email de notificación si se proporcionó
        if notify_email:
            video.metadata_tecnico['notify_email'] = notify_email
            sec_logger.info(f"   📧 Notificar a: {notify_email}")

        # Actualizar estado
        video.actualizar_estado(EstadoSecurityVideo.UPLOADED)
        _get_security_repo().guardar_video(video)

        sec_logger.info(f"✅ UPLOAD COMPLETADO - Estado: {video.estado.value}")
        logger.info(f"✅ Upload completado: {video_id}")

        # =========== ANÁLISIS AUTOMÁTICO ===========
        estimated_time_minutes = None
        processing_started = False
        job_id = None  # Fase 3 - ID del trabajo en la cola
        
        if auto_process:
            sec_logger.info("🚀 Iniciando análisis automático...")
            
            # Estimar tiempo de procesamiento (aprox 2-3 min por hora de video)
            duracion_segundos = metadata.get('duracion_segundos', 0) if metadata else 0
            duracion_horas = duracion_segundos / 3600
            estimated_time_minutes = max(5, int(duracion_horas * 2.5))
            
            sec_logger.info(f"   ⏱️ Tiempo estimado: ~{estimated_time_minutes} minutos")
            
            # Fase 3 - Mejoras Pipeline v3.0: Usar cola Redis + RQ Workers
            try:
                from infrastructure.services.job_queue import enqueue_video_analysis, is_redis_available
                
                if is_redis_available():
                    # Usar cola de trabajos Redis + RQ
                    job_id = enqueue_video_analysis(video_id)
                    if job_id:
                        processing_started = True
                        sec_logger.info(f"✅ Video encolado para procesamiento (Job ID: {job_id})")
                        # Guardar job_id en metadata del video
                        video.metadata_tecnico['job_id'] = job_id
                        _get_security_repo().guardar_video(video)
                    else:
                        sec_logger.error("❌ Error encolando video, usando fallback threading")
                        raise Exception("No se pudo encolar en Redis")
                else:
                    sec_logger.warning("⚠️ Redis no disponible, usando fallback threading")
                    raise Exception("Redis no disponible")
                    
            except Exception as e:
                # Fallback a threading si Redis no está disponible
                sec_logger.warning(f"⚠️ Usando fallback threading: {e}")
                
                import threading
                
                def process_in_background(vid_id):
                    """Procesa el video en background"""
                    try:
                        from use_cases.complete_security_processor import CompleteSecurityVideoProcessor
                        processor = CompleteSecurityVideoProcessor()
                        processor.process_video_complete(vid_id)
                    except Exception as e:
                        logger.error(f"❌ Error en procesamiento background: {e}")
                
                # Iniciar thread de procesamiento
                process_thread = threading.Thread(
                    target=process_in_background,
                    args=(video_id,),
                    daemon=True
                )
                process_thread.start()
                processing_started = True
            
            sec_logger.info(f"✅ Procesamiento iniciado")
            
            # Notificación de confirmación (el video fue recibido)
            try:
                if notify_email:
                    from infrastructure.services.notification_service import NotificationService
                    notifier = NotificationService()
                    notifier.send_email(
                        to=notify_email,
                        subject=f"📹 Video recibido - {video.nombre_camara}",
                        body=f"""
Tu video ha sido recibido y está siendo analizado.

📹 Cámara: {video.nombre_camara}
📍 Ubicación: {video.ubicacion}
⏱️ Duración: {duracion_horas:.1f} horas
⏳ Tiempo estimado: ~{estimated_time_minutes} minutos

Te notificaremos cuando el análisis esté completo.

--
Sistema TIVIT-CU002 Security
                        """
                    )
                    sec_logger.info(f"📧 Email de confirmación enviado")
            except Exception as e:
                sec_logger.warning(f"⚠️ No se pudo enviar email de confirmación: {e}")

        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.info(f"✅ Upload complete OK [trace={trace_id}] {elapsed_ms:.0f}ms")

        return (
            jsonify(
                {
                    "success": True,
                    "video_id": video_id,
                    "status": "processing" if processing_started else video.estado.value,
                    "metadata": video.metadata_tecnico,
                    "message": "Análisis iniciado automáticamente. Te notificaremos al completar." if processing_started else "Upload completado",
                    "estimated_time_minutes": estimated_time_minutes,
                    "processing_started": processing_started,
                    "job_id": job_id  # Fase 3 - ID del trabajo en la cola Redis
                }
            ),
            200,
        )

    except Exception as e:
        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.error(f"❌ Error completando upload [trace={trace_id}] {elapsed_ms:.0f}ms: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ========== REPROCESAMIENTO DE VIDEO ==========


@app_security.route("/videos/<video_id>/reprocess", methods=["POST"])
@api_socio_requerido
def reprocesar_video(video_id: str):
    """
    Reprocesa un video que ya está en GCS sin necesidad de subirlo de nuevo.
    Útil cuando el análisis falló o se quiere re-analizar con algoritmos actualizados.

    Body (opcional):
        {
            "notify_email": "usuario@empresa.com"
        }

    Returns:
        {
            "success": true,
            "video_id": "sec_video_xxx",
            "status": "processing",
            "message": "Reprocesamiento iniciado"
        }
    """
    request_start = time.perf_counter()
    trace_id = uuid.uuid4().hex[:8]

    try:
        data = request.get_json() or {}
        notify_email = data.get("notify_email")

        logger.info(f"🔄 REPROCESANDO video: {video_id} [trace={trace_id}]")

        if notify_email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(notify_email)):
            return jsonify({"success": False, "error": "notify_email inválido"}), 400

        # Obtener video
        video = _get_security_repo().obtener_video(video_id)
        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        if not _has_video_access(video):
            return jsonify({"success": False, "error": "No tiene permisos para reprocesar este video"}), 403

        # Verificar que el archivo existe en GCS
        if not _get_upload_service().verificar_upload_completo(video.ruta_gcs):
            return (
                jsonify(
                    {"success": False, "error": "El archivo no existe en GCS. Debe subir el video nuevamente."}
                ),
                400,
            )

        logger.info(f"   ✅ Archivo verificado en GCS: {video.ruta_gcs}")

        # Limpiar eventos anteriores si existen
        try:
            eventos_anteriores = _get_security_repo().obtener_eventos_video(video_id)
            if eventos_anteriores:
                logger.info(f"   🧹 Limpiando {len(eventos_anteriores)} eventos anteriores...")
                # Los eventos se sobreescribirán con el nuevo análisis
        except Exception:
            pass

        # Resetear estado y estadísticas
        video.actualizar_estado(EstadoSecurityVideo.UPLOADED)
        video.estadisticas = {}
        video.reporte_txt_url = ""
        video.reporte_pdf_url = ""
        video.fecha_procesamiento = None
        video.tiempo_procesamiento_segundos = None
        if 'error' in video.metadata_tecnico:
            del video.metadata_tecnico['error']
        
        # Guardar email de notificación si se proporcionó
        if notify_email:
            video.metadata_tecnico['notify_email'] = notify_email
            logger.info(f"   📧 Notificar a: {notify_email}")

        _get_security_repo().guardar_video(video)

        # Estimar tiempo de procesamiento
        duracion_segundos = video.duracion_segundos or video.metadata_tecnico.get('duracion_segundos', 0)
        duracion_horas = duracion_segundos / 3600 if duracion_segundos else 0
        estimated_time_minutes = max(5, int(duracion_horas * 2.5))

        logger.info(f"   ⏱️ Tiempo estimado: ~{estimated_time_minutes} minutos")

        # Iniciar procesamiento en background (Fase 3 - Usar cola Redis + RQ)
        job_id = None
        try:
            from infrastructure.services.job_queue import enqueue_video_analysis, is_redis_available
            
            if is_redis_available():
                # Usar cola de trabajos Redis + RQ
                job_id = enqueue_video_analysis(video_id)
                if job_id:
                    logger.info(f"✅ Video encolado para reprocesamiento (Job ID: {job_id})")
                    video.metadata_tecnico['job_id'] = job_id
                    _get_security_repo().guardar_video(video)
                else:
                    raise Exception("No se pudo encolar en Redis")
            else:
                raise Exception("Redis no disponible")
                
        except Exception as e:
            # Fallback a threading
            logger.warning(f"⚠️ Usando fallback threading: {e}")
            
            import threading

            def process_in_background(vid_id):
                """Procesa el video en background"""
                try:
                    from use_cases.complete_security_processor import CompleteSecurityVideoProcessor
                    processor = CompleteSecurityVideoProcessor()
                    processor.process_video_complete(vid_id)
                except Exception as e:
                    logger.error(f"❌ Error en reprocesamiento background: {e}")

            process_thread = threading.Thread(
                target=process_in_background,
                args=(video_id,),
                daemon=True
            )
            process_thread.start()

        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.info(f"✅ Reprocesamiento iniciado [trace={trace_id}] {elapsed_ms:.0f}ms")

        return (
            jsonify(
                {
                    "success": True,
                    "video_id": video_id,
                    "status": "processing",
                    "message": "Reprocesamiento iniciado. El video será analizado nuevamente.",
                    "estimated_time_minutes": estimated_time_minutes,
                    "gcs_path": video.ruta_gcs,
                    "job_id": job_id  # Fase 3 - ID del trabajo en la cola Redis (None si usó threading)
                }
            ),
            200,
        )

    except Exception as e:
        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.error(f"❌ Error reprocesando video [trace={trace_id}] {elapsed_ms:.0f}ms: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ========== ENDPOINTS DE CONSULTA ==========


@app_security.route("/videos", methods=["GET"])
@api_socio_requerido
def listar_videos():
    """
    Lista videos de seguridad del usuario

    Query params:
        - limit: Cantidad máxima de resultados (default: 50)
        - estado: Filtrar por estado (opcional)

    Returns:
        {
            "success": true,
            "videos": [...]
        }
    """
    try:
        # Obtener usuario de sesión
        usuario = session.get("username", "unknown")
        limit = int(request.args.get("limit", 50))
        estado_filter = request.args.get("estado")

        # Obtener videos
        if estado_filter:
            try:
                estado = EstadoSecurityVideo(estado_filter)
                videos = _get_security_repo().obtener_por_estado(estado, limit=limit)
                # Filtrar por usuario
                videos = [v for v in videos if v.usuario == usuario]
            except ValueError:
                return (
                    jsonify({"success": False, "error": f"Estado inválido: {estado_filter}"}),
                    400,
                )
        else:
            videos = _get_security_repo().obtener_por_usuario(usuario, limit=limit)

        # Convertir a dict
        videos_data = [
            {
                "id": v.id,
                "nombre_camara": v.nombre_camara,
                "ubicacion": v.ubicacion,
                "fecha_grabacion": v.fecha_grabacion,
                "duracion_segundos": v.duracion_segundos,
                "estado": v.estado.value,
                "fecha_creacion": v.fecha_creacion,
                "fecha_procesamiento": v.fecha_procesamiento,
                "tiempo_procesamiento_segundos": v.tiempo_procesamiento_segundos,
                "estadisticas": v.estadisticas,
                "metadata_tecnico": v.metadata_tecnico,
                "reporte_txt_url": v.reporte_txt_url,
                "reporte_pdf_url": v.reporte_pdf_url,
                "eventos_count": v.estadisticas.get('total_eventos', len(v.eventos)),
                "tiene_eventos_importantes": v.estadisticas.get('eventos_por_riesgo', {}).get('ALTO', 0) + v.estadisticas.get('eventos_por_riesgo', {}).get('CRITICO', 0) > 0,
            }
            for v in videos
        ]

        return jsonify({"success": True, "videos": videos_data, "total": len(videos_data)}), 200

    except Exception as e:
        logger.error(f"❌ Error listando videos: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_security.route("/videos/<video_id>", methods=["GET"])
@api_socio_requerido
def obtener_video(video_id: str):
    """
    Obtiene detalles de un video de seguridad

    Returns:
        {
            "success": true,
            "video": {...}
        }
    """
    try:
        video = _get_security_repo().obtener_video(video_id)

        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        # Verificar que el usuario tenga permisos para ver este video
        current_user = session.get("username")
        current_rol = session.get("rol")
        if current_rol != "admin" and video.usuario != current_user:
            return jsonify({"success": False, "error": "No tiene permisos para acceder a este video"}), 403

        video_data = {
            "id": video.id,
            "usuario": video.usuario,
            "nombre_camara": video.nombre_camara,
            "ubicacion": video.ubicacion,
            "fecha_grabacion": video.fecha_grabacion,
            "duracion_segundos": video.duracion_segundos,
            "ruta_gcs": video.ruta_gcs,
            "estado": video.estado.value,
            "metadata_tecnico": video.metadata_tecnico,
            "estadisticas": video.estadisticas,
            "reporte_txt_url": video.reporte_txt_url,
            "reporte_pdf_url": video.reporte_pdf_url,
            "fecha_creacion": video.fecha_creacion,
            "fecha_procesamiento": video.fecha_procesamiento,
            "tiempo_procesamiento_segundos": video.tiempo_procesamiento_segundos,
            "eventos_count": video.estadisticas.get('total_eventos', len(video.eventos)),
        }

        return jsonify({"success": True, "video": video_data}), 200

    except Exception as e:
        logger.error(f"❌ Error obteniendo video: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_security.route("/videos/<video_id>/eventos", methods=["GET"])
@api_socio_requerido
def obtener_eventos(video_id: str):
    """
    Obtiene eventos de un video de seguridad con paginación y filtros objetivos

    Query params:
        - page: Número de página (default: 1)
        - per_page: Items por página (default: 50, max: 200)
        - objeto: Filtrar por objeto detectado (ej: "person", "car")
        - accion: Filtrar por acción detectada (ej: "walking", "running")
        - min_personas: Filtrar por cantidad mínima de personas
        - min_vehiculos: Filtrar por cantidad mínima de vehículos
        - order: 'asc' o 'desc' por timestamp (default: 'asc')

    Returns:
        {
            "success": true,
            "eventos": [...],
            "pagination": {...}
        }
    """
    try:
        # Verificar que el video existe
        video = _get_security_repo().obtener_video(video_id)
        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        # Verificar permisos del usuario
        current_user = session.get("username")
        current_rol = session.get("rol")
        if current_rol != "admin" and video.usuario != current_user:
            return jsonify({"success": False, "error": "No tiene permisos para acceder a los eventos de este video"}), 403

        # Parámetros de paginación
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        order = request.args.get('order', 'asc', type=str)
        
        # Parámetros de filtrado objetivos
        objeto_filter = request.args.get("objeto")
        accion_filter = request.args.get("accion")
        min_personas = request.args.get("min_personas", type=int)
        min_vehiculos = request.args.get("min_vehiculos", type=int)
        
        # Validar parámetros
        page = max(1, page)
        per_page = min(200, max(1, per_page))
        
        # Obtener todos los eventos
        todos_eventos = _get_security_repo().obtener_eventos_video(video_id)
        
        # Aplicar filtros objetivos
        if objeto_filter:
            todos_eventos = [e for e in todos_eventos if objeto_filter in e.objetos_detectados]
        
        if accion_filter:
            todos_eventos = [e for e in todos_eventos if accion_filter in e.acciones_detectadas]
        
        if min_personas is not None:
            todos_eventos = [e for e in todos_eventos if e.personas_count >= min_personas]
        
        if min_vehiculos is not None:
            todos_eventos = [e for e in todos_eventos if e.vehiculos_count >= min_vehiculos]

        # Ordenar
        todos_eventos.sort(
            key=lambda e: e.timestamp_inicio,
            reverse=(order == 'desc')
        )
        
        # Calcular paginación
        total = len(todos_eventos)
        total_pages = (total + per_page - 1) // per_page
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        eventos_pagina = todos_eventos[start_idx:end_idx]

        # Convertir a dict con nuevos campos objetivos
        eventos_data = [
            {
                "id": e.id,
                "timestamp_inicio": e.timestamp_inicio,
                "timestamp_fin": e.timestamp_fin,
                "duracion": e.duracion,
                "objetos_detectados": e.objetos_detectados,
                "acciones_detectadas": e.acciones_detectadas,
                "personas_count": e.personas_count,
                "vehiculos_count": e.vehiculos_count,
                "descripcion": e.descripcion,
                "confianza": e.confianza,
                "clip_url": e.clip_url if hasattr(e, 'clip_url') else None,
                "frames_urls": e.frames_urls if hasattr(e, 'frames_urls') else [],
                "analisis_detallado": e.analisis_detallado
            }
            for e in eventos_pagina
        ]

        return jsonify({
            "success": True,
            "eventos": eventos_data,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }), 200

    except Exception as e:
        logger.error(f"❌ Error obteniendo eventos: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_security.route("/videos/<video_id>/query", methods=["POST"])
@api_socio_requerido
def consultar_video(video_id: str):
    """
    Consulta en lenguaje natural sobre el video analizado
    
    Body:
        {
            "question": "¿Hubo robos entre las 2pm y 4pm?"
        }
    
    Returns:
        {
            "success": true,
            "answer": "Respuesta generada por Gemini",
            "eventos_relevantes": [...],
            "metadata": {
                "total_eventos_analizados": 150,
                "eventos_encontrados": 3
            }
        }
    """
    try:
        data = request.get_json()
        question = data.get("question")
        
        if not question:
            return jsonify({"success": False, "error": "Campo 'question' requerido"}), 400
        
        # Verificar que el video existe
        video = _get_security_repo().obtener_video(video_id)
        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404
        
        # Verificar permisos del usuario
        current_user = session.get("username")
        current_rol = session.get("rol")
        if current_rol != "admin" and video.usuario != current_user:
            return jsonify({"success": False, "error": "No tiene permisos para consultar este video"}), 403

        logger.info(f"🔍 Consulta en video {video_id}: {question}")
        
        # Usar SecurityQueryEngine
        from use_cases.security_query_engine import SecurityQueryEngine
        
        query_engine = SecurityQueryEngine()
        result = query_engine.query(video_id, question)
        
        return jsonify({
            "success": True,
            "answer": result.get("answer", ""),
            "eventos_relevantes": result.get("relevant_events", []),
            "metadata": {
                "total_eventos_analizados": result.get("total_events", 0),
                "eventos_encontrados": len(result.get("relevant_events", []))
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error en consulta: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_security.route("/videos/<video_id>", methods=["DELETE"])
@api_socio_requerido
def eliminar_video(video_id: str):
    """
    Elimina un video de seguridad y sus eventos asociados

    Returns:
        {
            "success": true,
            "message": "Video eliminado"
        }
    """
    try:
        video = _get_security_repo().obtener_video(video_id)
        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        # Verificar permisos del usuario
        current_username = session.get("username")
        current_rol = session.get("rol")
        if current_rol != "admin" and video.usuario != current_username:
            logger.warning(f"⚠️ Intento de eliminación no autorizado: usuario={current_username} video={video_id}")
            return jsonify({"success": False, "error": "No tiene permisos para eliminar este video"}), 403

        # Eliminar archivo de GCS
        if video.ruta_gcs:
            _get_upload_service().eliminar_archivo(video.ruta_gcs)

        # Eliminar de repositorio (incluye eventos)
        success = _get_security_repo().eliminar_video(video_id)

        if success:
            logger.info(f"✅ Video eliminado: {video_id}")
            return jsonify({"success": True, "message": "Video eliminado correctamente"}), 200
        else:
            return jsonify({"success": False, "error": "No se pudo eliminar el video"}), 500

    except Exception as e:
        logger.error(f"❌ Error eliminando video: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_security.route("/videos/<video_id>/process", methods=["POST"])
@api_socio_requerido
def procesar_video(video_id: str):
    """
    Inicia el procesamiento COMPLETO de un video de seguridad
    
    NUEVO ENFOQUE (sin clasificaciones):
    1. Motion Detection (OpenCV) - filtra segmentos estáticos
    2. Análisis COMPLETO de TODOS los segmentos con movimiento
    3. Video Intelligence + Gemini para análisis objetivo
    4. Guardar TODO en Firestore
    5. Generación de reporte completo
    
    Returns:
        {
            "success": true,
            "message": "Procesamiento en cola",
            "video_id": "sec_video_xxx",
            "task_id": "xxx"
        }
    """
    try:
        sec_logger.set_context(video_id, "PROCESS_START")
        sec_logger.start_phase("API_PROCESS_REQUEST", f"Solicitud de procesamiento recibida")
        
        video = _get_security_repo().obtener_video(video_id)
        if not video:
            sec_logger.error(f"Video no encontrado: {video_id}")
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        if not _has_video_access(video):
            sec_logger.warning(f"Acceso no autorizado a procesamiento: video={video_id}")
            return jsonify({"success": False, "error": "No tiene permisos para procesar este video"}), 403
        
        sec_logger.info(f"📹 Video encontrado:")
        sec_logger.info(f"   Cámara: {video.nombre_camara}")
        sec_logger.info(f"   Ubicación: {video.ubicacion}")
        sec_logger.info(f"   Estado actual: {video.estado.value}")
        sec_logger.info(f"   GCS Path: {video.ruta_gcs}")
        
        # Verificar que el video esté en estado "uploaded"
        if video.estado != EstadoSecurityVideo.UPLOADED:
            sec_logger.warning(f"Estado inválido para procesar: {video.estado.value}")
            return jsonify({
                "success": False,
                "error": f"El video no está listo para procesar. Estado actual: {video.estado.value}"
            }), 400
        
        # Intentar usar Cloud Tasks, fallback a threading
        try:
            from infrastructure.adapters.cloud_tasks_adapter import CloudTasksAdapter
            
            cloud_tasks = CloudTasksAdapter()
            task_name = cloud_tasks.create_task(
                queue_name="security-video-processing",
                endpoint="/api/security/process-worker",
                payload={"video_id": video_id},
                delay_seconds=0
            )
            
            sec_logger.info(f"✅ Tarea creada en Cloud Tasks: {task_name}")
            sec_logger.end_phase("API_PROCESS_REQUEST", success=True, details="Cloud Task creada")
            
            return jsonify({
                "success": True,
                "message": "Procesamiento en cola (Cloud Tasks)",
                "video_id": video_id,
                "task_id": task_name,
                "note": "Análisis completo de TODOS los eventos (sin clasificaciones)"
            }), 200
            
        except Exception as cloud_error:
            # Fallback a threading si Cloud Tasks no está disponible
            logger.warning(f"⚠️ Cloud Tasks no disponible: {cloud_error}. Usando threading como fallback.")
            sec_logger.warning(f"Cloud Tasks no disponible, usando threading fallback")
            
            # ========== USAR NUEVO PROCESADOR COMPLETO ==========
            from use_cases.complete_security_processor import CompleteSecurityVideoProcessor
            processor = CompleteSecurityVideoProcessor(max_parallel_workers=4)
            
            import threading
            
            def process_with_logging(vid_id):
                """Wrapper para procesar con logging de inicio/fin"""
                sec_logger.set_context(vid_id, "BACKGROUND_PROCESS")
                sec_logger.info(f"🔄 PIPELINE v3.0 INICIADO (Video Clips + Gemini)")
                sec_logger.info(f"   Enfoque: Análisis exhaustivo con clips de video")
                try:
                    processor.process_video_complete(vid_id)
                    sec_logger.info(f"✅ THREAD COMPLETADO - Análisis completo finalizado")
                except Exception as e:
                    sec_logger.error(f"❌ THREAD ERROR: {e}")
                    sec_logger.error(f"   Traceback: {traceback.format_exc()}")
            
            thread = threading.Thread(
                target=process_with_logging,
                args=(video_id,)
            )
            thread.start()
            
            sec_logger.end_phase("API_PROCESS_REQUEST", success=True, details="Thread iniciado (fallback)")
            
            return jsonify({
                "success": True,
                "message": "Procesamiento iniciado en background (threading fallback)",
                "video_id": video_id,
                "note": "Análisis completo de TODOS los eventos (sin clasificaciones)"
            }), 200
    
    except Exception as e:
        sec_logger.error(f"❌ Error iniciando procesamiento: {e}")
        sec_logger.error(f"   Traceback: {traceback.format_exc()}")
        logger.error(f"❌ Error iniciando procesamiento: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_security.route("/process-worker", methods=["POST"])
def process_worker():
    """
    Worker endpoint para Cloud Tasks
    
    NO debe ser llamado directamente desde el frontend.
    Solo Cloud Tasks puede llamar este endpoint.
    
    Procesa un video de seguridad de forma completamente objetiva (sin clasificaciones).
    """
    try:
        valid, auth_response = _validate_worker_request()
        if not valid:
            return auth_response
        
        data = request.get_json()
        video_id = data.get("video_id")
        
        if not video_id:
            return jsonify({"error": "video_id requerido"}), 400
        
        logger.info(f"🚀 Worker procesando video: {video_id}")
        sec_logger.set_context(video_id, "WORKER")
        sec_logger.info("Worker de Cloud Tasks iniciado - Análisis completo sin clasificaciones")
        
        # ========== USAR NUEVO PROCESADOR COMPLETO ==========
        from use_cases.complete_security_processor import CompleteSecurityVideoProcessor
        processor = CompleteSecurityVideoProcessor(max_parallel_workers=4)
        
        processor.process_video_complete(video_id)
        
        logger.info(f"✅ Worker completado exitosamente: {video_id}")
        return jsonify({"success": True, "video_id": video_id}), 200
    
    except Exception as e:
        logger.error(f"❌ Error en worker: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": "Error interno del servidor"}), 500


# ========== ENDPOINTS LAZY ARCHITECTURE (ON-DEMAND) ==========


@app_security.route("/videos/<video_id>/index", methods=["POST"])
@api_socio_requerido
def indexar_video(video_id: str):
    """
    INDEXADO LIGERO: Procesa video con motion detection y clasificación básica
    No hace análisis profundo (más rápido y económico)
    
    Ideal para:
    - Procesamiento inicial rápido (10-15 min)
    - Bajo costo ($1-2 vs $12-18)
    - Consultas posteriores bajo demanda
    
    Returns:
        {
            "success": true,
            "message": "Video indexado",
            "video_id": "xxx",
            "clips_detectados": 50,
            "costo_estimado": 1.50
        }
    """
    try:
        sec_logger.set_context(video_id, "INDEX_REQUEST")
        sec_logger.info("📋 Solicitud de indexado recibida")
        
        video = _get_security_repo().obtener_video(video_id)
        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        if not _has_video_access(video):
            return jsonify({"success": False, "error": "No tiene permisos para indexar este video"}), 403
        
        if video.estado != EstadoSecurityVideo.UPLOADED:
            return jsonify({
                "success": False,
                "error": f"El video no está listo para indexar. Estado: {video.estado.value}"
            }), 400
        
        # Procesar en background con Cloud Tasks o threading
        try:
            from infrastructure.adapters.cloud_tasks_adapter import CloudTasksAdapter
            
            cloud_tasks = CloudTasksAdapter()
            task_name = cloud_tasks.create_task(
                queue_name="security-video-processing",
                endpoint="/api/security/index-worker",
                payload={"video_id": video_id},
                delay_seconds=0
            )
            
            sec_logger.info(f"✅ Tarea de indexado creada: {task_name}")
            
            return jsonify({
                "success": True,
                "message": "Indexado en cola (10-15 minutos)",
                "video_id": video_id,
                "task_id": task_name,
                "costo_estimado": 1.50
            }), 200
            
        except Exception:
            # Fallback a threading - NOTA: Indexado no implementado en CompleteSecurityVideoProcessor
            # El análisis completo ya incluye toda la información
            logger.warning("⚠️ Indexado separado no disponible en nuevo sistema. Use /process en su lugar.")
            return jsonify({
                "success": False,
                "error": "Indexado separado no implementado. Use el endpoint /process para análisis completo.",
                "message": "El nuevo sistema analiza todo de una vez, no requiere indexado separado"
            }), 501
    
    except Exception as e:
        sec_logger.error(f"❌ Error iniciando indexado: {e}")
        logger.error(f"❌ Error: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_security.route("/index-worker", methods=["POST"])
def index_worker():
    """Worker para indexado ligero (Cloud Tasks) - NO IMPLEMENTADO EN NUEVO SISTEMA"""
    try:
        valid, auth_response = _validate_worker_request()
        if not valid:
            return auth_response

        data = request.get_json()
        video_id = data.get("video_id")
        
        if not video_id:
            return jsonify({"error": "video_id requerido"}), 400
        
        logger.warning(f"⚠️ Indexado worker llamado pero no implementado: {video_id}")
        
        # El nuevo sistema analiza todo de una vez con CompleteSecurityVideoProcessor
        return jsonify({
            "success": False,
            "error": "Indexado separado no implementado en nuevo sistema",
            "message": "Use el endpoint /process para análisis completo"
        }), 501
    
    except Exception as e:
        logger.error(f"❌ Error en index worker: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500


@app_security.route("/videos/<video_id>/report/full", methods=["POST"])
@api_socio_requerido
def generar_reporte_completo(video_id: str):
    """
    REPORTE COMPLETO BAJO DEMANDA
    
    Genera reporte profesional analizando todos los clips faltantes
    
    Body:
        {
            "analisis_profundo": true,  // Si false, usa solo data en caché
            "formato": "pdf"  // "txt" | "pdf" | "json"
        }
    
    Returns:
        {
            "success": true,
            "reporte_url": "gs://...",
            "clips_analizados_nuevos": 15,
            "costo_total": 2.50,
            "tiempo_generacion": 120
        }
    """
    try:
        data = request.get_json() or {}
        analisis_profundo = data.get("analisis_profundo", True)
        formato = data.get("formato", "pdf")
        
        # Validar formato
        if formato not in ["txt", "pdf", "json"]:
            return jsonify({"success": False, "error": "Formato inválido (txt/pdf/json)"}), 400
        
        logger.info(f"📄 Generando reporte completo: {video_id} (profundo={analisis_profundo}, formato={formato})")
        
        # Verificar que el video esté indexado
        video = _get_security_repo().obtener_video(video_id)
        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        if not _has_video_access(video):
            return jsonify({"success": False, "error": "No tiene permisos para generar este reporte"}), 403
        
        if video.estado not in [EstadoSecurityVideo.INDEXED, EstadoSecurityVideo.COMPLETED]:
            return jsonify({
                "success": False,
                "error": f"Video no está indexado. Estado: {video.estado.value}"
            }), 400
        
        # Generar reporte usando ReportGenerator directamente
        from infrastructure.services.report_generator import ReportGenerator
        
        # Obtener eventos
        eventos = _get_security_repo().obtener_eventos(video_id)
        
        generator = ReportGenerator()
        
        if formato == 'txt':
            contenido = generator.generate_text_report(video, eventos)
            reporte_path = generator.save_text_report(contenido, video_id)
        elif formato == 'pdf':
            reporte_path = generator.generate_pdf_report(video, eventos, video_id)
        else:
            return jsonify({"success": False, "error": "Formato no soportado"}), 400
        
        if not reporte_path:
            return jsonify({"success": False, "error": "Error generando reporte"}), 500
        
        logger.info(f"✅ Reporte generado: {reporte_path}")
        
        return jsonify({
            "success": True,
            "video_id": video_id,
            "reporte_path": str(reporte_path),
            "formato": formato,
            "analisis_profundo": analisis_profundo,
            "eventos_totales": len(eventos)
        }), 200
    
    except Exception as e:
        logger.error(f"❌ Error generando reporte: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_security.route("/videos/<video_id>/cache/stats", methods=["GET"])
@api_socio_requerido
def obtener_cache_stats(video_id: str):
    """
    Obtiene estadísticas del caché de análisis de un video
    
    Útil para mostrar en UI:
    - Cuántos clips ya fueron analizados
    - Costo acumulado de queries
    - Historial de consultas
    
    Returns:
        {
            "success": true,
            "total_queries": 5,
            "total_clips_analizados": 23,
            "costo_total_acumulado": 3.50,
            "queries_recientes": [...]
        }
    """
    try:
        video = _get_security_repo().obtener_video(video_id)
        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        if not _has_video_access(video):
            return jsonify({"success": False, "error": "No tiene permisos para consultar este recurso"}), 403

        from infrastructure.services.analysis_cache_manager import get_cache_manager
        
        cache_manager = get_cache_manager()
        stats = cache_manager.get_cache_stats(video_id)
        history = cache_manager.get_query_history(video_id)
        
        return jsonify({
            "success": True,
            "video_id": video_id,
            "total_queries": stats.get('total_queries', 0),
            "total_clips_analizados": stats.get('total_clips_analizados', 0),
            "costo_total_queries": stats.get('costo_total_queries', 0.0),
            "costo_total_analisis": stats.get('costo_total_analisis', 0.0),
            "costo_total_acumulado": stats.get('costo_total_acumulado', 0.0),
            "ultima_actualizacion": stats.get('ultima_actualizacion'),
            "queries_recientes": history[-10:] if history else []  # Últimas 10
        }), 200
    
    except Exception as e:
        logger.error(f"❌ Error obteniendo stats de caché: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ========== ENDPOINTS DE NOTIFICACIONES EN TIEMPO REAL ==========


@app_security.route("/videos/<video_id>/progress", methods=["GET"])
@api_socio_requerido
def stream_progress(video_id: str):
    """
    Server-Sent Events (SSE) para monitorear progreso en tiempo real
    
    Retorna actualizaciones del procesamiento cada 2 segundos.
    
    Usage en frontend:
        const eventSource = new EventSource('/api/security/videos/${videoId}/progress');
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log(data.estado, data.progreso);
        };
    """
    video = _get_security_repo().obtener_video(video_id)
    if not video:
        return jsonify({"success": False, "error": "Video no encontrado"}), 404

    if not _has_video_access(video):
        return jsonify({"success": False, "error": "No tiene permisos para acceder a este recurso"}), 403

    def generate():
        """Generador de eventos SSE"""
        import time
        import json
        from flask import Response
        
        max_iterations = 300  # 10 minutos máximo (300 * 2s)
        iteration = 0
        
        while iteration < max_iterations:
            try:
                video = _get_security_repo().obtener_video(video_id)
                
                if not video:
                    data = {
                        "error": "Video no encontrado",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                    break
                
                # Calcular progreso basado en checkpoint
                checkpoint = video.metadata_tecnico.get('processing_checkpoint', 'INICIO')
                checkpoint_progress = {
                    'INICIO': 0,
                    'MOTION_DONE': 20,
                    'CLIPS_EXTRACTED': 30,
                    'CLASSIFICATION_DONE': 70,
                    'DEEP_ANALYSIS_DONE': 85,
                    'EVENTS_SAVED': 90,
                    'REPORT_DONE': 100
                }
                
                progreso = checkpoint_progress.get(checkpoint, 0)
                
                # Si está completado o con error, progreso 100%
                if video.estado in [EstadoSecurityVideo.COMPLETED, EstadoSecurityVideo.ERROR]:
                    progreso = 100
                
                data = {
                    "success": True,
                    "video_id": video_id,
                    "estado": video.estado.value,
                    "progreso": progreso,
                    "fase_actual": checkpoint,
                    "timestamp": datetime.utcnow().isoformat(),
                    "estadisticas": video.estadisticas if video.estadisticas else {}
                }
                
                yield f"data: {json.dumps(data)}\n\n"
                
                # Si completado o error, terminar stream
                if video.estado in [EstadoSecurityVideo.COMPLETED, EstadoSecurityVideo.ERROR]:
                    logger.info(f"📡 SSE finalizado para {video_id}: {video.estado.value}")
                    break
                
                time.sleep(2)  # Esperar 2 segundos entre updates
                iteration += 1
                
            except Exception as e:
                logger.error(f"Error en SSE stream: {e}")
                error_data = {
                    "error": "Error interno del servidor",
                    "timestamp": datetime.utcnow().isoformat()
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                break
    
    from flask import Response
    return Response(generate(), mimetype='text/event-stream')


@app_security.route("/videos/<video_id>/status", methods=["GET"])
@api_socio_requerido
def obtener_estado_video(video_id: str):
    """
    Obtiene el estado actual de un video (alternativa a SSE)
    
    Útil para polling manual
    
    Returns:
        {
            "success": true,
            "video_id": "xxx",
            "estado": "processing",
            "progreso": 45,
            "fase_actual": "CLASSIFICATION_DONE",
            "timestamp": "2026-02-08T..."
        }
    """
    try:
        video = _get_security_repo().obtener_video(video_id)
        
        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        if not _has_video_access(video):
            return jsonify({"success": False, "error": "No tiene permisos para acceder a este recurso"}), 403
        
        checkpoint = video.metadata_tecnico.get('processing_checkpoint', 'INICIO')
        checkpoint_progress = {
            'INICIO': 0,
            'MOTION_DONE': 20,
            'CLIPS_EXTRACTED': 30,
            'CLASSIFICATION_DONE': 70,
            'DEEP_ANALYSIS_DONE': 85,
            'EVENTS_SAVED': 90,
            'REPORT_DONE': 100
        }
        
        progreso = checkpoint_progress.get(checkpoint, 0)
        
        if video.estado in [EstadoSecurityVideo.COMPLETED, EstadoSecurityVideo.ERROR]:
            progreso = 100
        
        return jsonify({
            "success": True,
            "video_id": video_id,
            "estado": video.estado.value,
            "progreso": progreso,
            "fase_actual": checkpoint,
            "timestamp": datetime.utcnow().isoformat(),
            "estadisticas": video.estadisticas if video.estadisticas else {}
        }), 200
        
    except Exception as e:
        logger.error(f"Error obteniendo estado: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ========== ENDPOINT DE HEALTH CHECK ==========


@app_security.route("/health", methods=["GET"])
@api_socio_requerido
def health_check():
    """
    Verifica el estado de los servicios

    Returns:
        {
            "success": true,
            "services": {
                "repository": true,
                "upload_service": true
            }
        }
    """
    return (
        jsonify(
            {
                "success": True,
                "services": {
                    "repository": _get_security_repo().is_available(),
                    "upload_service": _get_upload_service().is_available(),
                },
            }
        ),
        200,
    )


# ========== ENDPOINTS DE LOGS Y MONITOREO ==========


@app_security.route("/logs/analysis", methods=["GET"])
@api_socio_requerido
def get_analysis_logs():
    """
    Obtiene los logs de análisis de seguridad
    
    Query params:
        lines: Número de líneas a retornar (default: 100)
        video_id: Filtrar por video específico (opcional)
        level: Filtrar por nivel (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        {
            "success": true,
            "logs": [...],
            "log_file": "/path/to/log",
            "total_lines": 500
        }
    """
    try:
        if not _is_admin_session():
            return jsonify({"success": False, "error": "Acceso denegado"}), 403

        from infrastructure.services.security_logger import get_security_logger
        
        sec_logger = get_security_logger()
        log_file = sec_logger.get_log_file_path()
        
        lines = int(request.args.get('lines', 100))
        video_id_filter = request.args.get('video_id')
        level_filter = request.args.get('level', '').upper()
        
        import os
        if not os.path.exists(log_file):
            return jsonify({
                "success": True,
                "logs": [],
                "log_file": log_file,
                "total_lines": 0,
                "message": "Log file not created yet"
            }), 200
        
        # Leer logs
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        
        # Filtrar si es necesario
        filtered_lines = []
        for line in all_lines:
            # Filtrar por video_id
            if video_id_filter and video_id_filter not in line:
                continue
            # Filtrar por nivel
            if level_filter and level_filter not in line:
                continue
            filtered_lines.append(line.strip())
        
        # Obtener las últimas N líneas
        result_lines = filtered_lines[-lines:] if len(filtered_lines) > lines else filtered_lines
        
        return jsonify({
            "success": True,
            "logs": result_lines,
            "log_file": log_file,
            "total_lines": len(all_lines),
            "filtered_lines": len(filtered_lines)
        }), 200
        
    except Exception as e:
        logger.error(f"Error obteniendo logs: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_security.route("/logs/analysis/stream", methods=["GET"])
@api_socio_requerido
def stream_analysis_logs():
    """
    Stream de logs en tiempo real (Server-Sent Events)
    
    Query params:
        video_id: Filtrar por video específico (opcional)
    
    Returns:
        Server-Sent Events stream
    """
    if not _is_admin_session():
        return jsonify({"success": False, "error": "Acceso denegado"}), 403

    from flask import Response
    import time
    
    def generate():
        from infrastructure.services.security_logger import get_security_logger
        import os
        
        sec_logger = get_security_logger()
        log_file = sec_logger.get_log_file_path()
        video_id_filter = request.args.get('video_id')
        
        # Esperar a que el archivo exista
        while not os.path.exists(log_file):
            yield f"data: Waiting for log file...\n\n"
            time.sleep(1)
        
        # Abrir archivo y hacer tail
        with open(log_file, 'r', encoding='utf-8') as f:
            # Ir al final del archivo
            f.seek(0, 2)
            
            while True:
                line = f.readline()
                if line:
                    # Filtrar si es necesario
                    if video_id_filter and video_id_filter not in line:
                        continue
                    yield f"data: {line.strip()}\n\n"
                else:
                    time.sleep(0.5)
    
    return Response(generate(), mimetype='text/event-stream')


@app_security.route("/logs/analysis/status/<video_id>", methods=["GET"])
@api_socio_requerido
def get_video_analysis_status(video_id):
    """
    Obtiene el estado de análisis de un video específico desde los logs
    
    Returns:
        {
            "success": true,
            "video_id": "xxx",
            "found": true,
            "phases_completed": ["MOTION_DETECTION", "CLIP_EXTRACTION"],
            "current_phase": "GEMINI_CLASSIFICATION",
            "errors": [],
            "last_activity": "2026-02-04 15:30:22"
        }
    """
    try:
        video = _get_security_repo().obtener_video(video_id)
        if not video:
            return jsonify({"success": False, "error": "Video no encontrado"}), 404

        if not _has_video_access(video):
            return jsonify({"success": False, "error": "No tiene permisos para acceder a este recurso"}), 403

        from infrastructure.services.security_logger import get_video_analysis_status
        
        status = get_video_analysis_status(video_id)
        
        return jsonify({
            "success": True,
            **status
        }), 200
        
    except Exception as e:
        logger.error(f"Error obteniendo status de análisis: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_security.route("/logs/errors", methods=["GET"])
@api_socio_requerido
def get_error_logs():
    """
    Obtiene los logs de errores de seguridad
    
    Query params:
        lines: Número de líneas a retornar (default: 50)
    
    Returns:
        {
            "success": true,
            "errors": [...],
            "total_errors": 10
        }
    """
    try:
        if not _is_admin_session():
            return jsonify({"success": False, "error": "Acceso denegado"}), 403

        import os
        
        log_dir = os.getenv('SECURITY_LOG_DIR', './logs/security')
        error_log = os.path.join(log_dir, 'security_errors.log')
        
        lines = int(request.args.get('lines', 50))
        
        if not os.path.exists(error_log):
            return jsonify({
                "success": True,
                "errors": [],
                "total_errors": 0,
                "message": "No error log file"
            }), 200
        
        with open(error_log, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        
        result_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        return jsonify({
            "success": True,
            "errors": [l.strip() for l in result_lines],
            "total_errors": len(all_lines)
        }), 200
        
    except Exception as e:
        logger.error(f"Error obteniendo error logs: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500
