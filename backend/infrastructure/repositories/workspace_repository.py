"""
Repositorio de Workspaces con SQLAlchemy
Persistencia permanente en PostgreSQL local
"""

from typing import List, Optional, Dict, Any
from threading import Lock
import logging
import json
import os
from datetime import datetime

from domain.entities import Workspace
from infrastructure.db.session import SessionLocal
from infrastructure.db.models import WorkspaceModel

logger = logging.getLogger(__name__)

_WORKSPACE_USER_CACHE_TTL = 15  # seconds


def _get_redis():
    """Obtiene la conexión Redis compartida. Retorna None si no disponible."""
    try:
        from infrastructure.services.job_queue import get_redis_connection
        conn = get_redis_connection()
        conn.ping()
        return conn
    except Exception:
        return None


def _redis_user_cache_key(usuario: str) -> str:
    return f"ws_user_list:{usuario}"


def _workspace_to_dict(ws: "Workspace") -> dict:
    """Serializa un Workspace a dict para almacenamiento en Redis."""
    return {
        'id': ws.id,
        'usuario': ws.usuario,
        'nombre': ws.nombre,
        'descripcion': ws.descripcion,
        'contexto': ws.contexto,
        'categoria': getattr(ws, 'categoria', 'general'),
        'tipo_contenido': getattr(ws, 'tipo_contenido', ''),
        'elementos_visuales': getattr(ws, 'elementos_visuales', ''),
        'nivel_tolerancia': getattr(ws, 'nivel_tolerancia', 'medio'),
        'fecha_creacion': ws.fecha_creacion,
        'fecha_modificacion': ws.fecha_modificacion,
        'es_general': ws.es_general,
        'es_exhaustivo': getattr(ws, 'es_exhaustivo', False),
        'color': ws.color,
        'icono_url': getattr(ws, 'icono_url', ''),
        'orden': ws.orden,
        'eliminado': getattr(ws, 'eliminado', False),
        'fecha_eliminacion': getattr(ws, 'fecha_eliminacion', ''),
        'eliminado_por': getattr(ws, 'eliminado_por', ''),
        'estadisticas': ws.estadisticas,
        'permisos': ws.permisos,
        'visibilidad': ws.visibilidad,
        'metadatos': ws.metadatos,
    }


def _workspace_from_dict(data: dict) -> "Workspace":
    """Deserializa un Workspace desde un dict (Redis)."""
    from domain.entities import Workspace
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


def _model_to_workspace(m: WorkspaceModel) -> Workspace:
    """Convierte un WorkspaceModel a entidad Workspace usando el JSON metadatos."""
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
        fecha_creacion=meta.get('fecha_creacion', m.created_at.isoformat() if m.created_at else ''),
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


def _workspace_to_model(ws: Workspace) -> dict:
    """Convierte un Workspace a atributos de WorkspaceModel (para upsert)."""
    elim = getattr(ws, 'eliminado', False)
    return {
        'id': ws.id,
        'usuario': ws.usuario,
        'nombre': ws.nombre,
        'descripcion': ws.descripcion,
        'categoria': getattr(ws, 'categoria', 'general'),
        'nivel_tolerancia': getattr(ws, 'nivel_tolerancia', 'medio'),
        'es_general': getattr(ws, 'es_general', False),
        'eliminado': elim,
        'metadatos': {
            'contexto': getattr(ws, 'contexto', ''),
            'tipo_contenido': getattr(ws, 'tipo_contenido', ''),
            'elementos_visuales': getattr(ws, 'elementos_visuales', ''),
            'fecha_creacion': getattr(ws, 'fecha_creacion', ''),
            'fecha_modificacion': getattr(ws, 'fecha_modificacion', ''),
            'es_exhaustivo': getattr(ws, 'es_exhaustivo', False),
            'color': getattr(ws, 'color', '#3B82F6'),
            'icono_url': getattr(ws, 'icono_url', ''),
            'orden': getattr(ws, 'orden', 0),
            'fecha_eliminacion': getattr(ws, 'fecha_eliminacion', ''),
            'eliminado_por': getattr(ws, 'eliminado_por', ''),
            'estadisticas': getattr(ws, 'estadisticas', {}),
            'permisos': getattr(ws, 'permisos', []),
            'visibilidad': getattr(ws, 'visibilidad', 'privado'),
            'metadatos': getattr(ws, 'metadatos', {}),
        },
    }


