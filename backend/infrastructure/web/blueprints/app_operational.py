"""
API Endpoints para Análisis Operativo de Videos v2.0
Módulo 2: Análisis contextual definido por el usuario

Tipos de análisis:
- ACCESS_CONTROL: Control de acceso, fotcheck, entradas/salidas
- OCCUPANCY: Aforo, capacidad máxima, alertas
- PEOPLE_FLOW: Flujo de personas, tiempos de espera, colas
- MERCHANDISE_CONTROL: Control de mercancía, inventario
- PARKING: Estacionamiento, ocupación, flujo vehicular
- WORK_SUPERVISION: Supervisión de trabajo, EPP, procedimientos

v2.0 Mejoras:
- Autenticación en todos los endpoints (api_socio_requerido)
- Paginación en eventos con ?page=&per_page=
- Endpoint SSE para streaming de progreso en tiempo real
- Endpoint de reprocesamiento de análisis fallidos
- Cache Redis para análisis completados
- Notificaciones al completar

TRAZABILIDAD:
- Cada endpoint loguea inicio/fin con timestamps
- Errores se registran con stack trace completo
"""

from flask import Blueprint, request, jsonify, session, Response
import logging
from datetime import datetime
import os
import uuid
import traceback
import time
import json
from cachetools import TTLCache

from infrastructure.web.auth_decorators import api_socio_requerido
from infrastructure.repositories.operational_analysis_repository import OperationalAnalysisRepository
from infrastructure.services.resumable_upload_service import ResumableUploadService
from infrastructure.services.multipart_upload_service import MultipartUploadService
from infrastructure.dependencies import get_storage_adapter
from infrastructure.services.log_utils import sanitize_context_for_log as _sanitize_context_for_log
from domain.entities import (
    OperationalAnalysis, EstadoOperationalAnalysis, OPERATIONAL_ANALYSIS_TYPES,
    MAX_CUSTOM_CONTEXT_LENGTH
)

logger = logging.getLogger(__name__)

# Blueprint para la sección operativa
app_operational = Blueprint("operational", __name__, url_prefix="/api/operational")

# Lazy init de servicios (evitar conexiones GCP al importar)
_operational_repo = None
_upload_service = None
_multipart_service = None

def _get_operational_repo():
    global _operational_repo
    if _operational_repo is None:
        _operational_repo = OperationalAnalysisRepository()
    return _operational_repo

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

