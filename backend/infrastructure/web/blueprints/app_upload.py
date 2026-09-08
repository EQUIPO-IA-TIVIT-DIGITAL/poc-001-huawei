"""
Endpoints para upload de videos usando Signed URLs (Fase 1 - Escalado)
"""
from flask import Blueprint, jsonify, request, session
from datetime import datetime, timedelta
from functools import wraps
import logging

from infrastructure.services.gcs_service import GCSService
from infrastructure.dependencies import get_video_repository, get_user_repository
from infrastructure.web.auth_decorators import socio_requerido
from domain.entities import Video
from infrastructure.rate_limiter import limiter, UPLOAD_LIMIT

logger = logging.getLogger(__name__)

# Crear Blueprint
upload_bp = Blueprint("upload", __name__, url_prefix="/api/v1/videos")

# Lazy init de servicio GCS (evitar conexión al importar)
_gcs_service = None

def _get_gcs_service():
    global _gcs_service
    if _gcs_service is None:
        _gcs_service = GCSService()
    return _gcs_service


# ========== ENDPOINTS ==========


@upload_bp.route('/upload-url', methods=['POST', 'OPTIONS'])
@limiter.limit(UPLOAD_LIMIT)
@socio_requerido
def get_upload_url():
    """
    Genera URL firmada para subida directa a GCS
    
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
                "upload_url": "https://storage.googleapis.com/...",
                "expires_at": "2026-01-27T15:00:00Z",
                "blob_name": "videos/123/202601/..."
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
        
        # Generar URL firmada (content_type derivado de la extensión en GCSService)
        result = _get_gcs_service().generate_upload_url(
            filename=data['filename'],
            content_type=None,  # ignorado: GCSService lo deriva de la extensión
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
                'blob_name': result['blob_name'],
                'bucket': result['bucket'],
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
    Confirma que la subida a GCS finalizó exitosamente
    
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
        
        # Verificar que el archivo existe en GCS
        if not _get_gcs_service().check_blob_exists(video.ruta_video):
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
                "url": "https://storage.googleapis.com/...",
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
        url = _get_gcs_service().generate_download_url(video.ruta_video)
        
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
