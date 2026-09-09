"""
Blueprint de Workspaces - CRUD de proyectos/carpetas para videos
"""

from flask import Blueprint, request, jsonify, session
from functools import wraps
import uuid
import re
from datetime import datetime

from infrastructure.repositories.workspace_repository import WorkspaceRepositoryFirestore
from infrastructure.repositories.video_repository import VideoRepositoryFirestore
from infrastructure.services.workspace_stats_service import recalculate_workspace_stats
from infrastructure.services.workspace_audit import WorkspaceAuditLogger
from infrastructure.services.workspace_transactions import (
    crear_workspace_atomico,
    actualizar_workspace_atomico,
    eliminar_workspace_con_batch,
    duplicar_workspace_atomico,
    soft_delete_workspace_atomico,
    restaurar_workspace_atomico
)
from infrastructure.validators import (
    sanitize_workspace_name,
    sanitize_workspace_description,
    sanitize_workspace_context,
    validate_hex_color,
    validate_categoria,
    validate_nivel_tolerancia,
    validate_workspace_name_length
)
from infrastructure.rate_limiter import limiter
from domain.entities import Workspace, EstadoVideo, ReglaNegocioException
import logging

logger = logging.getLogger(__name__)

# Inicializar cliente Firestore para transacciones (eliminado: stack 100% local)
_firestore_client = None

def _get_firestore_client():
    return None

# Constantes de validación
MAX_WORKSPACES_PER_USER = 20
MAX_VIDEOS_PER_WORKSPACE = 100
MIN_WORKSPACE_NAME_LENGTH = 3
MAX_WORKSPACE_NAME_LENGTH = 50
CARACTERES_PROHIBIDOS = ['/', '\\', '<', '>', ':', '"', '|', '?', '*', '\n', '\r', '\t']

workspace_bp = Blueprint('workspaces', __name__)

_workspace_repo = None
_video_repo = None

def _get_workspace_repo():
    global _workspace_repo
    if _workspace_repo is None:
        _workspace_repo = WorkspaceRepositoryFirestore()
    return _workspace_repo

def _get_video_repo():
    global _video_repo
    if _video_repo is None:
        _video_repo = VideoRepositoryFirestore()
    return _video_repo

# Handler global para OPTIONS en todos los endpoints de este blueprint
@workspace_bp.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.status_code = 200
        return response