# Rate limiting por usuario para creación de análisis (auto-evict after 1h)
_user_analysis_timestamps: TTLCache = TTLCache(maxsize=5000, ttl=3600)
MAX_ANALYSES_PER_HOUR = 10
MAX_UPLOAD_GB = int(os.getenv("OPERATIONAL_MAX_UPLOAD_GB", "100"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_GB * 1024 * 1024 * 1024


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _get_current_username() -> str:
    """Obtiene el username del usuario autenticado desde la sesión"""
    return session.get("username", session.get("usuario_id", "unknown"))


def _get_redis_cache():
    """Obtiene instancia de Redis cache (lazy, sin fallar si no existe)"""
    try:
        from infrastructure.services.redis_cache import get_cache_instance
        return get_cache_instance()
    except Exception:
        return None


def _invalidate_analysis_cache(analysis_id: str):
    """Invalida cache de un análisis específico"""
    cache = _get_redis_cache()
    if cache:
        try:
            cache.delete(f"op_analysis:{analysis_id}")
            cache.delete(f"op_events:{analysis_id}")
        except Exception:
            pass


def _consume_analysis_rate_limit(usuario: str) -> bool:
    """Rate limit distribuido por usuario con fallback local en memoria."""
    now = int(time.time())
    hour_bucket = now // 3600

    try:
        from infrastructure.services.job_queue import get_redis_connection

        redis_conn = get_redis_connection()
        key = f"op_rate_limit:{usuario}:{hour_bucket}"
        new_count = int(redis_conn.incr(key))
        if new_count == 1:
            redis_conn.expire(key, (3600 - (now % 3600)) + 60)
        return new_count <= MAX_ANALYSES_PER_HOUR
    except Exception:
        pass

    cache = _get_redis_cache()
    if cache:
        try:
            key = f"op_rate_limit:{usuario}:{hour_bucket}"
            current = cache.get(key)
            if current is None:
                cache.set(key, 1, ttl=(3600 - (now % 3600)) + 60)
                return True

            current_count = int(current)
            if current_count >= MAX_ANALYSES_PER_HOUR:
                return False

            cache.set(key, current_count + 1, ttl=(3600 - (now % 3600)) + 60)
            return True
        except Exception:
            pass

    # Fallback local en memoria — no es confiable en entornos con múltiples instancias
    from infrastructure.services.job_queue import is_queue_required
    if is_queue_required():
        logger.warning(
            f"⚠️ Redis no disponible para rate limit distribuido de operativo "
            f"(usuario={usuario}). Sistema degradado: límites por instancia, no globales."
        )
    if usuario not in _user_analysis_timestamps:
        _user_analysis_timestamps[usuario] = []
    _user_analysis_timestamps[usuario] = [
        ts for ts in _user_analysis_timestamps[usuario] if now - ts < 3600
    ]
    if len(_user_analysis_timestamps[usuario]) >= MAX_ANALYSES_PER_HOUR:
        return False
    _user_analysis_timestamps[usuario].append(now)
    return True


# Extensiones de video permitidas para uploads directos
_ALLOWED_VIDEO_EXTENSIONS = frozenset({
    '.mp4', '.mov', '.avi', '.mkv', '.webm', '.ogv',
    '.flv', '.m4v', '.ts', '.mts', '.m2ts', '.mpeg', '.mpg',
})


def _is_supported_video_signature(file_stream) -> bool:
    """Valida firmas binarias básicas de formatos de video comunes."""
    try:
        pos = file_stream.tell()
        header = file_stream.read(16) or b""
        file_stream.seek(pos)

        if len(header) < 4:
            return False

        # MP4/MOV/ISO BMFF: 'ftyp' en offset 4
        if len(header) >= 8 and header[4:8] == b"ftyp":
            return True

        # Matroska/WebM
        if header.startswith(b"\x1A\x45\xDF\xA3"):
            return True

        # AVI (RIFF....AVI )
        if len(header) >= 12 and header[0:4] == b"RIFF" and header[8:12] == b"AVI ":
            return True

        # OGG / Theora
        if header.startswith(b"OggS"):
            return True

        # FLV
        if header[:3] == b"FLV":
            return True

        # MPEG-TS (Transport Stream: paquetes de 188B comenzando con 0x47)
        if header[0:1] == b"\x47":
            return True

        # MPEG-PS (Program Stream) y MPEG-1/2 Video Elementary Stream
        if header[:4] in (b"\x00\x00\x01\xBA", b"\x00\x00\x01\xB3"):
            return True

        return False
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: TIPOS DE ANÁLISIS (público)
# ═══════════════════════════════════════════════════════════════


@app_operational.route("/types", methods=["GET"])
def listar_tipos():
    """
    Lista todos los tipos de análisis operativo disponibles.
    Este endpoint es público (no requiere auth).

    Returns:
        {
            "success": true,
            "types": { "ACCESS_CONTROL": {...}, ... }
        }
    """
    return jsonify({
        "success": True,
        "types": {
            k: {
                "name": v["name"],
                "description": v["description"],
                "icon": v["icon"],
                "key_metrics": v.get("key_metrics", []),
                "estimated_minutes_per_hour": v.get("estimated_minutes_per_hour", 8)
            }
            for k, v in OPERATIONAL_ANALYSIS_TYPES.items()
        },
        "max_context_length": MAX_CUSTOM_CONTEXT_LENGTH
    }), 200


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS: UPLOAD E INICIO DE ANÁLISIS (requiere auth)
# ═══════════════════════════════════════════════════════════════


@app_operational.route("/upload/init", methods=["POST"])
@api_socio_requerido
def iniciar_upload():
    """
    Inicia un upload y crea el registro de análisis operativo.
    Requiere autenticación de socio.
    """
    request_start = time.perf_counter()
    trace_id = uuid.uuid4().hex[:8]

    try:
        data = request.get_json() or {}

        # Validar campos requeridos
        required_fields = ["filename", "analysis_type"]
        for field in required_fields:
            if field not in data:
                return jsonify({"success": False, "error": f"Campo requerido: {field}"}), 400

        analysis_type = data["analysis_type"]
        if analysis_type not in OPERATIONAL_ANALYSIS_TYPES:
            return jsonify({
                "success": False,
                "error": f"Tipo inválido: {analysis_type}. Válidos: {list(OPERATIONAL_ANALYSIS_TYPES.keys())}"
            }), 400

        custom_context = data.get("custom_context", "")
        _raw_questions = data.get("custom_questions", [])
        content_type = data.get("content_type", "video/mp4")
        # Sanitizar custom_questions: máx 5 preguntas, 200 chars c/u
        if not isinstance(_raw_questions, list):
            _raw_questions = []
        custom_questions = [
            str(q)[:200]
            for q in _raw_questions[:5]
            if isinstance(q, (str, int, float)) and str(q).strip()
        ]

        # ═══ Validar longitud de contexto ═══
        if len(custom_context) > MAX_CUSTOM_CONTEXT_LENGTH:
            return jsonify({
                "success": False,
                "error": f"El contexto excede {MAX_CUSTOM_CONTEXT_LENGTH} caracteres (actual: {len(custom_context)})"
            }), 400

        # ═══ Rate limiting por usuario ═══
        usuario = _get_current_username()
        if not _consume_analysis_rate_limit(usuario):
            return jsonify({
                "success": False,
                "error": f"Has alcanzado el límite de {MAX_ANALYSES_PER_HOUR} análisis por hora. Intenta más tarde."
            }), 429

        if content_type and not str(content_type).lower().startswith("video/"):
            return jsonify({"success": False, "error": "content_type inválido. Debe ser video/*"}), 400

        nombre_camara = data.get("nombre_camara", "SIN_CAMARA")
        ubicacion = data.get("ubicacion", "Sin ubicación")
        usuario = _get_current_username()

        # Generar URL de upload resumable
        upload_data = _get_upload_service().generar_resumable_upload_url(
            filename=data["filename"],
            content_type=content_type,
            metadata={
                "analysis_type": analysis_type,
                "nombre_camara": nombre_camara,
                "ubicacion": ubicacion,
            },
        )

        if not upload_data:
            return jsonify({"success": False, "error": "No se pudo generar URL de upload"}), 500

        # Crear registro del análisis operativo
        analysis_id = f"op_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        vid = analysis_id[:8]

        logger.info(f"[{vid}] 📤 UPLOAD OPERATIVO INICIADO [trace={trace_id}] usuario={usuario}")
        logger.info(f"[{vid}]    Tipo: {analysis_type}")
        logger.info(f"[{vid}]    Contexto: {_sanitize_context_for_log(custom_context)}")
        logger.info(f"[{vid}]    Cámara: {nombre_camara}")
        logger.info(f"[{vid}]    Archivo: {data['filename']}")

        analysis = OperationalAnalysis(
            id=analysis_id,
            usuario=usuario,
            analysis_type=analysis_type,
            custom_context=custom_context,
            custom_questions=custom_questions,
            nombre_camara=nombre_camara,
            ubicacion=ubicacion,
            video_filename=data["filename"],
            video_url=upload_data["storage_path"],
            estado=EstadoOperationalAnalysis.PENDING,
            created_at=datetime.utcnow().isoformat(),
        )

        try:
            _get_operational_repo().guardar_analisis(analysis)
            elapsed_ms = (time.perf_counter() - request_start) * 1000
            logger.info(f"[{vid}] ✅ Análisis registrado en la base de datos [{elapsed_ms:.0f}ms]")
        except Exception as save_error:
            logger.error(f"[{vid}] ❌ Error guardando análisis en la base de datos: {save_error}", exc_info=True)
            return jsonify({
                "success": False,
                "error": "No se pudo guardar el análisis. Verifica la configuración de la base de datos."
            }), 500

        return jsonify({
            "success": True,
            "analysis_id": analysis_id,
            "upload_url": upload_data["upload_url"],
            "storage_path": upload_data["storage_path"],
            "bucket": upload_data["bucket"],
            "blob_name": upload_data["blob_name"],
            "expiration_hours": upload_data["expiration_hours"],
        }), 200

    except Exception as e:
        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.error(f"❌ Upload init error [trace={trace_id}] {elapsed_ms:.0f}ms: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_operational.route("/upload/stream", methods=["POST"])
@api_socio_requerido
def subir_video_stream():
    """
    Sube video directamente al backend (proxy para evitar CORS).
    Requiere autenticación de socio.
    """
    request_start = time.perf_counter()
    trace_id = uuid.uuid4().hex[:8]

    try:
        analysis_id = request.form.get("analysis_id")
        if not analysis_id:
            return jsonify({"success": False, "error": "analysis_id es requerido"}), 400

        vid = analysis_id[:8]
        logger.info(f"[{vid}] 📥 Upload stream iniciado [trace={trace_id}]")

        if "file" not in request.files:
            return jsonify({"success": False, "error": "No se encontró archivo"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "Archivo vacío"}), 400

        if file.mimetype and not file.mimetype.lower().startswith("video/"):
            return jsonify({"success": False, "error": "El archivo debe ser de tipo video/*"}), 400

        # Validar extensión del archivo
        _filename_ext = os.path.splitext(file.filename or "")[1].lower()
        if _filename_ext and _filename_ext not in _ALLOWED_VIDEO_EXTENSIONS:
            return jsonify({"success": False, "error": "Extensión de archivo no permitida"}), 400

        analysis = _get_operational_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        # Verificar que el usuario es dueño del análisis
        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso para este análisis"}), 403

        # Tamaño del archivo
        file_size = request.content_length
        if not file_size:
            file.stream.seek(0, 2)
            file_size = file.stream.tell()
            file.stream.seek(0)

        if file_size and file_size > MAX_UPLOAD_BYTES:
            return jsonify({
                "success": False,
                "error": f"Archivo demasiado grande. Máximo permitido: {MAX_UPLOAD_GB} GB"
            }), 413

        if not _is_supported_video_signature(file.stream):
            return jsonify({
                "success": False,
                "error": "El archivo no parece ser un video válido (firma binaria inválida)"
            }), 400

        mb_size = file_size / (1024 * 1024) if file_size else 0
        logger.info(f"[{vid}]    Archivo: {file.filename} ({mb_size:.1f} MB)")

        # Upload al almacenamiento.
        USE_MULTIPART_THRESHOLD = 100 * 1024 * 1024
        use_multipart = file_size and file_size > USE_MULTIPART_THRESHOLD

        if use_multipart:
            logger.info(f"[{vid}]    📤 MULTIPART UPLOAD ({mb_size:.1f} MB)")
            result = _get_multipart_service().subir_archivo_multipart(
                file_stream=file.stream,
                storage_path=analysis.video_url,
                content_type=file.content_type or "video/mp4",
                chunk_size=50 * 1024 * 1024,
                max_workers=5,
            )
            bytes_uploaded = result['bytes_uploaded']
        else:
            logger.info(f"[{vid}]    📤 Upload simple ({mb_size:.1f} MB)")
            bytes_uploaded = _get_upload_service().subir_archivo_directo(
                file_stream=file.stream,
                storage_path=analysis.video_url,
                content_type=file.content_type or "video/mp4",
            )

        analysis.actualizar_estado(EstadoOperationalAnalysis.PENDING, 'Video subido')
        _get_operational_repo().guardar_analisis(analysis)

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


@app_operational.route("/upload/complete", methods=["POST"])
@api_socio_requerido
def completar_upload():
    """
    Marca upload como completado e INICIA ANÁLISIS AUTOMÁTICAMENTE.
    Requiere autenticación de socio.
    """
    request_start = time.perf_counter()
    trace_id = uuid.uuid4().hex[:8]

    try:
        data = request.get_json() or {}
        analysis_id = data.get("analysis_id")
        auto_process = data.get("auto_process", True)

        if not analysis_id:
            return jsonify({"success": False, "error": "analysis_id es requerido"}), 400

        vid = analysis_id[:8]
        logger.info(f"[{vid}] 📥 COMPLETANDO UPLOAD [trace={trace_id}]")

        analysis = _get_operational_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        # Verificar que el usuario es dueño
        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso para este análisis"}), 403

        # Verificar que el upload esté completo
        if analysis.video_url:
            status_ok = _get_upload_service().verificar_upload_completo(analysis.video_url)
            if not status_ok:
                return jsonify({"success": False, "error": "Archivo no subido completamente"}), 400

        logger.info(f"[{vid}]    ✅ Archivo verificado en el almacenamiento")

        # Obtener metadata
        metadata = _get_upload_service().obtener_metadata_archivo(analysis.video_url)
        if metadata:
            analysis.video_duration = metadata.get('duracion_segundos', 0)
            analysis.video_size_mb = metadata.get('size_bytes', 0) / (1024 * 1024)

        _get_operational_repo().guardar_analisis(analysis)

        # ===== ANÁLISIS AUTOMÁTICO =====
        job_id = None
        processing_started = False

        if auto_process:
            logger.info(f"[{vid}] 🚀 Iniciando análisis operativo automático...")
            try:
                from infrastructure.services.job_queue import (
                    enqueue_operational_analysis,
                    is_redis_available,
                    can_enqueue_operational_analysis,
                )

                if is_redis_available():
                    can_enqueue, queue_state = can_enqueue_operational_analysis()
                    if not can_enqueue:
                        return jsonify({
                            "success": False,
                            "error": "Sistema con alta carga. Intenta nuevamente en unos minutos.",
                            "queue": queue_state,
                        }), 503
                    job_id = enqueue_operational_analysis(analysis_id)
                    if job_id:
                        processing_started = True
                        logger.info(f"[{vid}] ✅ Encolado (Job ID: {job_id})")
                else:
                    logger.error(f"[{vid}] ❌ Redis no disponible — rechazando análisis")
                    return jsonify({
                        "success": False,
                        "error": "Sistema de cola no disponible. Reintenta en unos minutos.",
                    }), 503

            except Exception as e:
                logger.error(f"[{vid}] ❌ Error iniciando análisis: {e}", exc_info=True)

        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.info(f"[{vid}] ✅ Upload complete OK [{elapsed_ms:.0f}ms]")

        return jsonify({
            "success": True,
            "analysis_id": analysis_id,
            "status": "processing" if processing_started else "uploaded",
            "job_id": job_id,
            "message": "Análisis operativo iniciado" if processing_started else "Video subido",
        }), 200

    except Exception as e:
        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.error(f"❌ Upload complete error [trace={trace_id}] {elapsed_ms:.0f}ms: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS: CONSULTAS (requiere auth, con cache y paginación)
# ═══════════════════════════════════════════════════════════════


@app_operational.route("/analyses", methods=["GET"])
@api_socio_requerido
def listar_analisis():
    """
    Lista los análisis operativos del usuario autenticado.

    Query params:
        - analysis_type: Filtrar por tipo (opcional)
        - limit: Límite de resultados (default 50)

    Returns:
        {
            "success": true,
            "analyses": [...],
            "count": N
        }
    """
    trace_id = uuid.uuid4().hex[:8]
    try:
        analysis_type = request.args.get("analysis_type")
        try:
            limit = int(request.args.get("limit", 50))
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Parámetro 'limit' debe ser un entero"}), 400
        current_user = _get_current_username()

        analyses = _get_operational_repo().listar_analisis_por_usuario(
            usuario=current_user,
            analysis_type=analysis_type,
            limit=limit
        )

        logger.info(f"📋 Listado: {len(analyses)} análisis para {current_user} [trace={trace_id}]")

        return jsonify({
            "success": True,
            "analyses": [a.to_dict() for a in analyses],
            "count": len(analyses)
        }), 200

    except Exception as e:
        logger.error(f"❌ Error listando análisis [trace={trace_id}]: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_operational.route("/analyses/<analysis_id>", methods=["GET"])
@api_socio_requerido
def obtener_analisis(analysis_id):
    """
    Obtiene un análisis operativo por su ID.
    Requiere que el usuario sea dueño del análisis.
    Cache Redis de 5min para análisis completados.
    """
    vid = analysis_id[:8]
    try:
        # Intentar cache para análisis completados
        cache = _get_redis_cache()
        cache_key = f"op_analysis:{analysis_id}"
        if cache:
            cached = cache.get(cache_key)
            if cached and isinstance(cached, dict):
                # Verificar ownership
                if cached.get('usuario') == _get_current_username():
                    return jsonify({"success": True, "analysis": cached}), 200

        analysis = _get_operational_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        # Verificar ownership
        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso para este análisis"}), 403

        analysis_dict = analysis.to_dict()

        # Cache si está completado (5 min TTL)
        if cache and analysis.estado == EstadoOperationalAnalysis.COMPLETED:
            cache.set(cache_key, analysis_dict, ttl=300)

        return jsonify({
            "success": True,
            "analysis": analysis_dict
        }), 200

    except Exception as e:
        logger.error(f"[{vid}] ❌ Error obteniendo análisis: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_operational.route("/analyses/<analysis_id>/events", methods=["GET"])
@api_socio_requerido
def obtener_eventos(analysis_id):
    """
    Obtiene los eventos de un análisis operativo con paginación.
    Usa paginación a nivel de repositorio para mejor rendimiento.

    Query params:
        - page: Número de página (default 1)
        - per_page: Eventos por página (default 20, max 100)
    """
    vid = analysis_id[:8]
    try:
        # Verificar ownership
        analysis = _get_operational_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso para este análisis"}), 403

        # Paginación (compatibilidad: page/per_page + opcional cursor)
        try:
            page = max(1, int(request.args.get("page", 1)))
            per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Parámetros 'page' y 'per_page' deben ser enteros"}), 400
        cursor = request.args.get("cursor")

        # Intentar cache para eventos de análisis completados
        cache = _get_redis_cache()
        if cursor:
            cache_key = f"op_events:{analysis_id}:cursor:{cursor}:pp{per_page}"
        else:
            cache_key = f"op_events:{analysis_id}:p{page}:pp{per_page}"
        cached_result = None

        if cache and analysis.estado == EstadoOperationalAnalysis.COMPLETED:
            cached_result = cache.get(cache_key)
            if cached_result and isinstance(cached_result, dict):
                return jsonify({"success": True, **cached_result}), 200

        if cursor:
            paginated_events, next_cursor, total = _get_operational_repo().obtener_eventos_cursor(
                analysis_id, cursor=cursor, per_page=per_page
            )
            paginated = [e.to_dict() for e in paginated_events]
            paginated = _resolve_frame_urls(paginated, analysis_id, request.url_root)
            total_pages = max(1, (total + per_page - 1) // per_page)
            result = {
                "events": paginated,
                "count": len(paginated),
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
                "cursor": cursor,
                "next_cursor": next_cursor,
                "has_more": bool(next_cursor),
            }
        else:
            paginated_events, total = _get_operational_repo().obtener_eventos_paginados(
                analysis_id, page=page, per_page=per_page
            )
            paginated = [e.to_dict() for e in paginated_events]
            paginated = _resolve_frame_urls(paginated, analysis_id, request.url_root)
            total_pages = max(1, (total + per_page - 1) // per_page)

            result = {
                "events": paginated,
                "count": len(paginated),
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages
            }

        # Cache si completado (5 min TTL por página)
        if cache and analysis.estado == EstadoOperationalAnalysis.COMPLETED:
            cache.set(cache_key, result, ttl=300)

        return jsonify({"success": True, **result}), 200

    except Exception as e:
        logger.error(f"[{vid}] ❌ Error obteniendo eventos: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_operational.route("/analyses/<analysis_id>/video-url", methods=["GET"])
@api_socio_requerido
def obtener_video_url(analysis_id):
    """
    Genera una URL firmada (signed URL) temporal para reproducir el video
    desde el almacenamiento directamente en el navegador.
    La URL expira en 60 minutos.
    """
    vid = analysis_id[:8]
    try:
        analysis = _get_operational_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        if not analysis.video_url:
            logger.warning(f"[{vid}] ⚠️ video_url está vacío")
            return jsonify({"success": False, "error": "No hay video asociado"}), 404

        logger.info(f"[{vid}] 📹 video_url: {analysis.video_url}")

        # Intentar cache
        cache = _get_redis_cache()
        cache_key = f"op_video_url:{analysis_id}"
        if cache:
            cached_url = cache.get(cache_key)
            if cached_url:
                logger.info(f"[{vid}] ✅ URL desde cache")
                return jsonify({"success": True, "url": cached_url}), 200

        storage_adapter = get_storage_adapter()
        signed_url = storage_adapter.generate_signed_url_from_storage_uri(
            analysis.video_url, expiration_minutes=60
        )

        if not signed_url:
            logger.error(f"[{vid}] ❌ No se pudo generar signed URL")
            return jsonify({"success": False, "error": "No se pudo generar URL de video"}), 500

        logger.info(f"[{vid}] ✅ Signed URL generada")

        # Cache por 55 min (URL dura 60)
        if cache:
            cache.set(cache_key, signed_url, ttl=3300)

        return jsonify({"success": True, "url": signed_url}), 200

    except Exception as e:
        logger.error(f"[{vid}] ❌ Error generando URL de video: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_operational.route("/analyses/<analysis_id>/stream-video", methods=["GET"])
@api_socio_requerido
def stream_video(analysis_id):
    """
    Redirects to a short-lived storage signed URL for video playback.
    The browser follows the redirect directly to storage (fast, no buffering proxy).
    """
    vid = analysis_id[:8]
    try:
        analysis = _get_operational_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"error": "Sin permiso"}), 403

        if not analysis.video_url:
            return jsonify({"error": "No hay video asociado"}), 404

        from flask import redirect
        storage = get_storage_adapter()
        if not storage.is_available():
            return jsonify({"error": "Almacenamiento no disponible"}), 503

        signed_url = storage.generate_signed_url_from_storage_uri(
            analysis.video_url, expiration_minutes=60
        )
        if not signed_url:
            return jsonify({"error": "No se pudo generar URL"}), 500

        return redirect(signed_url, code=302)

    except Exception as e:
        logger.error(f"[{vid}] ❌ Error generando URL de video: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500


# ─── Helper interno ───────────────────────────────────────────────────────────
def _resolve_frame_urls(events: list, analysis_id: str, base_url: str) -> list:
    """
    Convierte rutas de objetos S3 en frame_urls al endpoint proxy del backend.
    """
    for event in events:
        raw = event.get("frame_urls") or []
        if not raw:
            continue
        resolved = []
        for uri in raw:
            if uri.startswith("s3://"):
                # s3://bucket/blob_path → authenticated backend proxy.
                blob_path = uri.split("/", 3)[-1]
                resolved.append(f"{base_url}api/operational/analyses/{analysis_id}/frames/{blob_path}")
            else:
                resolved.append(uri)
        event["frame_urls"] = resolved
    return events


@app_operational.route("/analyses/<analysis_id>/frames/<path:blob_path>", methods=["GET"])
@api_socio_requerido
def proxy_frame(analysis_id, blob_path):
    """
    Proxy autenticado para servir frames almacenados en el almacenamiento.
    El backend descarga el objeto y lo sirve directamente al cliente autenticado.
    """
    vid = analysis_id[:8]
    try:
        analysis = _get_operational_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"error": "Sin permiso"}), 403

        # Restringir blob_path al prefijo esperado para evitar path traversal
        expected_prefix = f"operational/{analysis_id}/"
        if not blob_path.startswith(expected_prefix):
            logger.warning(f"[{vid}] ⚠️ Intento de acceso a blob fuera de prefijo: {blob_path}")
            return jsonify({"error": "Ruta inválida"}), 400

        from flask import Response
        import tempfile
        from pathlib import Path
        storage = get_storage_adapter()
        if not storage.is_available():
            return jsonify({"error": "Almacenamiento no disponible"}), 503

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

        return Response(
            image_bytes,
            mimetype="image/jpeg",
            headers={"Cache-Control": "private, max-age=3600"}
        )

    except Exception as e:
        logger.error(f"[{vid}] ❌ Error sirviendo frame {blob_path}: {e}")
        return jsonify({"error": "Frame no disponible"}), 404


@app_operational.route("/analyses/<analysis_id>/heatmap", methods=["GET"])
@api_socio_requerido
def obtener_heatmap(analysis_id):
    """
    Calcula los datos del heatmap de actividad temporal usando TODOS los eventos,
    no solo los de la página actual.
    Devuelve los buckets (conteo de eventos por intervalo de tiempo).
    """
    vid = analysis_id[:8]
    try:
        analysis = _get_operational_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        if analysis.estado != EstadoOperationalAnalysis.COMPLETED:
            return jsonify({"success": False, "error": "Análisis no completado"}), 400

        video_duration = analysis.video_duration or 0
        if video_duration <= 0:
            return jsonify({"success": True, "heatmap": None}), 200

        materialized_heatmap = (analysis.scan_stats or {}).get('heatmap')
        if isinstance(materialized_heatmap, dict) and materialized_heatmap.get('buckets'):
            return jsonify({"success": True, "heatmap": materialized_heatmap}), 200

        # Intentar cache
        cache = _get_redis_cache()
        cache_key = f"op_heatmap:{analysis_id}"
        if cache:
            cached = cache.get(cache_key)
            if cached and isinstance(cached, dict):
                return jsonify({"success": True, "heatmap": cached}), 200

        total = _get_operational_repo().contar_eventos(analysis_id)
        if total <= 0:
            return jsonify({"success": True, "heatmap": None}), 200

        bucket_size = max(30, int(video_duration / 20))
        num_buckets = max(1, int(video_duration / bucket_size) + 1)
        buckets = [0] * num_buckets

        for ts in _get_operational_repo().iter_event_timestamps(analysis_id, batch_size=1500):
            idx = min(int(ts / bucket_size), num_buckets - 1)
            buckets[idx] += 1

        max_count = max(buckets) if buckets else 1
        heatmap_data = {
            "buckets": buckets,
            "bucket_size": bucket_size,
            "max_count": max_count,
            "total_events": total,
            "video_duration": video_duration,
        }

        # Cache 5 min
        if cache:
            cache.set(cache_key, heatmap_data, ttl=300)

        return jsonify({"success": True, "heatmap": heatmap_data}), 200

    except Exception as e:
        logger.error(f"[{vid}] ❌ Error generando heatmap: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


@app_operational.route("/analyses/<analysis_id>/status", methods=["GET"])
@api_socio_requerido
def obtener_estado(analysis_id):
    """
    Obtiene el estado actual de un análisis (polling desde frontend).
    """
    vid = analysis_id[:8]
    try:
        analysis = _get_operational_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "No encontrado"}), 404

        # Verificar ownership
        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        return jsonify({
            "success": True,
            "status": analysis.estado.value,
            "progress": analysis.progress,
            "current_phase": analysis.current_phase,
        }), 200

    except Exception as e:
        logger.error(f"[{vid}] ❌ Error obteniendo estado: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: SSE — Streaming de progreso en tiempo real
# ═══════════════════════════════════════════════════════════════


@app_operational.route("/analyses/<analysis_id>/stream", methods=["GET"])
@api_socio_requerido
def stream_estado(analysis_id):
    """
    Server-Sent Events para progreso en tiempo real.
    Optimizado: sleep corto (1s), timeout adaptivo, envía heartbeats.
    Se cierra automáticamente al llegar a completed, error o cancelled.
    """
    vid = analysis_id[:8]

    # Verificar ownership antes de abrir stream
    analysis = _get_operational_repo().obtener_analisis(analysis_id)
    if not analysis:
        return jsonify({"success": False, "error": "No encontrado"}), 404

    current_user = _get_current_username()
    if analysis.usuario != current_user:
        return jsonify({"success": False, "error": "No tienes permiso"}), 403

    def _build_state_from_analysis(a):
        eta_seconds = None
        if a.progress > 5 and a.started_at:
            try:
                started = datetime.fromisoformat(a.started_at)
                elapsed = (datetime.utcnow() - started).total_seconds()
                if a.progress > 0:
                    total_estimated = elapsed / (a.progress / 100)
                    eta_seconds = max(0, total_estimated - elapsed)
            except Exception:
                pass

        status = a.estado.value
        return {
            "status": status,
            "progress": round(a.progress, 1),
            "current_phase": a.current_phase,
            "summary": a.summary if a.estado == EstadoOperationalAnalysis.COMPLETED else {},
            "error_message": a.error_message if status in ('error', 'cancelled') else "",
            "scan_stats": a.scan_stats,
            "eta_seconds": eta_seconds,
            "final": status in ('completed', 'error', 'cancelled'),
        }

    def generate():
        last_state = None
        retries = 0
        max_retries = 600  # 40 min máximo (4s × 600); análisis más largos usan notificación
        poll_interval = 4.0
        max_poll_interval = 8.0
        pubsub = None

        try:
            from infrastructure.services.job_queue import get_redis_connection

            redis_conn = get_redis_connection()
            pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(f"op_progress:{analysis_id}")

            latest_raw = redis_conn.get(f"op_progress_latest:{analysis_id}")
            if latest_raw:
                latest_text = latest_raw.decode('utf-8') if isinstance(latest_raw, bytes) else str(latest_raw)
                try:
                    latest_state = json.loads(latest_text)
                    state_key = (latest_state.get('status'), round(float(latest_state.get('progress', 0)), 1))
                    yield f"data: {json.dumps(latest_state, default=str)}\n\n"
                    last_state = state_key
                    if latest_state.get('final'):
                        return
                except Exception:
                    pass
        except Exception:
            pubsub = None

        while retries < max_retries:
            try:
                if pubsub is not None:
                    try:
                        msg = pubsub.get_message(timeout=poll_interval)
                    except Exception:
                        msg = None

                    if msg and msg.get('type') == 'message' and msg.get('data'):
                        raw = msg['data']
                        raw_text = raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)
                        try:
                            state = json.loads(raw_text)
                        except Exception:
                            state = None

                        if state:
                            state_key = (state.get('status'), round(float(state.get('progress', 0)), 1))
                            if state_key != last_state:
                                yield f"data: {json.dumps(state, default=str)}\n\n"
                                last_state = state_key
                                poll_interval = 4.0
                            else:
                                yield f": heartbeat\n\n"

                            if state.get('final'):
                                yield f"data: {json.dumps({**state, 'final': True}, default=str)}\n\n"
                                break

                            retries += 1
                            continue

                a = _get_operational_repo().obtener_analisis(analysis_id)
                if not a:
                    yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
                    break

                state = _build_state_from_analysis(a)
                state_key = (state.get('status'), round(float(state.get('progress', 0)), 1))

                if state_key != last_state:
                    yield f"data: {json.dumps(state, default=str)}\n\n"
                    last_state = state_key
                    poll_interval = 4.0
                else:
                    yield f": heartbeat\n\n"
                    poll_interval = min(max_poll_interval, poll_interval + 0.5)

                if state.get('final'):
                    yield f"data: {json.dumps({**state, 'final': True})}\n\n"
                    break

                time.sleep(poll_interval)
                retries += 1

            except GeneratorExit:
                break
            except Exception as e:
                logger.warning(f"[{vid}] SSE error: {e}")
                yield f"data: {json.dumps({'error': 'Error interno del servidor'})}\n\n"
                break

        if pubsub is not None:
            try:
                pubsub.unsubscribe(f"op_progress:{analysis_id}")
                pubsub.close()
            except Exception:
                pass

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: CANCELAR ANÁLISIS EN PROGRESO
# ═══════════════════════════════════════════════════════════════


@app_operational.route("/analyses/<analysis_id>/cancel", methods=["POST"])
@api_socio_requerido
def cancelar_analisis(analysis_id):
    """
    Cancela un análisis en progreso.
    Cambia estado a CANCELLED, el pipeline lo detecta y se detiene.
    """
    vid = analysis_id[:8]
    try:
        analysis = _get_operational_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        # Solo permitir cancelar si está en progreso
        cancellable_states = [
            EstadoOperationalAnalysis.PENDING,
            EstadoOperationalAnalysis.DOWNLOADING,
            EstadoOperationalAnalysis.SCANNING,
            EstadoOperationalAnalysis.ANALYZING,
            EstadoOperationalAnalysis.CROSS_ANALYZING,
            EstadoOperationalAnalysis.GENERATING_REPORT,
        ]
        if analysis.estado not in cancellable_states:
            return jsonify({
                "success": False,
                "error": f"No se puede cancelar un análisis en estado '{analysis.estado.value}'"
            }), 400

        logger.info(f"[{vid}] 🛑 Cancelando análisis operativo (usuario={current_user})")

        analysis.actualizar_estado(EstadoOperationalAnalysis.CANCELLED, 'Cancelado por el usuario')
        analysis.error_message = "Análisis cancelado por el usuario"
        _get_operational_repo().guardar_analisis(analysis)

        # Invalidar cache
        _invalidate_analysis_cache(analysis_id)

        return jsonify({
            "success": True,
            "message": "Análisis cancelado correctamente",
            "status": "cancelled"
        }), 200

    except Exception as e:
        logger.error(f"[{vid}] ❌ Error cancelando análisis: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: ESTIMACIÓN DE TIEMPO
# ═══════════════════════════════════════════════════════════════


@app_operational.route("/estimate-time", methods=["POST"])
def estimar_tiempo():
    """
    Estima el tiempo de procesamiento (endpoint público).
    
    Body: { "analysis_type": "ACCESS_CONTROL", "video_duration_seconds": 3600, "file_size_mb": 500 }
    """
    try:
        data = request.get_json() or {}
        analysis_type = data.get("analysis_type", "ACCESS_CONTROL")
        video_duration = data.get("video_duration_seconds", 0)
        file_size_mb = data.get("file_size_mb", 0)

        type_info = OPERATIONAL_ANALYSIS_TYPES.get(analysis_type, {})
        minutes_per_hour = type_info.get("estimated_minutes_per_hour", 8)

        # Calcular estimación
        video_hours = video_duration / 3600 if video_duration > 0 else file_size_mb / 500  # ~500MB/h
        estimated_minutes = max(5, video_hours * minutes_per_hour)

        # Sumar tiempo de descarga/upload
        upload_minutes = max(1, file_size_mb / 100)  # ~100MB/min
        total_minutes = estimated_minutes + upload_minutes

        return jsonify({
            "success": True,
            "estimated_minutes": round(total_minutes, 1),
            "estimated_range": {
                "min_minutes": round(total_minutes * 0.7, 1),
                "max_minutes": round(total_minutes * 1.5, 1),
            },
            "breakdown": {
                "upload_minutes": round(upload_minutes, 1),
                "analysis_minutes": round(estimated_minutes, 1),
            }
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: REPROCESAR ANÁLISIS FALLIDO
# ═══════════════════════════════════════════════════════════════


@app_operational.route("/analyses/<analysis_id>/reprocess", methods=["POST"])
@api_socio_requerido
def reprocesar_analisis(analysis_id):
    """
    Re-procesa un análisis que falló (estado 'error').
    Reutiliza el video ya subido al almacenamiento.
    """
    vid = analysis_id[:8]
    request_start = time.perf_counter()

    try:
        analysis = _get_operational_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "Análisis no encontrado"}), 404

        # Verificar ownership
        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso"}), 403

        # Solo permitir reprocesar si está en error
        if analysis.estado != EstadoOperationalAnalysis.ERROR:
            return jsonify({
                "success": False,
                "error": f"Solo se pueden reprocesar análisis en error. Estado actual: {analysis.estado.value}"
            }), 400

        # Verificar que el video sigue existiendo en el almacenamiento.
        if analysis.video_url:
            video_exists = _get_upload_service().verificar_upload_completo(analysis.video_url)
            if not video_exists:
                return jsonify({
                    "success": False,
                    "error": "El video ya no está disponible en el almacenamiento. Debes subir el video nuevamente."
                }), 400

        logger.info(f"[{vid}] 🔄 REPROCESANDO análisis operativo")

        # Resetear estado
        analysis.actualizar_estado(EstadoOperationalAnalysis.PENDING, 'Reprocesando...', 0)
        analysis.error_message = ""
        analysis.summary = {}
        analysis.eventos = []
        analysis.scan_stats = {}
        analysis.phase_timings = {}
        analysis.started_at = ""
        analysis.completed_at = ""
        analysis.tiempo_procesamiento_segundos = 0
        analysis.report_pdf_url = ""
        _get_operational_repo().guardar_analisis(analysis)

        # Eliminar eventos previos
        try:
            deleted = _get_operational_repo().eliminar_eventos_by_analysis_id(analysis_id)
            if deleted:
                logger.info(f"[{vid}]    🗑️ Eliminados {deleted} eventos previos")
        except Exception as e:
            logger.warning(f"[{vid}]    ⚠️ Error eliminando eventos previos: {e}")

        # Invalidar cache
        _invalidate_analysis_cache(analysis_id)

        # Encolar análisis
        job_id = None
        processing_started = False

        try:
            from infrastructure.services.job_queue import (
                enqueue_operational_analysis,
                is_redis_available,
                can_enqueue_operational_analysis,
            )

            if is_redis_available():
                can_enqueue, queue_state = can_enqueue_operational_analysis()
                if not can_enqueue:
                    return jsonify({
                        "success": False,
                        "error": "Sistema con alta carga. Intenta nuevamente en unos minutos.",
                        "queue": queue_state,
                    }), 503
                job_id = enqueue_operational_analysis(analysis_id)
                if job_id:
                    processing_started = True
                    logger.info(f"[{vid}] ✅ Re-encolado (Job ID: {job_id})")
            else:
                logger.error(f"[{vid}] ❌ Redis no disponible — rechazando re-encolado")
                return jsonify({
                    "success": False,
                    "error": "Sistema de cola no disponible. Reintenta en unos minutos.",
                }), 503

        except Exception as e:
            logger.error(f"[{vid}] ❌ Error re-encolando: {e}", exc_info=True)
            analysis.actualizar_estado(
                EstadoOperationalAnalysis.ERROR,
                'Error al reiniciar el análisis'
            )
            analysis.error_message = 'Error interno al reiniciar'
            _get_operational_repo().guardar_analisis(analysis)
            return jsonify({"success": False, "error": "Error interno del servidor"}), 500

        elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.info(f"[{vid}] ✅ Reprocesamiento iniciado [{elapsed_ms:.0f}ms]")

        return jsonify({
            "success": True,
            "analysis_id": analysis_id,
            "status": "processing" if processing_started else "pending",
            "job_id": job_id,
            "message": "Análisis re-iniciado correctamente",
        }), 200

    except Exception as e:
        logger.error(f"[{vid}] ❌ Error reprocesando: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: COMPARATIVA ENTRE ANÁLISIS
# ═══════════════════════════════════════════════════════════════


@app_operational.route("/analyses/compare", methods=["POST"])
@api_socio_requerido
def comparar_analisis():
    """
    Compara 2 análisis del mismo tipo.

    Body:
        {
            "analysis_id_a": "op_xxx",
            "analysis_id_b": "op_yyy"
        }

    Returns comparativa con deltas de métricas.
    """
    try:
        data = request.get_json() or {}
        id_a = data.get("analysis_id_a")
        id_b = data.get("analysis_id_b")

        if not id_a or not id_b:
            return jsonify({"success": False, "error": "Se requieren analysis_id_a y analysis_id_b"}), 400

        current_user = _get_current_username()

        analysis_a = _get_operational_repo().obtener_analisis(id_a)
        analysis_b = _get_operational_repo().obtener_analisis(id_b)

        if not analysis_a or not analysis_b:
            return jsonify({"success": False, "error": "Uno o ambos análisis no encontrados"}), 404

        # Verificar ownership
        if analysis_a.usuario != current_user or analysis_b.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso para uno o ambos análisis"}), 403

        # Verificar mismo tipo
        if analysis_a.analysis_type != analysis_b.analysis_type:
            return jsonify({
                "success": False,
                "error": f"Los análisis deben ser del mismo tipo. A={analysis_a.analysis_type}, B={analysis_b.analysis_type}"
            }), 400

        # Verificar ambos completados
        if (analysis_a.estado != EstadoOperationalAnalysis.COMPLETED or
                analysis_b.estado != EstadoOperationalAnalysis.COMPLETED):
            return jsonify({"success": False, "error": "Ambos análisis deben estar completados"}), 400

        # Construir comparativa
        summary_a = analysis_a.summary or {}
        summary_b = analysis_b.summary or {}

        # Extraer métricas numéricas comunes
        all_keys = set(list(summary_a.keys()) + list(summary_b.keys()))
        numeric_keys = [k for k in all_keys if isinstance(summary_a.get(k), (int, float)) or isinstance(summary_b.get(k), (int, float))]

        deltas = {}
        for key in numeric_keys:
            val_a = summary_a.get(key, 0)
            val_b = summary_b.get(key, 0)
            if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                delta = val_b - val_a
                pct = ((val_b - val_a) / val_a * 100) if val_a != 0 else 0
                deltas[key] = {
                    "analysis_a": val_a,
                    "analysis_b": val_b,
                    "delta": delta,
                    "delta_pct": round(pct, 1),
                }

        total_events_a = _get_operational_repo().contar_eventos(id_a)
        total_events_b = _get_operational_repo().contar_eventos(id_b)

        comparison = {
            "analysis_type": analysis_a.analysis_type,
            "analysis_a": {
                "id": id_a,
                "video_filename": analysis_a.video_filename,
                "video_duration": analysis_a.video_duration,
                "created_at": analysis_a.created_at,
                "total_events": total_events_a,
                "summary": summary_a,
            },
            "analysis_b": {
                "id": id_b,
                "video_filename": analysis_b.video_filename,
                "video_duration": analysis_b.video_duration,
                "created_at": analysis_b.created_at,
                "total_events": total_events_b,
                "summary": summary_b,
            },
            "deltas": deltas,
            "event_count_delta": total_events_b - total_events_a,
        }

        return jsonify({
            "success": True,
            "comparison": comparison
        }), 200

    except Exception as e:
        logger.error(f"❌ Error comparando análisis: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: ELIMINAR
# ═══════════════════════════════════════════════════════════════


@app_operational.route("/analyses/<analysis_id>", methods=["DELETE"])
@api_socio_requerido
def eliminar_analisis(analysis_id):
    """
    Elimina un análisis operativo y sus eventos.
    Requiere que el usuario sea dueño del análisis.
    """
    vid = analysis_id[:8]
    try:
        # Verificar ownership
        analysis = _get_operational_repo().obtener_analisis(analysis_id)
        if not analysis:
            return jsonify({"success": False, "error": "No encontrado"}), 404

        current_user = _get_current_username()
        if analysis.usuario != current_user:
            return jsonify({"success": False, "error": "No tienes permiso para eliminar este análisis"}), 403

        logger.info(f"[{vid}] 🗑️ Eliminando análisis operativo (usuario={current_user})")

        ok = _get_operational_repo().eliminar_analisis(analysis_id)
        if not ok:
            return jsonify({"success": False, "error": "Error eliminando"}), 500

        # Invalidar cache
        _invalidate_analysis_cache(analysis_id)

        logger.info(f"[{vid}] ✅ Análisis eliminado")
        return jsonify({"success": True, "message": "Análisis eliminado"}), 200

    except Exception as e:
        logger.error(f"[{vid}] ❌ Error eliminando análisis: {e}")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500
