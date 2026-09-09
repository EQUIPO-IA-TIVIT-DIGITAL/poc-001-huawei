"""
API Endpoints para Análisis de Audio
Módulo: Análisis de Audio

Funcionalidad:
- Upload de audio o video (máx 2h de duración)
- Extracción y transcripción de audio con timestamps
- Consultas inteligentes sobre el contenido transcrito
- Respuestas con momento exacto en el contenido

Endpoints:
- POST   /api/audio/upload/init       → Inicia upload y crea registro
- POST   /api/audio/upload/stream     → Sube archivo (proxy para CORS)
- POST   /api/audio/upload/complete   → Completa upload e inicia procesamiento
- GET    /api/audio/analyses          → Lista análisis del usuario
- GET    /api/audio/analyses/<id>     → Detalle de un análisis
- DELETE /api/audio/analyses/<id>     → Elimina un análisis
- GET    /api/audio/analyses/<id>/status       → Estado actual
- GET    /api/audio/analyses/<id>/segments     → Segmentos de transcripción (paginados)
- POST   /api/audio/analyses/<id>/query        → Consulta sobre el contenido
- GET    /api/audio/analyses/<id>/transcription → Transcripción completa
- POST   /api/audio/analyses/<id>/reprocess    → Reprocesar análisis fallido
"""

from flask import Blueprint, request, jsonify, session, Response, stream_with_context
import logging
from datetime import datetime
import uuid
import traceback
import time
import os
import json
import re
from cachetools import TTLCache

from infrastructure.web.auth_decorators import api_socio_requerido
from infrastructure.rate_limiter import limiter, API_LIMIT, UPLOAD_LIMIT, POLLING_LIMIT, AI_CHAT_LIMIT
from infrastructure.repositories.audio_analysis_repository import AudioAnalysisRepository
from infrastructure.services.resumable_upload_service import ResumableUploadService
from infrastructure.services.multipart_upload_service import MultipartUploadService
from domain.entities import (
    AudioAnalysis, EstadoAudioAnalysis, MAX_AUDIO_VIDEO_DURATION_SECONDS
)
logger = logging.getLogger(__name__)


def _get_storage_client():
    try:
        from infrastructure.dependencies import get_storage_adapter
        return get_storage_adapter()
    except Exception:
        return None

# Fallback memoria para rate limit (desarrollo single-process)
_user_analysis_timestamps: dict[str, list[int]] = {}

# Blueprint para la sección de análisis de audio
app_audio = Blueprint("audio", __name__, url_prefix="/api/audio")

# SEC-03: validación de formato de analysis_id
_ANALYSIS_ID_RE = re.compile(r'^aud_\d{8}_\d{6}_[a-f0-9]{8}$')


def _validate_analysis_id(analysis_id: str) -> bool:
    """Valida que el analysis_id tenga el formato esperado (SEC-03)."""
    return bool(_ANALYSIS_ID_RE.match(analysis_id or ""))


# Inicializar servicios
audio_repo = AudioAnalysisRepository()
upload_service = ResumableUploadService()
multipart_service = MultipartUploadService()

# Lazy init de servicios (evitar conexiones GCP al importar)
_audio_repo = None
_upload_service = None
_multipart_service = None

def _get_audio_repo():
    global _audio_repo
    if _audio_repo is None:
        _audio_repo = AudioAnalysisRepository()
    return _audio_repo

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
MAX_PROXY_UPLOAD_BYTES = int(os.getenv("AUDIO_MAX_PROXY_UPLOAD_BYTES", str(10 * 1024 * 1024 * 1024)))
MAX_ANALYSES_PER_HOUR = int(os.getenv("AUDIO_MAX_ANALYSES_PER_HOUR", "10"))
ALLOWED_MEDIA_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv", ".mpeg", ".mpg", ".3gp", ".ts",
    ".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg", ".oga", ".opus", ".wma", ".amr", ".aiff", ".aif",
    ".mp2", ".mka",
}


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _get_current_username() -> str:
    """Obtiene el username del usuario autenticado desde la sesión"""
    return session.get("username", session.get("usuario_id", "unknown"))


def _is_supported_media_filename(filename: str) -> bool:
    _, ext = os.path.splitext((filename or "").lower())
    return ext in ALLOWED_MEDIA_EXTENSIONS


