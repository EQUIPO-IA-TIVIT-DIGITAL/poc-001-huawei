"""
Operaciones atómicas para Workspace en PostgreSQL.

NOTA: Se usan sesiones SQLAlchemy (SessionLocal) e inserciones únicas por id
con verificación previa de límites/unicidad en lugar de transacciones de la base de datos.
Las garantías de consistencia se mantienen vía query + create con validación
de límites y nombre único por usuario.
"""

from typing import Optional, Tuple, Dict, Any
from datetime import datetime
import uuid
import logging

from domain.entities import Workspace
from infrastructure.db.session import SessionLocal
from infrastructure.db.models import WorkspaceModel

logger = logging.getLogger(__name__)

# Límites de negocio
MAX_WORKSPACES_PER_USER = 20
MAX_VIDEOS_PER_WORKSPACE = 100


def _workspace_to_dict(workspace: Workspace) -> Dict[str, Any]:
    """Convierte un Workspace a diccionario para persistencia"""
    return {
        'id': workspace.id,
        'usuario': workspace.usuario,
        'nombre': workspace.nombre,
        'descripcion': workspace.descripcion,
        'contexto': workspace.contexto,
        'categoria': getattr(workspace, 'categoria', 'general'),
        'tipo_contenido': getattr(workspace, 'tipo_contenido', ''),
        'elementos_visuales': getattr(workspace, 'elementos_visuales', ''),
        'nivel_tolerancia': getattr(workspace, 'nivel_tolerancia', 'medio'),
        'fecha_creacion': workspace.fecha_creacion,
        'fecha_modificacion': workspace.fecha_modificacion,
        'es_general': workspace.es_general,
        'es_exhaustivo': getattr(workspace, 'es_exhaustivo', False),
        'color': workspace.color,
        'icono_url': getattr(workspace, 'icono_url', ''),
        'orden': workspace.orden,
        'estadisticas': workspace.estadisticas,
        'permisos': workspace.permisos,
        'visibilidad': workspace.visibilidad,
        'metadatos': workspace.metadatos,
    }


def _dict_to_workspace(data: Dict[str, Any]) -> Workspace:
    """Convierte un dict a Workspace"""
    return Workspace(
        id=data['id'],
        usuario=data['usuario'],
        nombre=data['nombre'],
        descripcion=data.get('descripcion', ''),
        contexto=data.get('contexto', ''),
        categoria=data.get('categoria', 'general'),
        tipo_contenido=data.get('tipo_contenido', ''),
        elementos_visuales=data.get('elementos_visuales', ''),
        nivel_tolerancia=data.get('nivel_tolerancia', 'medio'),
        fecha_creacion=data.get('fecha_creacion', ''),
        fecha_modificacion=data.get('fecha_modificacion', ''),
        es_general=data.get('es_general', False),
        es_exhaustivo=data.get('es_exhaustivo', False),
        color=data.get('color', '#3B82F6'),
        icono_url=data.get('icono_url', ''),
        orden=data.get('orden', 0),
        eliminado=data.get('eliminado', False),
        fecha_eliminacion=data.get('fecha_eliminacion', ''),
        eliminado_por=data.get('eliminado_por', ''),
        estadisticas=data.get('estadisticas', {}),
        permisos=data.get('permisos', []),
        visibilidad=data.get('visibilidad', 'privado'),
        metadatos=data.get('metadatos', {}),
    )