def workspace_auth_required(f):
    """Decorator para required autenticación"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Permitir preflight checks de CORS sin autenticación
        if request.method == "OPTIONS":
            return "", 200
        
        if 'username' not in session:
            return jsonify({'success': False, 'error': 'No autenticado'}), 401
        return f(*args, **kwargs)
    return decorated_function


@workspace_bp.route('/workspaces', methods=['POST', 'OPTIONS'])
@limiter.limit("10 per minute")  # Rate limiting: máximo 10 creaciones por minuto
@workspace_auth_required
def create_workspace():
    """Crear nuevo workspace con transacción atómica y sanitización"""
    try:
        usuario = session['username']
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'Datos requeridos'}), 400
        
        # ===== SANITIZACIÓN Y VALIDACIÓN =====
        
        # 1. Sanitizar y validar nombre
        try:
            nombre = sanitize_workspace_name(data.get('nombre', '').strip())
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        
        if not validate_workspace_name_length(nombre, MIN_WORKSPACE_NAME_LENGTH, MAX_WORKSPACE_NAME_LENGTH):
            return jsonify({
                'success': False,
                'error': f'El nombre debe tener entre {MIN_WORKSPACE_NAME_LENGTH} y {MAX_WORKSPACE_NAME_LENGTH} caracteres'
            }), 400
        
        # 2. Sanitizar descripción
        descripcion = sanitize_workspace_description(data.get('descripcion', '').strip())
        
        # 3. Sanitizar contexto
        contexto = sanitize_workspace_context(data.get('contexto', '').strip())
        
        # 4. Validar categoría
        categoria = data.get('categoria', 'general')
        if not validate_categoria(categoria):
            return jsonify({
                'success': False,
                'error': 'Categoría inválida'
            }), 400
        
        # 5. Validar nivel de tolerancia
        nivel_tolerancia = data.get('nivel_tolerancia', 'medio')
        if not validate_nivel_tolerancia(nivel_tolerancia):
            return jsonify({
                'success': False,
                'error': 'Nivel de tolerancia inválido'
            }), 400
        
        # 6. Validar color
        color = data.get('color', '#3B82F6')
        if not validate_hex_color(color):
            return jsonify({
                'success': False,
                'error': 'Color inválido (debe ser formato #RRGGBB)'
            }), 400
        
        # 7. Sanitizar campos opcionales
        tipo_contenido = sanitize_workspace_context(data.get('tipo_contenido', '').strip())
        elementos_visuales = sanitize_workspace_context(data.get('elementos_visuales', '').strip())
        icono_url = data.get('icono_url', '').strip()[:500]  # Limitar URL
        
        # ===== CREAR WORKSPACE CON TRANSACCIÓN ATÓMICA =====
        
        workspace_data = {
            'id': str(uuid.uuid4()),
            'usuario': usuario,
            'nombre': nombre,
            'descripcion': descripcion,
            'contexto': contexto,
            'categoria': categoria,
            'tipo_contenido': tipo_contenido,
            'elementos_visuales': elementos_visuales,
            'nivel_tolerancia': nivel_tolerancia,
            'fecha_creacion': datetime.now().isoformat(),
            'fecha_modificacion': datetime.now().isoformat(),
            'color': color,
            'icono_url': icono_url,
            'es_exhaustivo': bool(data.get('es_exhaustivo', False)),
            'es_general': False,
            'orden': 0,
            'estadisticas': {
                'total_videos': 0,
                'aprobados': 0,
                'rechazados': 0,
                'en_revision': 0,
                'duracion_total_segundos': 0,
                'ultima_actividad': ''
            },
            'permisos': [],
            'visibilidad': 'privado',
            'metadatos': {}
        }
        
        # Ejecutar transacción atómica
        success, error_msg, workspace_id = crear_workspace_atomico(
            None, None, usuario, nombre, workspace_data
        )
        
        if not success:
            # Solo registrar auditoría de fallos técnicos, no validaciones de negocio
            if 'ya existe' not in error_msg.lower() and 'límite' not in error_msg.lower():
                WorkspaceAuditLogger.log_create(
                    usuario=usuario,
                    workspace_id='N/A',
                    workspace_nombre=nombre,
                    workspace_data=workspace_data,
                    success=False,
                    error_message=error_msg
                )
            return jsonify({'success': False, 'error': error_msg}), 400
        
        # Invalidar cache del repositorio
        _get_workspace_repo()._cache.pop(workspace_id, None)
        
        # Registrar auditoría de éxito
        WorkspaceAuditLogger.log_create(
            usuario=usuario,
            workspace_id=workspace_id,
            workspace_nombre=nombre,
            workspace_data=workspace_data,
            success=True
        )
        
        # Retornar workspace creado
        return jsonify({
            'success': True,
            'workspace': {
                'id': workspace_id,
                'nombre': nombre,
                'descripcion': descripcion,
                'contexto': contexto,
                'color': color,
                'icono_url': icono_url,
                'es_exhaustivo': workspace_data['es_exhaustivo'],
                'estadisticas': workspace_data['estadisticas']
            }
        }), 201
        
    except ReglaNegocioException as e:
        logger.warning(f"Regla de negocio violada en create_workspace: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400
    except ValueError as e:
        logger.warning(f"Valor inválido en create_workspace: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error inesperado en create_workspace: {e}", exc_info=True)
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500


@workspace_bp.route('/workspaces', methods=['GET', 'OPTIONS'])
@limiter.limit("30 per minute")  # Rate limiting: 30 consultas por minuto
@workspace_auth_required
def list_workspaces():
    """Listar workspaces del usuario con estadísticas mantenidas por evento."""
    try:
        usuario = session['username']
        ordenar_por = request.args.get('ordenar_por', 'fecha_creacion')
        
        workspaces = _get_workspace_repo().listar_por_usuario(usuario, ordenar_por)
        
        result = []
        for ws in workspaces:
            cached_stats = ws.estadisticas or {}
            stats = {
                "total_videos": cached_stats.get("total_videos", 0),
                "aprobados": cached_stats.get("aprobados", 0),
                "rechazados": cached_stats.get("rechazados", 0),
                "en_revision": cached_stats.get("en_revision", 0),
                "duracion_total_segundos": cached_stats.get("duracion_total_segundos", 0),
                "ultima_actividad": cached_stats.get("ultima_actividad", ws.fecha_modificacion or ""),
            }
            
            result.append({
                'id': ws.id,
                'nombre': ws.nombre,
                'descripcion': ws.descripcion,
                'contexto': ws.contexto,
                'color': ws.color,
                'icono_url': ws.icono_url if hasattr(ws, 'icono_url') else '',
                'es_general': ws.es_general,
                'es_exhaustivo': getattr(ws, 'es_exhaustivo', False),
                'estadisticas': stats,
                'fecha_creacion': ws.fecha_creacion
            })
        
        return jsonify({
            'success': True,
            'workspaces': result
        })
    except Exception as e:
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500


@workspace_bp.route('/workspaces/<workspace_id>', methods=['GET', 'OPTIONS'])
@workspace_auth_required
def get_workspace(workspace_id):
    """Obtener workspace por ID"""
    try:
        usuario = session['username']
        workspace = _get_workspace_repo().obtener_por_id(workspace_id)
        
        if not workspace:
            return jsonify({'success': False, 'error': 'Workspace no encontrado'}), 404
        
        if workspace.usuario != usuario:
            return jsonify({'success': False, 'error': 'No autorizado'}), 403
        
        return jsonify({
            'success': True,
            'workspace': {
                'id': workspace.id,
                'nombre': workspace.nombre,
                'descripcion': workspace.descripcion,
                'contexto': workspace.contexto,
                'color': workspace.color,
                'es_general': workspace.es_general,
                'es_exhaustivo': getattr(workspace, 'es_exhaustivo', False),
                'estadisticas': workspace.estadisticas,
                'fecha_creacion': workspace.fecha_creacion,
                'fecha_modificacion': workspace.fecha_modificacion
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500


@workspace_bp.route('/workspaces/<workspace_id>', methods=['PUT', 'OPTIONS'])
@limiter.limit("20 per minute")  # Rate limiting: 20 actualizaciones por minuto
@workspace_auth_required
def update_workspace(workspace_id):
    """Actualizar workspace con validación completa y transacción atómica"""
    try:
        usuario = session['username']
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'Datos requeridos'}), 400
        
        # Preparar diccionario de actualizaciones validadas
        updates = {}
        
        # ===== VALIDAR Y SANITIZAR CADA CAMPO =====
        
        # 1. Nombre
        if 'nombre' in data:
            try:
                nombre = sanitize_workspace_name(data['nombre'].strip())
            except ValueError as e:
                return jsonify({'success': False, 'error': str(e)}), 400
            
            if not validate_workspace_name_length(nombre, MIN_WORKSPACE_NAME_LENGTH, MAX_WORKSPACE_NAME_LENGTH):
                return jsonify({
                    'success': False,
                    'error': f'El nombre debe tener entre {MIN_WORKSPACE_NAME_LENGTH} y {MAX_WORKSPACE_NAME_LENGTH} caracteres'
                }), 400
            
            updates['nombre'] = nombre
        
        # 2. Descripción
        if 'descripcion' in data:
            descripcion = sanitize_workspace_description(data['descripcion'].strip())
            updates['descripcion'] = descripcion
        
        # 3. Contexto
        if 'contexto' in data:
            contexto = sanitize_workspace_context(data['contexto'].strip())
            updates['contexto'] = contexto
        
        # 4. Color
        if 'color' in data:
            color = data['color'].strip()
            if not validate_hex_color(color):
                return jsonify({
                    'success': False,
                    'error': 'Color inválido (debe ser formato #RRGGBB)'
                }), 400
            updates['color'] = color
        
        # 5. Categoría
        if 'categoria' in data:
            categoria = data['categoria']
            if not validate_categoria(categoria):
                return jsonify({'success': False, 'error': 'Categoría inválida'}), 400
            updates['categoria'] = categoria
        
        # 6. Nivel de tolerancia
        if 'nivel_tolerancia' in data:
            nivel = data['nivel_tolerancia']
            if not validate_nivel_tolerancia(nivel):
                return jsonify({'success': False, 'error': 'Nivel de tolerancia inválido'}), 400
            updates['nivel_tolerancia'] = nivel
        
        # 7. Campos opcionales
        if 'icono_url' in data:
            updates['icono_url'] = data['icono_url'].strip()[:500]
        
        if 'tipo_contenido' in data:
            updates['tipo_contenido'] = sanitize_workspace_context(data['tipo_contenido'].strip())
        
        if 'elementos_visuales' in data:
            updates['elementos_visuales'] = sanitize_workspace_context(data['elementos_visuales'].strip())
        
        if 'es_exhaustivo' in data:
            updates['es_exhaustivo'] = bool(data['es_exhaustivo'])
        
        # ===== ACTUALIZAR CON TRANSACCIÓN ATÓMICA =====
        
        if not updates:
            return jsonify({'success': False, 'error': 'No hay cambios para aplicar'}), 400
        
        # Obtener datos antiguos para auditoría
        old_ws = _get_workspace_repo().obtener_por_id(workspace_id)
        old_data = {
            'nombre': old_ws.nombre if old_ws else 'Desconocido',
            'descripcion': old_ws.descripcion if old_ws else '',
        }
        
        success, error_msg = actualizar_workspace_atomico(
            None, None, workspace_id, usuario, updates
        )
        
        if not success:
            # Registrar auditoría de fallo
            WorkspaceAuditLogger.log_update(
                usuario=usuario,
                workspace_id=workspace_id,
                workspace_nombre=old_data.get('nombre', 'Desconocido'),
                old_data=old_data,
                new_data=updates,
                success=False,
                error_message=error_msg
            )
            return jsonify({'success': False, 'error': error_msg}), 400 if error_msg != "No autorizado" else 403
        
        # Invalidar cache
        _get_workspace_repo()._cache.pop(workspace_id, None)
        
        # Registrar auditoría de éxito
        WorkspaceAuditLogger.log_update(
            usuario=usuario,
            workspace_id=workspace_id,
            workspace_nombre=old_data.get('nombre', 'Desconocido'),
            old_data=old_data,
            new_data=updates,
            success=True
        )
        
        return jsonify({'success': True, 'workspace': {'id': workspace_id}})
        
    except ValueError as e:
        logger.warning(f"Valor inválido en update_workspace: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error inesperado en update_workspace: {e}", exc_info=True)
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500


@workspace_bp.route('/workspaces/<workspace_id>', methods=['DELETE', 'OPTIONS'])
@limiter.limit("15 per minute")  # Rate limiting: 15 eliminaciones por minuto
@workspace_auth_required
def delete_workspace(workspace_id):
    """
    Eliminar workspace usando SOFT DELETE (papelera)
    
    El workspace se marca como eliminado pero no se borra físicamente.
    Los videos permanecen asociados al workspace eliminado.
    
    Query params:
        - hard_delete=true: Eliminar permanentemente (mover videos a General)
    """
    try:
        usuario = session['username']
        workspace = _get_workspace_repo().obtener_por_id(workspace_id)
        
        if not workspace or workspace.usuario != usuario:
            return jsonify({'success': False, 'error': 'No autorizado'}), 403
        
        if workspace.es_general:
            return jsonify({'success': False, 'error': 'No se puede eliminar el workspace General'}), 400
        
        # Verificar si es hard delete o soft delete
        hard_delete = request.args.get('hard_delete', 'false').lower() == 'true'
        
        if hard_delete:
            # HARD DELETE: Eliminar permanentemente moviendo videos
            workspace_general = _get_workspace_repo().obtener_workspace_general(usuario)
            videos = _get_video_repo().obtener_por_usuario(usuario)
            video_ids = [video.id for video in videos if getattr(video, 'workspace_id', None) == workspace_id]
            
            success, error_msg = eliminar_workspace_con_batch(
                None, workspace_id, usuario, workspace_general.id, video_ids
            )
            
            accion = 'hard_delete'
        else:
            # SOFT DELETE: Mover a papelera
            success, error_msg = soft_delete_workspace_atomico(
                None, workspace_id, usuario
            )
            
            accion = 'soft_delete'
            video_ids = []
        
        if not success:
            # Registrar auditoría de fallo
            WorkspaceAuditLogger.log_delete(
                usuario=usuario,
                workspace_id=workspace_id,
                workspace_nombre=workspace.nombre,
                videos_count=len(video_ids) if hard_delete else 0,
                accion_videos=accion,
                success=False,
                error_message=error_msg
            )
            return jsonify({'success': False, 'error': error_msg}), 500
        
        # Registrar auditoría de éxito
        WorkspaceAuditLogger.log_delete(
            usuario=usuario,
            workspace_id=workspace_id,
            workspace_nombre=workspace.nombre,
            videos_count=len(video_ids) if hard_delete else 0,
            accion_videos=accion,
            success=True
        )
        
        # Invalidar cache
        _get_workspace_repo()._cache.pop(workspace_id, None)
        
        # Si es hard delete, recalcular estadísticas
        # Invalidar cache
        _get_workspace_repo()._cache.pop(workspace_id, None)
        
        # Si es hard delete, recalcular estadísticas
        if hard_delete:
            workspace_general = _get_workspace_repo().obtener_workspace_general(usuario)
            recalculate_workspace_stats(workspace_general.id, touch_activity=True)
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error inesperado en delete_workspace: {e}", exc_info=True)
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500


@workspace_bp.route('/workspaces/<workspace_id>/restore', methods=['POST'])
@limiter.limit("15 per minute")  # Rate limiting: 15 restauraciones por minuto
@workspace_auth_required
def restore_workspace(workspace_id):
    """Restaurar workspace eliminado (revertir soft delete)"""
    try:
        usuario = session['username']
        
        # Restaurar con transacción atómica
        success, error_msg = restaurar_workspace_atomico(
            None, workspace_id, usuario
        )
        
        if not success:
            # Registrar auditoría de fallo
            WorkspaceAuditLogger.log_restore(
                usuario=usuario,
                workspace_id=workspace_id,
                workspace_nombre='Desconocido',
                success=False,
                error_message=error_msg
            )
            status_code = 403 if error_msg == "No autorizado" else 400
            return jsonify({'success': False, 'error': error_msg}), status_code
        
        # Obtener workspace restaurado
        workspace = _get_workspace_repo().obtener_por_id(workspace_id)
        
        # Registrar auditoría de éxito
        WorkspaceAuditLogger.log_restore(
            usuario=usuario,
            workspace_id=workspace_id,
            workspace_nombre=workspace.nombre if workspace else 'Desconocido',
            success=True
        )
        
        # Invalidar cache
        _get_workspace_repo()._cache.pop(workspace_id, None)
        
        return jsonify({
            'success': True,
            'workspace': {
                'id': workspace_id,
                'nombre': workspace.nombre if workspace else ''
            }
        })
        
    except Exception as e:
        logger.error(f"Error inesperado en restore_workspace: {e}", exc_info=True)
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500


@workspace_bp.route('/workspaces/trash', methods=['GET'])
@limiter.limit("30 per minute")  # Rate limiting: 30 consultas por minuto
@workspace_auth_required
def list_deleted_workspaces():
    """Listar workspaces eliminados (papelera)"""
    try:
        usuario = session['username']
        
        # Obtener workspaces eliminados desde SQLAlchemy
        from infrastructure.db.session import SessionLocal
        from infrastructure.db.models import WorkspaceModel

        s = SessionLocal()
        try:
            rows = (
                s.query(WorkspaceModel)
                .filter(WorkspaceModel.usuario == usuario, WorkspaceModel.eliminado == True)  # noqa: E712
                .all()
            )
        finally:
            s.close()

        # Convertir a formato JSON
        workspaces_json = []
        for m in rows:
            meta = m.metadatos or {}
            workspaces_json.append({
                'id': m.id,
                'nombre': m.nombre,
                'descripcion': m.descripcion or '',
                'color': meta.get('color', ''),
                'icono_url': meta.get('icono_url', ''),
                'categoria': m.categoria or 'general',
                'fecha_creacion': meta.get('fecha_creacion', ''),
                'fecha_eliminacion': meta.get('fecha_eliminacion', ''),
                'eliminado_por': meta.get('eliminado_por', ''),
                'estadisticas': meta.get('estadisticas', {})
            })
        
        return jsonify({
            'success': True,
            'workspaces': workspaces_json,
            'total': len(workspaces_json)
        })
        
    except Exception as e:
        logger.error(f"Error obteniendo workspaces eliminados: {e}", exc_info=True)
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500


@workspace_bp.route('/workspaces/<workspace_id>/duplicate', methods=['POST'])
@limiter.limit("5 per minute")  # Rate limiting: 5 duplicaciones por minuto
@workspace_auth_required
def duplicate_workspace(workspace_id):
    """Duplicar workspace con validación atómica de límites"""
    try:
        usuario = session['username']
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'Datos requeridos'}), 400
        
        nuevo_nombre_raw = data.get('nuevo_nombre', '').strip()
        
        if not nuevo_nombre_raw:
            return jsonify({'success': False, 'error': 'Nombre requerido'}), 400
        
        # Sanitizar y validar nuevo nombre
        try:
            nuevo_nombre = sanitize_workspace_name(nuevo_nombre_raw)
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        
        if not validate_workspace_name_length(nuevo_nombre, MIN_WORKSPACE_NAME_LENGTH, MAX_WORKSPACE_NAME_LENGTH):
            return jsonify({
                'success': False,
                'error': f'El nombre debe tener entre {MIN_WORKSPACE_NAME_LENGTH} y {MAX_WORKSPACE_NAME_LENGTH} caracteres'
            }), 400
        
        # Duplicar con transacción atómica
        
        # Obtener workspace original para auditoría
        workspace_original = _get_workspace_repo().obtener_por_id(workspace_id)
        if not workspace_original:
            return jsonify({'success': False, 'error': 'Workspace no encontrado'}), 404
        
        success, error_msg, nuevo_id = duplicar_workspace_atomico(
            None, usuario, workspace_id, nuevo_nombre
        )
        
        if not success:
            # Registrar auditoría de fallo
            WorkspaceAuditLogger.log_duplicate(
                usuario=usuario,
                workspace_original_id=workspace_id,
                workspace_original_nombre=workspace_original.nombre,
                workspace_nuevo_id='',
                workspace_nuevo_nombre=nuevo_nombre,
                success=False,
                error_message=error_msg
            )
            status_code = 403 if error_msg == "No autorizado" else 400
            return jsonify({'success': False, 'error': error_msg}), status_code
        
        # Obtener workspace duplicado para retornar
        workspace_duplicado = _get_workspace_repo().obtener_por_id(nuevo_id)
        
        # Registrar auditoría de éxito
        WorkspaceAuditLogger.log_duplicate(
            usuario=usuario,
            workspace_original_id=workspace_id,
            workspace_original_nombre=workspace_original.nombre,
            workspace_nuevo_id=nuevo_id,
            workspace_nuevo_nombre=nuevo_nombre,
            success=True
        )
        
        return jsonify({
            'success': True,
            'workspace': {
                'id': workspace_duplicado.id,
                'nombre': workspace_duplicado.nombre,
                'descripcion': workspace_duplicado.descripcion,
                'contexto': workspace_duplicado.contexto,
                'color': workspace_duplicado.color
            }
        }), 201
        
    except ValueError as e:
        logger.warning(f"Valor inválido en duplicate_workspace: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error inesperado en duplicate_workspace: {e}", exc_info=True)
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500


@workspace_bp.route('/workspaces/search', methods=['GET'])
@limiter.limit("30 per minute")  # Rate limiting: 30 búsquedas por minuto
@workspace_auth_required
def search_workspaces():
    """Buscar workspaces por nombre, descripción o contexto"""
    try:
        usuario = session['username']
        query = request.args.get('q', '').strip()
        
        if not query:
            return jsonify({'success': False, 'error': 'Query requerido'}), 400
        
        resultados = _get_workspace_repo().buscar(usuario, query)
        
        return jsonify({
            'success': True,
            'resultados': [{
                'id': ws.id,
                'nombre': ws.nombre,
                'descripcion': ws.descripcion,
                'contexto': ws.contexto,
                'color': ws.color,
                'es_exhaustivo': getattr(ws, 'es_exhaustivo', False),
                'estadisticas': ws.estadisticas
            } for ws in resultados],
            'total': len(resultados)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500


@workspace_bp.route('/workspaces/<workspace_id>/videos', methods=['GET', 'OPTIONS'])
@workspace_auth_required
def get_workspace_videos(workspace_id):
    """Obtener videos del workspace"""
    try:
        usuario = session['username']
        workspace = _get_workspace_repo().obtener_por_id(workspace_id)
        
        if not workspace or workspace.usuario != usuario:
            return jsonify({'success': False, 'error': 'No autorizado'}), 403
        
        videos = _get_video_repo().obtener_por_usuario_y_workspace(usuario, workspace_id)

        # Sincronizar estadísticas si el conteo difiere del valor guardado
        stored_total = (workspace.estadisticas or {}).get('total_videos', -1)
        if stored_total != len(videos):
            try:
                recalculate_workspace_stats(workspace_id, touch_activity=False)
            except Exception as stats_err:
                logger.warning(f"No se pudieron sincronizar estadísticas del workspace {workspace_id}: {stats_err}")

        return jsonify({
            'success': True,
            'videos': [{
                'id': v.id,
                'nombre_archivo': v.nombre_archivo,
                'descripcion': v.descripcion,
                'estado': v.estado.value if hasattr(v.estado, 'value') else str(v.estado),
                'thumbnail_url': f"/thumbnails/{v.id}_thumb.jpg",
                'video_url': f"/socio/media/{v.id}",
            } for v in videos]
        })
    except Exception as e:
        print(f"❌ Error en get_workspace_videos: {e}")
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500