def _is_supported_media_content_type(content_type: str) -> bool:
    if not content_type:
        return True
    normalized = content_type.lower().strip()
    if normalized in {"application/octet-stream", "binary/octet-stream"}:
        return True
    return normalized.startswith("video/") or normalized.startswith("audio/")


def _is_within_analysis_limit(usuario: str) -> bool:
    """
    Límite por usuario en ventana de 1 hora.
    Usa Redis (distribuido) cuando está disponible y fallback local en memoria.
    """
    now = int(time.time())

    try:
        from infrastructure.services.job_queue import get_redis_connection

        redis_conn = get_redis_connection()
        key = f"audio:analysis:init:{usuario}"

        # Limpiar ventana y consultar conteo actual
        pipe = redis_conn.pipeline()
        pipe.zremrangebyscore(key, 0, now - 3600)
        pipe.zcard(key)
        _, current = pipe.execute()

        if int(current or 0) >= MAX_ANALYSES_PER_HOUR:
            return False

        member = f"{now}:{uuid.uuid4().hex[:8]}"
        pipe = redis_conn.pipeline()
        pipe.zadd(key, {member: now})
        pipe.expire(key, 3700)
        pipe.execute()
        return True
    except Exception:
        from infrastructure.services.job_queue import is_queue_required
        if is_queue_required():
            # SEC-05: En producción sin Redis, el rate limit multi-proceso no es confiable.
            # Denegar para evitar que N workers permitan N×10 análisis/hora por usuario.
            logger.warning(f"⚠️ Redis no disponible para rate limit distribuido (usuario={usuario})")
            return False
        # Fallback local (solo válido en desarrollo single-process)
        if usuario not in _user_analysis_timestamps:
            _user_analysis_timestamps[usuario] = []

        _user_analysis_timestamps[usuario] = [
            ts for ts in _user_analysis_timestamps[usuario] if now - ts < 3600
        ]
        if len(_user_analysis_timestamps[usuario]) >= MAX_ANALYSES_PER_HOUR:
            return False
        _user_analysis_timestamps[usuario].append(now)
        return True