def _insert_workspace_row(data: Dict[str, Any]) -> None:
    """Inserta (o actualiza) un registro en la tabla workspaces a partir de un dict."""
    meta = dict(data)
    db = SessionLocal()
    try:
        m = db.get(WorkspaceModel, data.get('id'))
        if m is None:
            m = WorkspaceModel()
            db.add(m)
        m.id = meta.get('id', str(uuid.uuid4()))
        m.usuario = meta.get('usuario')
        m.nombre = meta.get('nombre')
        m.descripcion = meta.get('descripcion', '')
        m.categoria = meta.get('categoria', 'general')
        m.nivel_tolerancia = meta.get('nivel_tolerancia', 'medio')
        m.es_general = meta.get('es_general', False)
        m.eliminado = meta.get('eliminado', False)
        m.metadatos = {
            'contexto': meta.get('contexto', ''),
            'tipo_contenido': meta.get('tipo_contenido', ''),
            'elementos_visuales': meta.get('elementos_visuales', ''),
            'fecha_creacion': meta.get('fecha_creacion', ''),
            'fecha_modificacion': meta.get('fecha_modificacion', ''),
            'es_exhaustivo': meta.get('es_exhaustivo', False),
            'color': meta.get('color', '#3B82F6'),
            'icono_url': meta.get('icono_url', ''),
            'orden': meta.get('orden', 0),
            'fecha_eliminacion': meta.get('fecha_eliminacion', ''),
            'eliminado_por': meta.get('eliminado_por', ''),
            'estadisticas': meta.get('estadisticas', {}),
            'permisos': meta.get('permisos', []),
            'visibilidad': meta.get('visibilidad', 'privado'),
            'metadatos': meta.get('metadatos', {}),
        }
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Error insertando workspace: %s", e, exc_info=True)
        raise
    finally:
        db.close()


def _row_to_workspace(m: WorkspaceModel) -> Workspace:
    """Convierte un WorkspaceModel a Workspace"""
    meta = m.metadatos or {}
    return Workspace(
        id=m.id,
        usuario=m.usuario,
        nombre=m.nombre,
        descripcion=m.descripcion or '',
        contexto=meta.get('contexto', ''),
        categoria=m.categoria or 'general',
        tipo_contenido=meta.get('tipo_contenido', ''),
        elementos_visuales=meta.get('elementos_visuales', ''),
        nivel_tolerancia=m.nivel_tolerancia or 'medio',
        fecha_creacion=meta.get('fecha_creacion', ''),
        fecha_modificacion=meta.get('fecha_modificacion', ''),
        es_general=m.es_general if m.es_general is not None else False,
        es_exhaustivo=meta.get('es_exhaustivo', False),
        color=meta.get('color', '#3B82F6'),
        icono_url=meta.get('icono_url', ''),
        orden=meta.get('orden', 0),
        eliminado=m.eliminado if m.eliminado is not None else False,
        fecha_eliminacion=meta.get('fecha_eliminacion', ''),
        eliminado_por=meta.get('eliminado_por', ''),
        estadisticas=meta.get('estadisticas', {}),
        permisos=meta.get('permisos', []),
        visibilidad=meta.get('visibilidad', 'privado'),
        metadatos=meta.get('metadatos', {}),
    )


def _active_workspaces_by_user(db, usuario: str):
    """Retorna lista de filas activas (no eliminadas) de un usuario."""
    return (
        db.query(WorkspaceModel)
        .filter(WorkspaceModel.usuario == usuario, WorkspaceModel.eliminado == False)  # noqa: E712
        .all()
    )


# ---------------------------------------------------------------------------
# crear_workspace_atomico
# ---------------------------------------------------------------------------

