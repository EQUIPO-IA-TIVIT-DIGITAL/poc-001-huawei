"""
Endpoints para upload de videos usando Signed URLs (Fase 1 - Escalado)
"""
from flask import Blueprint, jsonify, request, session
from datetime import datetime, timedelta
from functools import wraps
import logging
import uuid
import os
from werkzeug.utils import secure_filename

from infrastructure.dependencies import get_video_repository, get_user_repository, get_storage_adapter
from infrastructure.web.auth_decorators import socio_requerido
from domain.entities import Video
from infrastructure.rate_limiter import limiter, UPLOAD_LIMIT

logger = logging.getLogger(__name__)

# Crear Blueprint
upload_bp = Blueprint("upload", __name__, url_prefix="/api/v1/videos")

_ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
}

# Lazy init de almacenamiento local (evitar conexión al importar)
def _get_storage():
    return get_storage_adapter()


def _generate_upload_url(filename: str, user_id: str) -> dict:
    """Genera URL firmada PUT contra MinIO (o almacenamiento local)."""
    safe_name = secure_filename(filename)
    if not safe_name:
        raise ValueError("Nombre de archivo inválido")
    file_extension = os.path.splitext(safe_name)[1].lower()
    if file_extension not in _ALLOWED_VIDEO_EXTENSIONS:
        raise ValueError(
            f"Extensión no permitida: {file_extension!r}. "
            f"Permitidas: {', '.join(_ALLOWED_VIDEO_EXTENSIONS)}"
        )
    server_content_type = _ALLOWED_VIDEO_EXTENSIONS[file_extension]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    current_date = datetime.now()
    blob_name = f"videos/{user_id}/{current_date.strftime('%Y%m')}/{unique_filename}"

    storage = _get_storage()
    if not storage or not storage.is_available():
        raise RuntimeError("Almacenamiento no disponible")

    bucket_name = getattr(storage, "bucket", "cu002-videos")

    # MinIO / S3: presigned PUT
    if hasattr(storage, "_get_client"):
        c = storage._get_client()
        url = c.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": bucket_name, "Key": blob_name, "ContentType": server_content_type},
            ExpiresIn=3600,
        )
        return {
            "upload_url": url,
            "blob_name": blob_name,
            "bucket": bucket_name,
            "content_type": server_content_type,
        }

    # Filesystem: sin PUT firmado; el blob_name sirve de referencia local
    return {
        "upload_url": "",
        "blob_name": blob_name,
        "bucket": bucket_name,
        "content_type": server_content_type,
    }


def _check_blob_exists(blob_name: str) -> bool:
    storage = _get_storage()
    if not storage or not storage.is_available():
        return False
    if hasattr(storage, "_get_client"):
        try:
            storage._get_client().head_object(Bucket=storage.bucket, Key=blob_name)
            return True
        except Exception:
            return False
    if hasattr(storage, "base_dir"):
        from pathlib import Path
        return (Path(storage.base_dir) / blob_name).exists()
    return False


def _generate_download_url(blob_name: str) -> str:
    storage = _get_storage()
    if not storage or not storage.is_available():
        return ""
    if hasattr(storage, "generate_signed_url"):
        return storage.generate_signed_url(blob_name, 60) or ""
    return ""


# ========== ENDPOINTS ==========