def _upsert_workspace(workspace: Workspace) -> Workspace:
    """Persiste un Workspace en la tabla workspaces (upsert por id)."""
    db = SessionLocal()
    try:
        m = db.get(WorkspaceModel, workspace.id)
        if m is None:
            m = WorkspaceModel()
            db.add(m)
        attrs = _workspace_to_model(workspace)
        m.id = attrs['id']
        m.usuario = attrs['usuario']
        m.nombre = attrs['nombre']
        m.descripcion = attrs['descripcion']
        m.categoria = attrs['categoria']
        m.nivel_tolerancia = attrs['nivel_tolerancia']
        m.es_general = attrs['es_general']
        m.eliminado = attrs['eliminado']
        m.metadatos = attrs['metadatos']
        db.commit()
        db.refresh(m)
        return _model_to_workspace(m)
    except Exception as e:
        db.rollback()
        logger.error(f"Error persistiendo workspace {workspace.id}: {e}")
        raise
    finally:
        db.close()


class WorkspaceRepositoryFirestore:
    """
    Repositorio de workspaces con persistencia en PostgreSQL (SQLAlchemy).

    Implementa el patrón Singleton con cache en memoria para rendimiento.
    Todos los cambios se persisten en la tabla workspaces automáticamente.

    Estructura en PostgreSQL:
    - workspaces -> registro por workspace (columnas + JSON metadatos)
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        """Implementación del patrón Singleton"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Inicializa el repositorio con conexión a PostgreSQL"""
        if self._initialized:
            return

        self._cache: Dict[str, Workspace] = {}
        self._lock_repo = Lock()
        self._initialized = True

        logger.info("Repositorio de workspaces conectado a PostgreSQL (SQLAlchemy)")

    def guardar(self, workspace: Workspace) -> Workspace:
        """
        Guarda un workspace en PostgreSQL y cache.

        Args:
            workspace: Workspace a guardar

        Returns:
            Workspace guardado
        """
        with self._lock_repo:
            workspace.fecha_modificacion = datetime.now().isoformat()
            self._cache[workspace.id] = workspace

            if hasattr(workspace, 'usuario') and workspace.usuario:
                try:
                    r = _get_redis()
                    if r:
                        r.delete(_redis_user_cache_key(workspace.usuario))
                except Exception:
                    pass

            try:
                _upsert_workspace(workspace)
                logger.debug(f"✅ Workspace guardado en PostgreSQL: {workspace.id}")
            except Exception as e:
                logger.error(f"❌ Error guardando workspace en PostgreSQL: {e}")

            return workspace

    def obtener_por_id(self, workspace_id: str) -> Optional[Workspace]:
        """Obtiene un workspace por ID"""
        with self._lock_repo:
            if workspace_id in self._cache:
                return self._cache[workspace_id]

            db = SessionLocal()
            try:
                m = db.get(WorkspaceModel, workspace_id)
                if m:
                    workspace = _model_to_workspace(m)
                    self._cache[workspace_id] = workspace
                    return workspace
            except Exception as e:
                logger.error(f"Error buscando workspace: {e}")
            finally:
                db.close()

            return None

    def listar_por_usuario(
        self,
        usuario: str,
        ordenar_por: str = "fecha_creacion"
    ) -> List[Workspace]:
        """
        Obtiene todos los workspaces de un usuario.
        Usa cache Redis (TTL 15s) compartido entre instancias para evitar roundtrips
        a PostgreSQL en la misma ventana de tiempo.

        Args:
            usuario: Username del propietario
            ordenar_por: Criterio de ordenamiento (fecha_creacion|alfabetico|actividad|num_videos)
        """
        redis_key = _redis_user_cache_key(usuario)
        try:
            r = _get_redis()
            if r:
                raw = r.get(redis_key)
                if raw:
                    try:
                        workspaces_data = json.loads(raw)
                        if not isinstance(workspaces_data, list):
                            logger.warning(f"⚠️ Cache Redis corrupto para {usuario}: no es una lista")
                            r.delete(redis_key)
                            raise ValueError("Cache corrupto: no es lista")

                        workspaces = []
                        for idx, data in enumerate(workspaces_data):
                            try:
                                if not isinstance(data, dict):
                                    logger.warning(f"⚠️ Item {idx} en cache no es dict")
                                    continue
                                ws = _workspace_from_dict(data)
                                workspaces.append(ws)
                            except Exception as item_err:
                                logger.warning(f"⚠️ Error deserializando workspace {idx}: {item_err}")
                                continue

                        if workspaces:
                            logger.debug(f"✅ Cache Redis hit para {usuario}: {len(workspaces)} workspaces")
                            return self._ordenar_workspaces(workspaces, ordenar_por)
                        else:
                            logger.warning(f"⚠️ Cache sin workspaces válidos para {usuario}, buscando en PostgreSQL...")
                            r.delete(redis_key)

                    except json.JSONDecodeError as json_err:
                        logger.error(f"❌ JSON corrupto en cache de {usuario}: {json_err}")
                        try:
                            r.delete(redis_key)
                            logger.info(f"🧹 Cache corrupto eliminado para {usuario}")
                        except Exception:
                            pass
        except Exception as e:
            logger.debug(f"Redis cache miss para workspaces de {usuario}: {e}")

        db = SessionLocal()
        try:
            rows = db.query(WorkspaceModel).filter(
                WorkspaceModel.usuario == usuario,
                WorkspaceModel.eliminado == False  # noqa: E712
            ).all()
            workspaces = [_model_to_workspace(r) for r in rows]
            for ws in workspaces:
                self._cache[ws.id] = ws
            try:
                r = _get_redis()
                if r:
                    try:
                        workspace_dicts = [_workspace_to_dict(ws) for ws in workspaces]
                        cache_data = json.dumps(workspace_dicts)
                        if len(cache_data) > 1_000_000:
                            logger.warning(f"⚠️ Cache demasiado grande para {usuario}: {len(cache_data)} bytes")
                        else:
                            r.setex(redis_key, _WORKSPACE_USER_CACHE_TTL, cache_data)
                            logger.debug(f"✅ Cache guardado para {usuario}: {len(workspaces)} workspaces")
                    except (TypeError, ValueError) as ser_err:
                        logger.error(f"❌ Error serializando workspaces para cache: {ser_err}")
            except Exception as cache_err:
                logger.debug(f"No se pudo guardar cache Redis: {cache_err}")
            return self._ordenar_workspaces(workspaces, ordenar_por)
        except Exception as e:
            logger.error(f"Error obteniendo workspaces del usuario: {e}")
        finally:
            db.close()

        with self._lock_repo:
            workspaces = [ws for ws in self._cache.values() if ws.usuario == usuario and not ws.eliminado]
            return self._ordenar_workspaces(workspaces, ordenar_por)

    def _ordenar_workspaces(
        self,
        workspaces: List[Workspace],
        ordenar_por: str
    ) -> List[Workspace]:
        """Ordena workspaces según criterio"""
        if ordenar_por == "alfabetico":
            return sorted(workspaces, key=lambda w: w.nombre.lower())
        elif ordenar_por == "actividad":
            return sorted(
                workspaces,
                key=lambda w: w.estadisticas.get("ultima_actividad", ""),
                reverse=True
            )
        elif ordenar_por == "num_videos":
            return sorted(
                workspaces,
                key=lambda w: w.estadisticas.get("total_videos", 0),
                reverse=True
            )
        elif ordenar_por == "orden":
            return sorted(workspaces, key=lambda w: w.orden)
        else:  # fecha_creacion (default)
            return sorted(workspaces, key=lambda w: w.fecha_creacion, reverse=True)

    def obtener_workspace_general(self, usuario: str) -> Workspace:
        """
        Obtiene o crea el workspace "General" para un usuario.

        Usa lógica atómica (query + create) para prevenir creación de
        duplicados en caso de requests simultáneos.
        """
        from infrastructure.services.workspace_transactions import (
            obtener_o_crear_workspace_general_atomico
        )

        success, error_msg, workspace_general = obtener_o_crear_workspace_general_atomico(None, usuario)

        if not success:
            logger.error(f"Error obteniendo workspace General: {error_msg}")
            workspace_general = Workspace(
                id=f"general_{usuario}_{int(datetime.now().timestamp())}",
                usuario=usuario,
                nombre="General",
                descripcion="Videos sin proyecto específico",
                contexto="",
                fecha_creacion=datetime.now().isoformat(),
                es_general=True,
                color="#6B7280"
            )
            return self.guardar(workspace_general)

        with self._lock_repo:
            self._cache[workspace_general.id] = workspace_general

        return workspace_general

    def eliminar(self, workspace_id: str) -> bool:
        """Elimina un workspace"""
        workspace = self.obtener_por_id(workspace_id)
        if not workspace:
            return False

        if workspace.es_general:
            logger.warning("No se puede eliminar el workspace General")
            return False

        with self._lock_repo:
            if workspace_id in self._cache:
                del self._cache[workspace_id]

            if hasattr(workspace, 'usuario') and workspace.usuario:
                try:
                    r = _get_redis()
                    if r:
                        r.delete(_redis_user_cache_key(workspace.usuario))
                except Exception:
                    pass

            db = SessionLocal()
            try:
                m = db.get(WorkspaceModel, workspace_id)
                if m:
                    db.delete(m)
                    db.commit()
                    return True
            except Exception as e:
                db.rollback()
                logger.error(f"Error eliminando workspace: {e}")
                return False
            finally:
                db.close()

            return True

    def contar_workspaces(self, usuario: str) -> int:
        """Cuenta el total de workspaces de un usuario"""
        workspaces = self.listar_por_usuario(usuario)
        return len(workspaces)

    def buscar(self, usuario: str, query: str) -> List[Workspace]:
        """
        Busca workspaces por nombre, descripción o contexto

        Args:
            usuario: Usuario propietario
            query: Texto a buscar
        """
        workspaces = self.listar_por_usuario(usuario)
        query_lower = query.lower()

        resultados = []
        for ws in workspaces:
            if (query_lower in ws.nombre.lower() or
                    query_lower in ws.descripcion.lower() or
                    query_lower in ws.contexto.lower()):
                resultados.append(ws)

        return resultados

    def duplicar(self, workspace_id: str, nuevo_nombre: str) -> Optional[Workspace]:
        """
        Duplica un workspace (sin sus videos)

        Args:
            workspace_id: ID del workspace a duplicar
            nuevo_nombre: Nombre para el nuevo workspace
        """
        original = self.obtener_por_id(workspace_id)
        if not original:
            return None

        import uuid
        nuevo_workspace = Workspace(
            id=str(uuid.uuid4()),
            usuario=original.usuario,
            nombre=nuevo_nombre,
            descripcion=original.descripcion,
            contexto=original.contexto,
            fecha_creacion=datetime.now().isoformat(),
            es_general=False,
            color=original.color,
            orden=original.orden,
            visibilidad=original.visibilidad
        )

        return self.guardar(nuevo_workspace)


# Alias para compatibilidad
WorkspaceRepositoryMemory = WorkspaceRepositoryFirestore
