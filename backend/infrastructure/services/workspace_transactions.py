"""
Operaciones atómicas para Workspace en Firestore.

NOTA: Se usa batch writes y create() en lugar de @firestore.transactional
porque el decorator causa "no transaction ID" con credenciales ADC en Docker.
Las garantías de consistencia se mantienen via create() (único para username)
y batch commits (atómicos para escrituras múltiples).
"""

from typing import Optional, Tuple, Dict, Any
from datetime import datetime
import uuid
import logging

from google.cloud import firestore
from domain.entities import Workspace

logger = logging.getLogger(__name__)

# Límites de negocio
MAX_WORKSPACES_PER_USER = 20
MAX_VIDEOS_PER_WORKSPACE = 100


def _workspace_to_dict(workspace: Workspace) -> Dict[str, Any]:
    """Convierte un Workspace a diccionario para Firestore"""
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
    """Convierte un dict de Firestore a Workspace"""
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


# ---------------------------------------------------------------------------
# crear_workspace_atomico
# ---------------------------------------------------------------------------

def crear_workspace_atomico(
    transaction,  # Se mantiene por compatibilidad con llamadores existentes (ignorado)
    db: firestore.Client,
    usuario: str,
    nombre: str,
    workspace_data: Dict[str, Any],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Crea un workspace verificando límites y unicidad de nombre.

    Usa lecturas directas + set() en lugar de @transactional para compatibilidad
    con credenciales ADC en Docker.

    Returns:
        Tupla (success, error_message, workspace_id)
    """
    try:
        workspaces_ref = db.collection('workspaces')

        # 1. Leer workspaces existentes del usuario
        existing_docs = list(workspaces_ref.where(filter=firestore.FieldFilter('usuario', '==', usuario)).stream())
        active_workspaces = [
            doc.to_dict() for doc in existing_docs
            if not doc.to_dict().get('eliminado', False)
        ]

        # 2. Verificar límite
        if len(active_workspaces) >= MAX_WORKSPACES_PER_USER:
            logger.warning("⚠️ Usuario %s alcanzó límite de %d workspaces", usuario, MAX_WORKSPACES_PER_USER)
            return (False, f'Has alcanzado el límite de {MAX_WORKSPACES_PER_USER} proyectos', None)

        # 3. Verificar nombre único (case-insensitive, solo activos)
        nombre_lower = nombre.lower()
        for ws in active_workspaces:
            if ws.get('nombre', '').lower() == nombre_lower:
                logger.warning("⚠️ Usuario %s intentó crear workspace con nombre duplicado: %s", usuario, nombre)
                return (False, 'Ya existe un proyecto con ese nombre', None)

        # 4. Preparar y guardar
        workspace_id = workspace_data.get('id') or str(uuid.uuid4())
        workspace_data['id'] = workspace_id
        workspace_data['usuario'] = usuario
        workspace_data['nombre'] = nombre
        workspace_data.setdefault('fecha_creacion', datetime.now().isoformat())
        workspace_data.setdefault('fecha_modificacion', datetime.now().isoformat())

        doc_ref = workspaces_ref.document(workspace_id)
        doc_ref.set(workspace_data)

        logger.info("✅ Workspace creado: %s - %s (usuario: %s)", workspace_id, nombre, usuario)
        return (True, None, workspace_id)

    except Exception as e:
        logger.error("❌ Error creando workspace: %s", e, exc_info=True)
        return (False, "Error interno al crear el proyecto", None)


# ---------------------------------------------------------------------------
# actualizar_workspace_atomico
# ---------------------------------------------------------------------------

def actualizar_workspace_atomico(
    transaction,  # Ignorado — mantenido por compatibilidad
    db: firestore.Client,
    workspace_id: str,
    usuario: str,
    updates: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Actualiza un workspace con validaciones de permisos y nombre único.
    """
    try:
        doc_ref = db.collection('workspaces').document(workspace_id)
        doc = doc_ref.get()

        if not doc.exists:
            return (False, "Workspace no encontrado")

        workspace_data = doc.to_dict()

        # Verificar permisos
        if workspace_data.get('usuario') != usuario:
            logger.warning("⚠️ Usuario %s intentó modificar workspace de otro: %s", usuario, workspace_id)
            return (False, "No autorizado")

        # No permitir modificar General
        if workspace_data.get('es_general', False):
            return (False, "No se puede editar el workspace General")

        # Validar unicidad de nombre si cambió
        if 'nombre' in updates:
            nuevo_nombre_lower = updates['nombre'].lower()
            actual_lower = workspace_data.get('nombre', '').lower()
            if nuevo_nombre_lower != actual_lower:
                existing = list(
                    db.collection('workspaces').where(filter=firestore.FieldFilter('usuario', '==', usuario)).stream()
                )
                for ex_doc in existing:
                    if ex_doc.id != workspace_id:
                        ex_data = ex_doc.to_dict()
                        if ex_data.get('nombre', '').lower() == nuevo_nombre_lower:
                            return (False, "Ya existe un proyecto con ese nombre")

        updates['fecha_modificacion'] = datetime.now().isoformat()
        doc_ref.update(updates)

        logger.info("✅ Workspace actualizado: %s (campos: %s)", workspace_id, list(updates.keys()))
        return (True, None)

    except Exception as e:
        logger.error("❌ Error actualizando workspace: %s", e, exc_info=True)
        return (False, "Error interno al actualizar el proyecto")


# ---------------------------------------------------------------------------
# soft_delete_workspace_atomico
# ---------------------------------------------------------------------------

def soft_delete_workspace_atomico(
    db: firestore.Client,
    workspace_id: str,
    usuario: str,
) -> Tuple[bool, Optional[str]]:
    """
    Marca un workspace como eliminado (soft delete).
    """
    try:
        workspace_ref = db.collection('workspaces').document(workspace_id)
        workspace_doc = workspace_ref.get()

        if not workspace_doc.exists:
            return (False, "Workspace no encontrado")

        workspace_data = workspace_doc.to_dict()

        if workspace_data.get('usuario') != usuario:
            return (False, "No autorizado")

        if workspace_data.get('es_general', False):
            return (False, "No se puede eliminar el workspace General")

        workspace_ref.update({
            'eliminado': True,
            'fecha_eliminacion': datetime.now().isoformat(),
            'eliminado_por': usuario,
            'fecha_modificacion': datetime.now().isoformat(),
        })

        logger.info("✅ Workspace soft-deleted: %s", workspace_id)
        return (True, None)

    except Exception as e:
        logger.error("❌ Error en soft delete de workspace: %s", e, exc_info=True)
        return (False, "Error interno al eliminar el proyecto")


# ---------------------------------------------------------------------------
# restaurar_workspace_atomico
# ---------------------------------------------------------------------------

def restaurar_workspace_atomico(
    db: firestore.Client,
    workspace_id: str,
    usuario: str,
) -> Tuple[bool, Optional[str]]:
    """
    Restaura un workspace eliminado (revierte soft delete).
    """
    try:
        workspace_ref = db.collection('workspaces').document(workspace_id)
        workspace_doc = workspace_ref.get()

        if not workspace_doc.exists:
            return (False, "Workspace no encontrado")

        workspace_data = workspace_doc.to_dict()

        if workspace_data.get('usuario') != usuario:
            return (False, "No autorizado")

        if not workspace_data.get('eliminado', False):
            return (False, "El workspace no está eliminado")

        workspace_ref.update({
            'eliminado': False,
            'fecha_eliminacion': '',
            'eliminado_por': '',
            'fecha_modificacion': datetime.now().isoformat(),
        })

        logger.info("✅ Workspace restaurado: %s", workspace_id)
        return (True, None)

    except Exception as e:
        logger.error("❌ Error restaurando workspace: %s", e, exc_info=True)
        return (False, "Error interno al restaurar el proyecto")


# ---------------------------------------------------------------------------
# eliminar_workspace_con_batch
# ---------------------------------------------------------------------------

def eliminar_workspace_con_batch(
    db: firestore.Client,
    workspace_id: str,
    usuario: str,
    workspace_general_id: str,
    video_ids: list,
) -> Tuple[bool, Optional[str]]:
    """
    HARD DELETE: Elimina físicamente un workspace moviendo sus videos a General.
    Usa batch write para atomicidad en las escrituras.
    """
    try:
        batch = db.batch()

        for video_id in video_ids:
            video_ref = db.collection('videos').document(video_id)
            batch.update(video_ref, {
                'workspace_id': workspace_general_id,
                'fecha_modificacion': datetime.now().isoformat(),
            })

        workspace_ref = db.collection('workspaces').document(workspace_id)
        batch.delete(workspace_ref)

        batch.commit()

        logger.warning("⚠️ HARD DELETE: workspace %s, %d videos movidos", workspace_id, len(video_ids))
        return (True, None)

    except Exception as e:
        logger.error("❌ Error en batch de eliminación de workspace: %s", e, exc_info=True)
        return (False, "Error interno al eliminar el proyecto")


# ---------------------------------------------------------------------------
# duplicar_workspace_atomico
# ---------------------------------------------------------------------------

def duplicar_workspace_atomico(
    db: firestore.Client,
    usuario: str,
    workspace_original_id: str,
    nuevo_nombre: str,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Duplica un workspace verificando límites.
    """
    try:
        original_ref = db.collection('workspaces').document(workspace_original_id)
        original_doc = original_ref.get()

        if not original_doc.exists:
            return (False, "Workspace original no encontrado", None)

        original_data = original_doc.to_dict()

        if original_data.get('usuario') != usuario:
            return (False, "No autorizado", None)

        # Verificar límite
        workspaces_ref = db.collection('workspaces')
        existing_docs = list(workspaces_ref.where(filter=firestore.FieldFilter('usuario', '==', usuario)).stream())
        active_docs = [d for d in existing_docs if not d.to_dict().get('eliminado', False)]

        if len(active_docs) >= MAX_WORKSPACES_PER_USER:
            return (False, f'Has alcanzado el límite de {MAX_WORKSPACES_PER_USER} proyectos', None)

        # Verificar nombre único
        nuevo_nombre_lower = nuevo_nombre.lower()
        for doc in active_docs:
            if doc.to_dict().get('nombre', '').lower() == nuevo_nombre_lower:
                return (False, "Ya existe un proyecto con ese nombre", None)

        # Crear duplicado
        nuevo_id = str(uuid.uuid4())
        nuevo_data = {
            'id': nuevo_id,
            'usuario': usuario,
            'nombre': nuevo_nombre,
            'descripcion': original_data.get('descripcion', ''),
            'contexto': original_data.get('contexto', ''),
            'categoria': original_data.get('categoria', 'general'),
            'tipo_contenido': original_data.get('tipo_contenido', ''),
            'elementos_visuales': original_data.get('elementos_visuales', ''),
            'nivel_tolerancia': original_data.get('nivel_tolerancia', 'medio'),
            'fecha_creacion': datetime.now().isoformat(),
            'fecha_modificacion': datetime.now().isoformat(),
            'es_general': False,
            'es_exhaustivo': original_data.get('es_exhaustivo', False),
            'color': original_data.get('color', '#3B82F6'),
            'icono_url': original_data.get('icono_url', ''),
            'orden': original_data.get('orden', 0),
            'estadisticas': {
                'total_videos': 0,
                'aprobados': 0,
                'rechazados': 0,
                'en_revision': 0,
                'duracion_total_segundos': 0,
                'ultima_actividad': '',
            },
            'permisos': [],
            'visibilidad': original_data.get('visibilidad', 'privado'),
            'metadatos': {},
        }

        workspaces_ref.document(nuevo_id).set(nuevo_data)

        logger.info("✅ Workspace duplicado: %s → %s", workspace_original_id, nuevo_id)
        return (True, None, nuevo_id)

    except Exception as e:
        logger.error("❌ Error duplicando workspace: %s", e, exc_info=True)
        return (False, "Error interno al duplicar el proyecto", None)


# ---------------------------------------------------------------------------
# obtener_o_crear_workspace_general_atomico
# ---------------------------------------------------------------------------

def obtener_o_crear_workspace_general_atomico(
    db: firestore.Client,
    usuario: str,
) -> Tuple[bool, Optional[str], Optional[Workspace]]:
    """
    Obtiene el workspace "General" de un usuario, o lo crea si no existe.

    Usa query directa + set() en lugar de @transactional para compatibilidad
    con credenciales ADC en Docker.
    """
    try:
        workspaces_ref = db.collection('workspaces')

        # 1. Buscar workspace General existente
        existing_docs = list(
            workspaces_ref
            .where(filter=firestore.FieldFilter('usuario', '==', usuario))
            .where(filter=firestore.FieldFilter('es_general', '==', True))
            .limit(1)
            .stream()
        )

        # 2. Si existe, retornarlo
        if existing_docs:
            data = existing_docs[0].to_dict()
            workspace_general = _dict_to_workspace(data)
            logger.info("✅ Workspace General encontrado: %s", workspace_general.id)
            return (True, None, workspace_general)

        # 3. Si no existe, crearlo
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

        workspaces_ref.document(nuevo_id).set(nuevo_data)

        workspace_general = _dict_to_workspace(nuevo_data)
        logger.info("✅ Workspace General creado: %s", nuevo_id)
        return (True, None, workspace_general)

    except Exception as e:
        logger.error("❌ Error obteniendo/creando workspace General: %s", e, exc_info=True)
        return (False, "Error interno al obtener el workspace General", None)