def crear_workspace_atomico(
    transaction,  # Se mantiene por compatibilidad con llamadores existentes (ignorado)
    db,  # Se mantiene por compatibilidad con llamadores existentes (ignorado)
    usuario: str,
    nombre: str,
    workspace_data: Dict[str, Any],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Crea un workspace verificando límites y unicidad de nombre.

    Returns:
        Tupla (success, error_message, workspace_id)
    """
    session = SessionLocal()
    try:
        active_workspaces = _active_workspaces_by_user(session, usuario)

        if len(active_workspaces) >= MAX_WORKSPACES_PER_USER:
            logger.warning("⚠️ Usuario %s alcanzó límite de %d workspaces", usuario, MAX_WORKSPACES_PER_USER)
            return (False, f'Has alcanzado el límite de {MAX_WORKSPACES_PER_USER} proyectos', None)

        nombre_lower = nombre.lower()
        for ws in active_workspaces:
            if ws.nombre.lower() == nombre_lower:
                logger.warning("⚠️ Usuario %s intentó crear workspace con nombre duplicado: %s", usuario, nombre)
                return (False, 'Ya existe un proyecto con ese nombre', None)

        workspace_id = workspace_data.get('id') or str(uuid.uuid4())
        workspace_data['id'] = workspace_id
        workspace_data['usuario'] = usuario
        workspace_data['nombre'] = nombre
        workspace_data.setdefault('fecha_creacion', datetime.now().isoformat())
        workspace_data.setdefault('fecha_modificacion', datetime.now().isoformat())

        _insert_workspace_row(workspace_data)

        logger.info("✅ Workspace creado: %s - %s (usuario: %s)", workspace_id, nombre, usuario)
        return (True, None, workspace_id)

    except Exception as e:
        logger.error("❌ Error creando workspace: %s", e, exc_info=True)
        return (False, "Error interno al crear el proyecto", None)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# actualizar_workspace_atomico
# ---------------------------------------------------------------------------

def actualizar_workspace_atomico(
    transaction,  # Ignorado — mantenido por compatibilidad
    db,  # Ignorado — mantenido por compatibilidad
    workspace_id: str,
    usuario: str,
    updates: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Actualiza un workspace con validaciones de permisos y nombre único.
    """
    session = SessionLocal()
    try:
        m = session.get(WorkspaceModel, workspace_id)

        if not m:
            return (False, "Workspace no encontrado")

        if m.usuario != usuario:
            logger.warning("⚠️ Usuario %s intentó modificar workspace de otro: %s", usuario, workspace_id)
            return (False, "No autorizado")

        if m.es_general:
            return (False, "No se puede editar el workspace General")

        meta = dict(m.metadatos or {})

        if 'nombre' in updates:
            nuevo_nombre_lower = updates['nombre'].lower()
            actual_lower = (m.nombre or '').lower()
            if nuevo_nombre_lower != actual_lower:
                existing = _active_workspaces_by_user(session, usuario)
                for ex in existing:
                    if ex.id != workspace_id and ex.nombre.lower() == nuevo_nombre_lower:
                        return (False, "Ya existe un proyecto con ese nombre")

        for key, value in updates.items():
            if key in ('id', 'usuario'):
                continue
            if key == 'nombre':
                m.nombre = value
            elif key == 'descripcion':
                m.descripcion = value
            elif key == 'categoria':
                m.categoria = value
            elif key == 'nivel_tolerancia':
                m.nivel_tolerancia = value
            elif key == 'eliminado':
                m.eliminado = bool(value)
            elif key == 'es_general':
                m.es_general = bool(value)
            else:
                meta[key] = value

        if 'fecha_modificacion' not in updates:
            updates['fecha_modificacion'] = datetime.now().isoformat()
        meta['fecha_modificacion'] = updates.get('fecha_modificacion')

        m.metadatos = meta
        session.commit()

        logger.info("✅ Workspace actualizado: %s (campos: %s)", workspace_id, list(updates.keys()))
        return (True, None)

    except Exception as e:
        session.rollback()
        logger.error("❌ Error actualizando workspace: %s", e, exc_info=True)
        return (False, "Error interno al actualizar el proyecto")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# soft_delete_workspace_atomico
# ---------------------------------------------------------------------------

def soft_delete_workspace_atomico(
    db,  # Ignorado — mantenido por compatibilidad
    workspace_id: str,
    usuario: str,
) -> Tuple[bool, Optional[str]]:
    """
    Marca un workspace como eliminado (soft delete).
    """
    session = SessionLocal()
    try:
        m = session.get(WorkspaceModel, workspace_id)

        if not m:
            return (False, "Workspace no encontrado")

        if m.usuario != usuario:
            return (False, "No autorizado")

        if m.es_general:
            return (False, "No se puede eliminar el workspace General")

        meta = dict(m.metadatos or {})
        m.eliminado = True
        meta['fecha_eliminacion'] = datetime.now().isoformat()
        meta['eliminado_por'] = usuario
        meta['fecha_modificacion'] = datetime.now().isoformat()
        m.metadatos = meta
        session.commit()

        logger.info("✅ Workspace soft-deleted: %s", workspace_id)
        return (True, None)

    except Exception as e:
        session.rollback()
        logger.error("❌ Error en soft delete de workspace: %s", e, exc_info=True)
        return (False, "Error interno al eliminar el proyecto")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# restaurar_workspace_atomico
# ---------------------------------------------------------------------------

def restaurar_workspace_atomico(
    db,  # Ignorado — mantenido por compatibilidad
    workspace_id: str,
    usuario: str,
) -> Tuple[bool, Optional[str]]:
    """
    Restaura un workspace eliminado (revierte soft delete).
    """
    session = SessionLocal()
    try:
        m = session.get(WorkspaceModel, workspace_id)

        if not m:
            return (False, "Workspace no encontrado")

        if m.usuario != usuario:
            return (False, "No autorizado")

        if not m.eliminado:
            return (False, "El workspace no está eliminado")

        meta = dict(m.metadatos or {})
        m.eliminado = False
        meta['fecha_eliminacion'] = ''
        meta['eliminado_por'] = ''
        meta['fecha_modificacion'] = datetime.now().isoformat()
        m.metadatos = meta
        session.commit()

        logger.info("✅ Workspace restaurado: %s", workspace_id)
        return (True, None)

    except Exception as e:
        session.rollback()
        logger.error("❌ Error restaurando workspace: %s", e, exc_info=True)
        return (False, "Error interno al restaurar el proyecto")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# eliminar_workspace_con_batch
# ---------------------------------------------------------------------------

def eliminar_workspace_con_batch(
    db,  # Ignorado — mantenido por compatibilidad
    workspace_id: str,
    usuario: str,
    workspace_general_id: str,
    video_ids: list,
) -> Tuple[bool, Optional[str]]:
    """
    HARD DELETE: Elimina físicamente un workspace moviendo sus videos a General.
    Usa una única transacción SQLAlchemy para atomicidad en las escrituras.
    """
    session = SessionLocal()
    try:
        from infrastructure.db.models import VideoModel

        for video_id in video_ids:
            video = session.get(VideoModel, video_id)
            if video:
                video.workspace_id = workspace_general_id
                video.updated_at = datetime.now()

        ws = session.get(WorkspaceModel, workspace_id)
        if ws:
            session.delete(ws)

        session.commit()

        logger.warning("⚠️ HARD DELETE: workspace %s, %d videos movidos", workspace_id, len(video_ids))
        return (True, None)

    except Exception as e:
        session.rollback()
        logger.error("❌ Error en batch de eliminación de workspace: %s", e, exc_info=True)
        return (False, "Error interno al eliminar el proyecto")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# duplicar_workspace_atomico
# ---------------------------------------------------------------------------

def duplicar_workspace_atomico(
    db,  # Ignorado — mantenido por compatibilidad
    usuario: str,
    workspace_original_id: str,
    nuevo_nombre: str,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Duplica un workspace verificando límites.
    """
    session = SessionLocal()
    try:
        original = session.get(WorkspaceModel, workspace_original_id)

        if not original:
            return (False, "Workspace original no encontrado", None)

        if original.usuario != usuario:
            return (False, "No autorizado", None)

        active_docs = _active_workspaces_by_user(session, usuario)

        if len(active_docs) >= MAX_WORKSPACES_PER_USER:
            return (False, f'Has alcanzado el límite de {MAX_WORKSPACES_PER_USER} proyectos', None)

        nuevo_nombre_lower = nuevo_nombre.lower()
        for doc in active_docs:
            if doc.nombre.lower() == nuevo_nombre_lower:
                return (False, "Ya existe un proyecto con ese nombre", None)

        nuevo_id = str(uuid.uuid4())
        meta = dict(original.metadatos or {})
        nuevo_data = {
            'id': nuevo_id,
            'usuario': usuario,
            'nombre': nuevo_nombre,
            'descripcion': original.descripcion or '',
            'contexto': meta.get('contexto', ''),
            'categoria': original.categoria or 'general',
            'tipo_contenido': meta.get('tipo_contenido', ''),
            'elementos_visuales': meta.get('elementos_visuales', ''),
            'nivel_tolerancia': original.nivel_tolerancia or 'medio',
            'fecha_creacion': datetime.now().isoformat(),
            'fecha_modificacion': datetime.now().isoformat(),
            'es_general': False,
            'es_exhaustivo': meta.get('es_exhaustivo', False),
            'color': meta.get('color', '#3B82F6'),
            'icono_url': meta.get('icono_url', ''),
            'orden': meta.get('orden', 0),
            'estadisticas': {
                'total_videos': 0,
                'aprobados': 0,
                'rechazados': 0,
                'en_revision': 0,
                'duracion_total_segundos': 0,
                'ultima_actividad': '',
            },
            'permisos': [],
            'visibilidad': meta.get('visibilidad', 'privado'),
            'metadatos': {},
        }

        _insert_workspace_row(nuevo_data)

        logger.info("✅ Workspace duplicado: %s → %s", workspace_original_id, nuevo_id)
        return (True, None, nuevo_id)

    except Exception as e:
        logger.error("❌ Error duplicando workspace: %s", e, exc_info=True)
        return (False, "Error interno al duplicar el proyecto", None)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# obtener_o_crear_workspace_general_atomico
# ---------------------------------------------------------------------------

def obtener_o_crear_workspace_general_atomico(
    db,  # Ignorado — mantenido por compatibilidad
    usuario: str,
) -> Tuple[bool, Optional[str], Optional[Workspace]]:
    """
    Obtiene el workspace "General" de un usuario, o lo crea si no existe.

    Usa query directa + insert con verificación previa en lugar de
    @transactional para compatibilidad y simplicidad local.
    """
    session = SessionLocal()
    try:
        existing = (
            session.query(WorkspaceModel)
            .filter(WorkspaceModel.usuario == usuario, WorkspaceModel.es_general == True)  # noqa: E712
            .first()
        )

        if existing:
            workspace_general = _row_to_workspace(existing)
            logger.info("✅ Workspace General encontrado: %s", workspace_general.id)
            return (True, None, workspace_general)

        nuevo_id = f"general_{usuario}_{int(datetime.now().timestamp())}"
        nuevo_data = {
            'id': nuevo_id,
            'usuario': usuario,
            'nombre': 'General',
            'descripcion': 'Videos sin proyecto específico',
            'contexto': '',
            'categoria': 'general',
            'tipo_contenido': '',
            'elementos_visuales': '',
            'nivel_tolerancia': 'medio',
            'fecha_creacion': datetime.now().isoformat(),
            'fecha_modificacion': datetime.now().isoformat(),
            'es_general': True,
            'es_exhaustivo': False,
            'color': '#6B7280',
            'icono_url': '',
            'orden': 0,
            'eliminado': False,
            'fecha_eliminacion': '',
            'eliminado_por': '',
            'estadisticas': {
                'total_videos': 0,
                'aprobados': 0,
                'rechazados': 0,
                'en_revision': 0,
                'duracion_total_segundos': 0,
                'ultima_actividad': '',
            },
            'permisos': [],
            'visibilidad': 'privado',
            'metadatos': {},
        }

        _insert_workspace_row(nuevo_data)

        workspace_general = _dict_to_workspace(nuevo_data)
        logger.info("✅ Workspace General creado: %s", nuevo_id)
        return (True, None, workspace_general)

    except Exception as e:
        logger.error("❌ Error obteniendo/creando workspace General: %s", e, exc_info=True)
        return (False, "Error interno al obtener el workspace General", None)
    finally:
        session.close()