def _get_float_value(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS: UPLOAD E INICIO DE ANÁLISIS
# ═══════════════════════════════════════════════════════════════


@app_audio.route("/upload/init", methods=["POST"])
@api_socio_requerido
@limiter.limit(UPLOAD_LIMIT, methods=["POST"])
def iniciar_upload():
    """
    Inicia un upload y crea el registro de análisis de audio.
    Requiere autenticación de socio.
    """
    request_start = time.perf_counter()
    trace_id = uuid.uuid4().hex[:8]

    try:
        data = request.get_json() or {}

        # Validar campos requeridos
        if "filename" not in data:
            return jsonify({"success": False, "error": "Campo requerido: filename"}), 400

        titulo = data.get("titulo", "")
        descripcion = data.get("descripcion", "")
        client_video_duration = _get_float_value(data.get("client_video_duration"), 0.0)

        content_type = (data.get("content_type") or "application/octet-stream").strip().lower()
        if not _is_supported_media_filename(data["filename"]):
            return jsonify({"success": False, "error": "Extensión de archivo no permitida para análisis de audio"}), 400
        if not _is_supported_media_content_type(content_type):
            return jsonify({"success": False, "error": "Tipo de contenido inválido. Debe ser audio/* o video/*"}), 400

        # Rate limiting por usuario (distribuido en Redis si está disponible)
        usuario = _get_current_username()
        if not _is_within_analysis_limit(usuario):
            return jsonify({
                "success": False,
                "error": f"Has alcanzado el límite de {MAX_ANALYSES_PER_HOUR} análisis por hora."
            }), 429

        # Generar URL de upload resumable
        upload_data = _get_upload_service().generar_resumable_upload_url(
            filename=data["filename"],
            content_type=content_type,
            metadata={
                "module": "audio_analysis",
                "titulo": titulo,
                "duracion_segundos": str(round(client_video_duration, 3)) if client_video_duration > 0 else "",
            },
        )

        if not upload_data:
            return jsonify({"success": False, "error": "No se pudo generar URL de upload"}), 500

        # Crear registro del análisis
        analysis_id = f"aud_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        vid = analysis_id[:8]

        logger.info(f"[{vid}] 🎵 UPLOAD AUDIO INICIADO [trace={trace_id}] usuario={usuario}")
        logger.info(f"[{vid}]    Título: {titulo}")
        logger.info(f"[{vid}]    Archivo: {data['filename']}")

        analysis = AudioAnalysis(
            id=analysis_id,
            usuario=usuario,
            titulo=titulo,
            descripcion=descripcion,
            video_filename=data["filename"],
            video_url=upload_data["storage_path"],
            video_duration=client_video_duration,
            estado=EstadoAudioAnalysis.PENDING,
            created_at=datetime.utcnow().isoformat(),
        )

        if analysis.video_duration > MAX_AUDIO_VIDEO_DURATION_SECONDS:
            hours = analysis.video_duration / 3600
            return jsonify({
                "success": False,
                "error": f"El archivo excede la duración máxima de 2 horas ({hours:.1f}h)"
            }), 400

        response_data = {
            "success": True,
            "analysis_id": analysis_id,
            "upload_url": upload_data["upload_url"],
            "storage_path": upload_data["storage_path"],
            "storage_bucket": upload_data["bucket"],
            "blob_name": upload_data["blob_name"],
            "expiration_hours": upload_data["expiration_hours"],
        }
        try:
            _get_audio_repo().guardar_analisis(analysis)
            elapsed_ms = (time.perf_counter() - request_start) * 1000
            logger.info(f"[{vid}] ✅ Análisis de audio registrado [{elapsed_ms:.0f}ms]")
        except Exception as save_error:
            logger.error(f"[{vid}] ❌ Error guardando análisis en Firestore: {save_error}", exc_info=True)
            return jsonify({
                "success": False,
                "error": "No se pudo guardar el análisis. Verifica la configuración de Firestore."
            }), 500

        try:
            return jsonify(response_data), 200
        except Exception:
            _get_audio_repo().eliminar_analisis(analysis_id)
            raise

    except Exception as e:
        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.error(f"❌ Upload init error [trace={trace_id}] {elapsed_ms:.0f}ms: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_audio.route("/upload/stream", methods=["POST"])
@api_socio_requerido
@limiter.limit(UPLOAD_LIMIT, methods=["POST"])
def subir_video_stream():
    """
    Sube archivo directamente al backend (proxy para evitar CORS).
    """
    request_start = time.perf_counter()
    trace_id = uuid.uuid4().hex[:8]

    try:
        analysis_id = request.form.get("analysis_id")
        if not analysis_id:
            return jsonify({"success": False, "error": "analysis_id es requerido"}), 400
        if not _validate_analysis_id(analysis_id):
            return jsonify({"success": False, "error": "ID de análisis inválido"}), 400

        vid = analysis_id[:8]
        logger.info(f"[{vid}] 📥 Upload stream audio iniciado [trace={trace_id}]")

        if "file" not in request.files:
            return jsonify({"success": False, "error": "No se encontró archivo"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "Archivo vacío"}), 400

        if not _is_supported_media_filename(file.filename):
            return jsonify({"success": False, "error": "Extensión de archivo no permitida para análisis de audio"}), 400
        if not _is_supported_media_content_type(file.content_type or ""):
            return jsonify({"success": False, "error": "Tipo de contenido inválido. Debe ser audio/* o video/*"}), 400

        analysis = _get_audio_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        # Verificar propiedad
        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso para este análisis"}), 403

        # Tamaño del archivo
        file_size = request.content_length
        if not file_size:
            file.stream.seek(0, 2)
            file_size = file.stream.tell()
            file.stream.seek(0)

        mb_size = file_size / (1024 * 1024) if file_size else 0
        if file_size and file_size > MAX_PROXY_UPLOAD_BYTES:
            max_gb = MAX_PROXY_UPLOAD_BYTES / (1024 * 1024 * 1024)
            return jsonify({
                "success": False,
                "error": f"Archivo excede el máximo permitido para proxy upload ({max_gb:.1f} GB)"
            }), 413

        logger.info(f"[{vid}]    Archivo: {file.filename} ({mb_size:.1f} MB)")

        # Upload al almacenamiento.
        USE_MULTIPART_THRESHOLD = 100 * 1024 * 1024
        use_multipart = file_size and file_size > USE_MULTIPART_THRESHOLD

        if use_multipart:
            logger.info(f"[{vid}]    📤 MULTIPART UPLOAD ({mb_size:.1f} MB)")
            result = _get_multipart_service().subir_archivo_multipart(
                file_stream=file.stream,
                storage_path=analysis.video_url,
                content_type=file.content_type or "application/octet-stream",
                chunk_size=50 * 1024 * 1024,
                max_workers=5,
            )
            bytes_uploaded = result['bytes_uploaded']
        else:
            logger.info(f"[{vid}]    📤 Upload simple ({mb_size:.1f} MB)")
            bytes_uploaded = _get_upload_service().subir_archivo_directo(
                file_stream=file.stream,
                storage_path=analysis.video_url,
                content_type=file.content_type or "application/octet-stream",
            )

        analysis.actualizar_estado(EstadoAudioAnalysis.PENDING, 'Video subido')
        _get_audio_repo().guardar_analisis(analysis)

        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.info(f"[{vid}] ✅ Upload stream completado [{elapsed_ms:.0f}ms]")

        return jsonify({
            "success": True,
            "analysis_id": analysis_id,
            "bytes_uploaded": bytes_uploaded,
            "status": analysis.estado.value,
        }), 200

    except Exception as e:
        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.error(f"❌ Upload stream error [trace={trace_id}] {elapsed_ms:.0f}ms: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_audio.route("/upload/complete", methods=["POST"])
@api_socio_requerido
@limiter.limit(UPLOAD_LIMIT, methods=["POST"])
def completar_upload():
    """
    Marca upload como completado e inicia procesamiento de audio automáticamente.
    """
    request_start = time.perf_counter()
    trace_id = uuid.uuid4().hex[:8]

    try:
        data = request.get_json() or {}
        analysis_id = data.get("analysis_id")
        auto_process = data.get("auto_process", True)
        client_video_duration = _get_float_value(data.get("client_video_duration"), 0.0)

        if not analysis_id:
            return jsonify({"success": False, "error": "analysis_id es requerido"}), 400
        if not _validate_analysis_id(analysis_id):
            return jsonify({"success": False, "error": "ID de análisis inválido"}), 400

        vid = analysis_id[:8]
        logger.info(f"[{vid}] 📥 COMPLETANDO UPLOAD AUDIO [trace={trace_id}]")

        analysis = _get_audio_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        # Verificar propiedad
        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso para este análisis"}), 403

        # Verificar upload
        if analysis.video_url:
            status_ok = _get_upload_service().verificar_upload_completo(analysis.video_url)
            if not status_ok:
                return jsonify({"success": False, "error": "Archivo no subido completamente"}), 400

        logger.info(f"[{vid}]    ✅ Archivo verificado en el almacenamiento")

        # Obtener metadata
        metadata = _get_upload_service().obtener_metadata_archivo(analysis.video_url)
        if metadata:
            size_mb = metadata.get("size_mb")
            if size_mb is None and metadata.get("size"):
                size_mb = round(float(metadata.get("size", 0)) / (1024 * 1024), 2)
            analysis.video_size_mb = float(size_mb or 0)

            duration = metadata.get("duracion_segundos")
            if duration is None:
                duration = (metadata.get("metadata") or {}).get("duracion_segundos")

            if (duration is None or float(duration) <= 0) and client_video_duration > 0:
                duration = client_video_duration

            if (duration is None or float(duration) <= 0) and analysis.video_duration > 0:
                duration = analysis.video_duration

            analysis.video_duration = float(duration or 0)

            if analysis.video_duration <= 0:
                return jsonify({
                    "success": False,
                    "error": "No se pudo determinar la duración del archivo. Reintenta con un formato compatible."
                }), 400

            # Verificar duración máxima (2 horas)
            if analysis.video_duration > MAX_AUDIO_VIDEO_DURATION_SECONDS:
                hours = analysis.video_duration / 3600
                return jsonify({
                    "success": False,
                    "error": f"El archivo excede la duración máxima de 2 horas ({hours:.1f}h)"
                }), 400

        _get_audio_repo().guardar_analisis(analysis)

        # Iniciar procesamiento automático
        job_id = None
        processing_started = False

        if auto_process:
            logger.info(f"[{vid}] 🚀 Iniciando análisis de audio automático...")
            try:
                from infrastructure.services.job_queue import (
                    enqueue_audio_analysis,
                    is_redis_available,
                    is_queue_required,
                    clear_active_audio_job,
                )

                if is_redis_available():
                    job_id = enqueue_audio_analysis(analysis_id)
                    if job_id:
                        processing_started = True
                        logger.info(f"[{vid}] ✅ Encolado (Job ID: {job_id})")
                    else:
                        logger.error(f"[{vid}] ❌ No se pudo encolar análisis en Redis")
                        return jsonify({
                            "success": False,
                            "error": "No se pudo encolar el análisis. Reintenta en unos minutos."
                        }), 503
                else:
                    if is_queue_required():
                        logger.error(f"[{vid}] ❌ Redis no disponible y cola async es obligatoria")
                        return jsonify({
                            "success": False,
                            "error": "Cola asíncrona no disponible. Reintenta en unos minutos."
                        }), 503

                    logger.warning(f"[{vid}] ⚠️ Redis no disponible, procesando inline")
                    from use_cases.audio_analyzer import AudioAnalyzer
                    analyzer = AudioAnalyzer()
                    analyzer.process(analysis_id)
                    clear_active_audio_job(analysis_id)
                    processing_started = True

            except Exception as e:
                logger.error(f"[{vid}] ❌ Error iniciando análisis: {e}", exc_info=True)

        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.info(f"[{vid}] ✅ Upload audio complete [{elapsed_ms:.0f}ms]")

        return jsonify({
            "success": True,
            "analysis_id": analysis_id,
            "processing_started": processing_started,
            "job_id": job_id,
            "video_duration": analysis.video_duration,
            "video_size_mb": round(analysis.video_size_mb, 2),
        }), 200

    except Exception as e:
        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.error(f"❌ Upload complete error [trace={trace_id}] {elapsed_ms:.0f}ms: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS: GESTIÓN DE ANÁLISIS
# ═══════════════════════════════════════════════════════════════


@app_audio.route("/analyses", methods=["GET"])
@api_socio_requerido
@limiter.limit(API_LIMIT, methods=["GET"])
def listar_analisis():
    """Lista todos los análisis de audio del usuario actual"""
    try:
        usuario = _get_current_username()
        limit = request.args.get("limit", 50, type=int)

        analyses = _get_audio_repo().listar_analisis_por_usuario(usuario, limit=limit)

        return jsonify({
            "success": True,
            "analyses": [a.to_dict() for a in analyses],
            "total": len(analyses),
        }), 200

    except Exception as e:
        logger.error(f"❌ Error listando análisis de audio: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_audio.route("/analyses/<analysis_id>", methods=["GET"])
@api_socio_requerido
@limiter.limit(API_LIMIT, methods=["GET"])
def obtener_analisis(analysis_id: str):
    """Obtiene detalle de un análisis de audio"""
    if not _validate_analysis_id(analysis_id):
        return jsonify({"success": False, "error": "ID de análisis inválido"}), 400
    try:
        analysis = _get_audio_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        # Verificar propiedad
        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        return jsonify({
            "success": True,
            "analysis": analysis.to_dict(),
        }), 200

    except Exception as e:
        logger.error(f"❌ Error obteniendo análisis de audio: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_audio.route("/analyses/<analysis_id>", methods=["DELETE"])
@api_socio_requerido
@limiter.limit(API_LIMIT, methods=["DELETE"])
def eliminar_analisis(analysis_id: str):
    """Elimina un análisis de audio y sus segmentos"""
    if not _validate_analysis_id(analysis_id):
        return jsonify({"success": False, "error": "ID de análisis inválido"}), 400
    try:
        analysis = _get_audio_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        _get_audio_repo().eliminar_analisis(analysis_id)

        # Eliminar archivos del almacenamiento.
        try:
            # Eliminar video original y audio extraído explícitamente
            if analysis.video_url:
                _get_upload_service().eliminar_archivo(analysis.video_url)
            if analysis.audio_url:
                _get_upload_service().eliminar_archivo(analysis.audio_url)

            storage = _get_storage_client()
            if storage and storage.is_available():
                prefix = f"audio_analysis/{analysis_id}/"
                if hasattr(storage, "_get_client"):
                    c = storage._get_client()
                    resp = c.list_objects_v2(Bucket=storage.bucket, Prefix=prefix)
                    for obj in resp.get("Contents", []):
                        storage.delete_file(obj["Key"])
                elif hasattr(storage, "base_dir"):
                    from pathlib import Path
                    for p in Path(storage.base_dir).rglob("audio_analysis/*"):
                        if p.is_file() and analysis_id in str(p):
                            storage.delete_file(str(p.relative_to(storage.base_dir)))
        except Exception as e:
            logger.warning(f"⚠️ Error limpiando almacenamiento: {e}")

        return jsonify({"success": True, "message": "Análisis eliminado"}), 200

    except Exception as e:
        logger.error(f"❌ Error eliminando análisis: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_audio.route("/analyses/<analysis_id>/status", methods=["GET"])
@api_socio_requerido
@limiter.limit(POLLING_LIMIT, methods=["GET"])
def obtener_estado(analysis_id: str):
    """Obtiene el estado actual de procesamiento"""
    if not _validate_analysis_id(analysis_id):
        return jsonify({"success": False, "error": "ID de análisis inválido"}), 400
    try:
        analysis = _get_audio_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        return jsonify({
            "success": True,
            "status": analysis.estado.value if hasattr(analysis.estado, 'value') else analysis.estado,
            "progress": analysis.progress,
            "current_phase": analysis.current_phase,
            "error_message": analysis.error_message,
        }), 200

    except Exception as e:
        logger.error(f"❌ Error obteniendo estado: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_audio.route("/analyses/<analysis_id>/status/stream", methods=["GET"])
@api_socio_requerido
@limiter.limit(POLLING_LIMIT, methods=["GET"])
def stream_estado(analysis_id: str):
    """Stream de estado por Server-Sent Events con Redis pub/sub (SCA-01)."""
    if not _validate_analysis_id(analysis_id):
        return jsonify({"success": False, "error": "ID de análisis inválido"}), 400

    analysis = _get_audio_repo().obtener_analisis(analysis_id)
    if not analysis:
        return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

    current_user = _get_current_username()
    if analysis.usuario != current_user:
        return jsonify({"success": False, "error": "No tienes permiso"}), 403

    def _build_payload(current_analysis):
        return {
            "success": True,
            "status": current_analysis.estado.value if hasattr(current_analysis.estado, 'value') else current_analysis.estado,
            "progress": current_analysis.progress,
            "current_phase": current_analysis.current_phase,
            "error_message": current_analysis.error_message,
        }

    @stream_with_context
    def generate():
        terminal_states = {"completed", "error", "cancelled"}
        _last = [None]  # mutable holder para comparar payloads sin nonlocal

        def _read_firestore():
            """Lee estado actual desde Firestore/cache y retorna (status, sse_line | None)."""
            current = _get_audio_repo().obtener_analisis(analysis_id)
            if not current:
                err = json.dumps({"success": False, "error": "Análisis no encontrado"}, ensure_ascii=False)
                return None, f"event: error\ndata: {err}\n\n"
            payload = _build_payload(current)
            pj = json.dumps(payload, ensure_ascii=False)
            line = f"data: {pj}\n\n" if pj != _last[0] else None
            _last[0] = pj
            return payload["status"], line

        # Estado inicial
        status, line = _read_firestore()
        if status is None:
            yield line
            return
        if line:
            yield line
        if status in terminal_states:
            return

        # Intentar suscripción Redis pub/sub (SCA-01)
        pubsub = None
        try:
            from infrastructure.services.job_queue import get_redis_connection
            r = get_redis_connection()
            pubsub = r.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(f"audio:status:{analysis_id}")
        except Exception as exc:
            logger.debug(f"[{analysis_id[:8]}] Redis pub/sub no disponible, fallback polling: {exc}")
            pubsub = None

        REDIS_WAIT_S = 30   # bloqueo máximo esperando mensaje Redis
        MAX_IDLE_POLLS = 60  # 60 × 30s = 30 min sin cambio → cerrar stream
        DEADLINE_S = 2700    # 45 min absoluto

        idle_polls = 0
        deadline = time.time() + DEADLINE_S

        try:
            while time.time() < deadline:
                if pubsub:
                    try:
                        msg = pubsub.get_message(timeout=REDIS_WAIT_S)
                    except Exception:
                        msg = None
                        pubsub = None  # Redis falló → caer a polling

                    if msg and msg.get('type') == 'message':
                        # Entregar payload directo desde Redis (sin leer Firestore)
                        try:
                            data = json.loads(msg['data'])
                            payload = {
                                "success": True,
                                "status": data.get('estado', status),
                                "progress": data.get('progress', 0),
                                "current_phase": data.get('current_phase', ''),
                                "error_message": data.get('error_message', ''),
                            }
                            pj = json.dumps(payload, ensure_ascii=False)
                            if pj != _last[0]:
                                yield f"data: {pj}\n\n"
                                _last[0] = pj
                                idle_polls = 0
                            status = payload["status"]
                        except Exception:
                            # Mensaje malformado → fallback a Firestore
                            status, line = _read_firestore()
                            if status is None:
                                yield line
                                break
                            if line:
                                yield line
                                idle_polls = 0
                    else:
                        # Timeout Redis (sin mensaje en REDIS_WAIT_S s) → verificar Firestore
                        status, line = _read_firestore()
                        if status is None:
                            yield line
                            break
                        if line:
                            yield line
                            idle_polls = 0
                        else:
                            idle_polls += 1
                else:
                    # Fallback polling puro (Redis no disponible)
                    time.sleep(REDIS_WAIT_S)
                    status, line = _read_firestore()
                    if status is None:
                        yield line
                        break
                    if line:
                        yield line
                        idle_polls = 0
                    else:
                        idle_polls += 1

                if status in terminal_states:
                    break

                if idle_polls >= MAX_IDLE_POLLS:
                    yield ": stream idle timeout\n\n"
                    break
        finally:
            if pubsub:
                try:
                    pubsub.unsubscribe()
                    pubsub.close()
                except Exception:
                    pass

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app_audio.route("/analyses/<analysis_id>/segments", methods=["GET"])
@api_socio_requerido
@limiter.limit(POLLING_LIMIT, methods=["GET"])
def obtener_segmentos(analysis_id: str):
    """Obtiene segmentos de transcripción paginados"""
    if not _validate_analysis_id(analysis_id):
        return jsonify({"success": False, "error": "ID de análisis inválido"}), 400
    try:
        analysis = _get_audio_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)
        cursor = request.args.get("cursor", "").strip()

        segments, total, next_cursor = _get_audio_repo().obtener_segmentos_paginados(
            analysis_id, page=page, per_page=per_page, cursor=cursor or None
        )

        total_pages = (total + per_page - 1) // per_page if per_page > 0 else 1

        return jsonify({
            "success": True,
            "segments": [s.to_dict() for s in segments],
            "count": len(segments),
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "next_cursor": next_cursor,
        }), 200

    except Exception as e:
        logger.error(f"❌ Error obteniendo segmentos: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_audio.route("/analyses/<analysis_id>/transcription", methods=["GET"])
@api_socio_requerido
@limiter.limit(API_LIMIT, methods=["GET"])
def obtener_transcripcion(analysis_id: str):
    """Obtiene la transcripción completa del audio"""
    if not _validate_analysis_id(analysis_id):
        return jsonify({"success": False, "error": "ID de análisis inválido"}), 400
    try:
        analysis = _get_audio_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        from domain.entities import EstadoAudioAnalysis
        if analysis.estado != EstadoAudioAnalysis.COMPLETED:
            return jsonify({"success": False, "error": "El análisis aún no ha completado"}), 400

        return jsonify({
            "success": True,
            "transcription": analysis.full_transcription,
            "total_segments": analysis.total_segments,
            "average_confidence": analysis.average_confidence,
            "summary": analysis.summary,
        }), 200

    except Exception as e:
        logger.error(f"❌ Error obteniendo transcripción: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: CONSULTAS SOBRE EL CONTENIDO
# ═══════════════════════════════════════════════════════════════


@app_audio.route("/analyses/<analysis_id>/query", methods=["POST"])
@api_socio_requerido
@limiter.limit(AI_CHAT_LIMIT, methods=["POST"])
def consultar_contenido(analysis_id: str):
    """
    Realiza una consulta sobre el contenido de audio transcrito.
    El sistema responde con la respuesta y el momento exacto del video.

    Body JSON:
    {
        "question": "¿Qué se dice sobre el presupuesto?"
    }
    """
    if not _validate_analysis_id(analysis_id):
        return jsonify({"success": False, "error": "ID de análisis inválido"}), 400
    request_start = time.perf_counter()

    try:
        analysis = _get_audio_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        data = request.get_json() or {}
        question = data.get("question", "").strip()

        if not question:
            return jsonify({"success": False, "error": "La pregunta es requerida"}), 400

        if len(question) > 1000:
            return jsonify({"success": False, "error": "La pregunta es demasiado larga (máx 1000 caracteres)"}), 400

        logger.info(
            f"[{analysis_id[:8]}] 🔍 Consulta recibida (chars={len(question)}, user={current_user})"
        )

        from use_cases.audio_analyzer import AudioAnalyzer
        analyzer = AudioAnalyzer()
        result = analyzer.query(analysis_id, question)

        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.info(f"[{analysis_id[:8]}] Consulta respondida en {elapsed_ms:.0f}ms")

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"❌ Error en consulta de audio: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: REPROCESAR
# ═══════════════════════════════════════════════════════════════


@app_audio.route("/analyses/<analysis_id>/reprocess", methods=["POST"])
@api_socio_requerido
@limiter.limit(API_LIMIT, methods=["POST"])
def reprocesar_analisis(analysis_id: str):
    """Reprocesa un análisis fallido o completado"""
    if not _validate_analysis_id(analysis_id):
        return jsonify({"success": False, "error": "ID de análisis inválido"}), 400
    try:
        analysis = _get_audio_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        from domain.entities import EstadoAudioAnalysis
        if analysis.estado not in [EstadoAudioAnalysis.ERROR, EstadoAudioAnalysis.COMPLETED, EstadoAudioAnalysis.CANCELLED]:
            return jsonify({
                "success": False,
                "error": "Solo se pueden reprocesar análisis en estado error, completado o cancelado"
            }), 400

        # Reset estado
        analysis.actualizar_estado(EstadoAudioAnalysis.PENDING, "Reprocesando...", 0.0)
        analysis.error_message = ""
        _get_audio_repo().guardar_analisis(analysis)

        # Encolar
        try:
            from infrastructure.services.job_queue import (
                enqueue_audio_analysis,
                is_redis_available,
                is_queue_required,
                clear_active_audio_job,
            )

            if is_redis_available():
                job_id = enqueue_audio_analysis(analysis_id)
                if not job_id:
                    return jsonify({
                        "success": False,
                        "error": "No se pudo encolar el reprocesamiento. Reintenta en unos minutos."
                    }), 503
                return jsonify({
                    "success": True,
                    "message": "Reprocesamiento iniciado",
                    "job_id": job_id,
                }), 200
            else:
                if is_queue_required():
                    return jsonify({
                        "success": False,
                        "error": "Cola asíncrona no disponible. Reintenta en unos minutos."
                    }), 503

                from use_cases.audio_analyzer import AudioAnalyzer
                analyzer = AudioAnalyzer()
                analyzer.process(analysis_id)
                clear_active_audio_job(analysis_id)
                return jsonify({"success": True, "message": "Reprocesamiento completado (inline)"}), 200

        except Exception as e:
            logger.error(f"Error reprocesando: {e}")
            return jsonify({"success": False, "error": "Error interno del servidor"}), 500

    except Exception as e:
        logger.error(f"❌ Error reprocesando análisis: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_audio.route("/analyses/<analysis_id>/search", methods=["GET"])
@api_socio_requerido
@limiter.limit(API_LIMIT, methods=["GET"])
def buscar_en_transcripcion(analysis_id: str):
    """
    Busca texto dentro de la transcripción del audio.
    
    Query params:
        q: Texto a buscar
    """
    if not _validate_analysis_id(analysis_id):
        return jsonify({"success": False, "error": "ID de análisis inválido"}), 400
    try:
        analysis = _get_audio_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"success": False, "error": "Parámetro 'q' requerido"}), 400
        if len(query) > 200:
            return jsonify({"success": False, "error": "Parámetro 'q' demasiado largo (máx 200)"}), 400

        limit = request.args.get("limit", 100, type=int)
        limit = max(1, min(limit, 500))

        segments = _get_audio_repo().buscar_en_transcripcion(analysis_id, query, limit=limit)

        def format_ts(seconds):
            total = int(seconds)
            h, m, s = total // 3600, (total % 3600) // 60, total % 60
            return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

        return jsonify({
            "success": True,
            "query": query,
            "results": [
                {
                    **s.to_dict(),
                    "timestamp_formatted": format_ts(s.start_time),
                }
                for s in segments
            ],
            "total": len(segments),
        }), 200

    except Exception as e:
        logger.error(f"❌ Error buscando en transcripción: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500