@upload_bp.route('/upload-url', methods=['POST', 'OPTIONS'])
@limiter.limit(UPLOAD_LIMIT)
@socio_requerido
def get_upload_url():
    """
    Genera URL firmada para subida directa al almacenamiento.
    
    Body:
        {
            "filename": "video.mp4",
            "content_type": "video/mp4",
            "size": 104857600,
            "title": "Mi video",
            "description": "Descripción opcional"
        }
    
    Response 200:
        {
            "success": true,
            "data": {
                "video_id": 123,
            "upload_url": "https://storage.example/...",
                "expires_at": "2026-01-27T15:00:00Z",
                "storage_path": "s3://bucket/videos/123/202601/...",
                "storage_bucket": "bucket"
            }
        }
    
    Response 400:
        {
            "success": false,
            "error": "filename is required"
        }
    """
    try:
        data = request.json
        user_id = session.get('usuario_id')
        
        # Validaciones
        if not data.get('filename'):
            return jsonify({'success': False, 'error': 'filename is required'}), 400
        
        # Validar tamaño máximo (5GB)
        max_size = 5 * 1024 * 1024 * 1024
        if data.get('size', 0) > max_size:
            return jsonify({
                'success': False, 
                'error': f'File too large. Maximum size is 5GB'
            }), 400
        
        # Validar extensión
        allowed_extensions = ['.mp4', '.webm', '.mov', '.avi', '.mkv']
        filename = data['filename'].lower()
        if not any(filename.endswith(ext) for ext in allowed_extensions):
            return jsonify({
                'success': False,
                'error': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'
            }), 400
        
        # Generar URL firmada (content_type derivado de la extensión)
        result = _generate_upload_url(
            filename=data['filename'],
            user_id=user_id
        )
        
        # Crear registro en DB con status='pending'
        video_repo = get_video_repository()
        
        video = Video(
            user_id=user_id,
            title=data.get('title', data['filename']),
            descripcion=data.get('description', ''),
            nombre_archivo=data['filename'],
            ruta_video=result['blob_name'],
            estado='pending',
            tamano_bytes=data.get('size', 0),
            fecha_creacion=datetime.now()
        )
        
        video_repo.save(video)
        
        # Calcular tiempo de expiración
        expires_at = (datetime.now() + timedelta(hours=1)).isoformat() + 'Z'
        
        return jsonify({
            'success': True,
            'data': {
                'video_id': video.id,
                'upload_url': result['upload_url'],
                'storage_path': f"s3://{result['bucket']}/{result['blob_name']}",
                'storage_bucket': result['bucket'],
                'expires_at': expires_at
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error generating upload URL: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@upload_bp.route('/<int:video_id>/confirm', methods=['POST', 'OPTIONS'])
@limiter.limit(UPLOAD_LIMIT)
@socio_requerido
def confirm_upload(video_id):
    """
    Confirma que la subida al almacenamiento finalizó exitosamente.
    
    Body: {} (vacío, opcional metadata adicional)
    
    Response 200:
        {
            "success": true,
            "data": {
                "video_id": 123,
                "status": "uploaded",
                "message": "Upload confirmed"
            }
        }
    
    Response 404:
        {
            "success": false,
            "error": "Video not found"
        }
    """
    try:
        user_id = session.get('usuario_id')
        video_repo = get_video_repository()
        
        # Buscar video
        video = video_repo.get_by_id(video_id)
        
        if not video:
            return jsonify({
                'success': False,
                'error': 'Video not found'
            }), 404
        
        # Verificar propiedad
        if video.user_id != user_id:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403
        
        # Verificar estado
        if video.estado != 'pending':
            return jsonify({
                'success': False,
                'error': f'Video already in state: {video.estado}'
            }), 400
        
        # Verificar que el archivo existe en almacenamiento
        if not _check_blob_exists(video.ruta_video):
            return jsonify({
                'success': False,
                'error': 'File not found in storage'
            }), 400
        
        # Actualizar estado
        video.estado = 'uploaded'
        video.fecha_subida = datetime.now()
        video_repo.save(video)
        
        # Procesamiento asíncrono delegado al worker (RQ/Cloud Tasks)
        
        return jsonify({
            'success': True,
            'data': {
                'video_id': video.id,
                'status': video.estado,
                'message': 'Upload confirmed. Video is being processed.'
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error confirming upload: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@upload_bp.route('/<int:video_id>/url', methods=['GET'])
@socio_requerido
def get_video_url(video_id):
    """
    Obtiene URL firmada para ver/descargar un video
    
    Response 200:
        {
            "success": true,
            "data": {
                "video_id": 123,
                "url": "https://storage.example/...",
                "expires_in_minutes": 60
            }
        }
    """
    try:
        user_id = session.get('usuario_id')
        video_repo = get_video_repository()
        
        video = video_repo.get_by_id(video_id)
        
        if not video:
            return jsonify({
                'success': False,
                'error': 'Video not found'
            }), 404
        
        # Verificar acceso (propiedad o admin)
        if video.user_id != user_id:
            return jsonify({
                'success': False,
                'error': 'Unauthorized'
            }), 403
        
        # Generar URL firmada
        url = _generate_download_url(video.ruta_video)
        
        return jsonify({
            'success': True,
            'data': {
                'video_id': video.id,
                'url': url,
                'expires_in_minutes': 60
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting video URL: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


# ========== HELPER IMPORTS ==========
# timedelta moved to top-level import
