"""
Sistema de Auditoría para Workspaces
Registra todas las operaciones CRUD con contexto completo
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from flask import request

from infrastructure.db.session import SessionLocal
from infrastructure.db.models import WorkspaceAuditModel

logger = logging.getLogger(__name__)


class WorkspaceAuditAction:
    """Acciones auditables en workspaces"""
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    DELETED = "DELETED"
    DUPLICATED = "DUPLICATED"
    RESTORED = "RESTORED"  # Para soft delete
    MOVED_VIDEOS = "MOVED_VIDEOS"


class WorkspaceAuditLogger:
    """
    Logger de auditoría para operaciones de workspaces

    Registra en la tabla 'workspace_audit_logs' (PostgreSQL/SQLAlchemy) con estructura:
    {
        'id': str,
        'timestamp': str (ISO 8601),
        'usuario': str,
        'accion': str (CREATED|UPDATED|DELETED|DUPLICATED|RESTORED|MOVED_VIDEOS),
        'workspace_id': str,
        'workspace_nombre': str,
        'cambios': dict,  # Detalles específicos de la operación
        'ip_address': str (opcional),
        'user_agent': str (opcional),
        'success': bool,
        'error_message': str (opcional)
    }
    """

    COLLECTION_NAME = 'workspace_audit_logs'

    @staticmethod
    def _get_request_context() -> Dict[str, Any]:
        """Obtiene contexto de la petición HTTP"""
        context = {}
        try:
            if request:
                forwarded_for = request.headers.get('X-Forwarded-For')
                context['ip_address'] = forwarded_for.split(',')[0].strip() if forwarded_for else request.remote_addr
                context['user_agent'] = request.headers.get('User-Agent', 'Unknown')
                context['endpoint'] = request.endpoint
                context['method'] = request.method
        except RuntimeError:
            pass
        return context

    @staticmethod
    def log_create(
        usuario: str,
        workspace_id: str,
        workspace_nombre: str,
        workspace_data: Dict[str, Any],
        success: bool = True,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Registra creación de workspace

        Args:
            usuario: Username del creador
            workspace_id: ID del workspace creado
            workspace_nombre: Nombre del workspace
            workspace_data: Datos completos del workspace
            success: Si la operación fue exitosa
            error_message: Mensaje de error si falló

        Returns:
            True si se registró correctamente
        """
        return WorkspaceAuditLogger._log_event(
            accion=WorkspaceAuditAction.CREATED,
            usuario=usuario,
            workspace_id=workspace_id,
            workspace_nombre=workspace_nombre,
            cambios={
                'categoria': workspace_data.get('categoria'),
                'nivel_tolerancia': workspace_data.get('nivel_tolerancia'),
                'color': workspace_data.get('color'),
                'descripcion_length': len(workspace_data.get('descripcion', '')),
                'contexto_length': len(workspace_data.get('contexto', ''))
            },
            success=success,
            error_message=error_message
        )

    @staticmethod
    def log_update(
        usuario: str,
        workspace_id: str,
        workspace_nombre: str,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any],
        success: bool = True,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Registra actualización de workspace

        Args:
            usuario: Username del usuario
            workspace_id: ID del workspace
            workspace_nombre: Nombre del workspace
            old_data: Datos anteriores
            new_data: Datos nuevos
            success: Si la operación fue exitosa
            error_message: Mensaje de error si falló

        Returns:
            True si se registró correctamente
        """
        cambios = {}
        for key in new_data:
            if key in old_data and old_data[key] != new_data[key]:
                cambios[key] = {
                    'old': old_data[key],
                    'new': new_data[key]
                }

        return WorkspaceAuditLogger._log_event(
            accion=WorkspaceAuditAction.UPDATED,
            usuario=usuario,
            workspace_id=workspace_id,
            workspace_nombre=workspace_nombre,
            cambios=cambios,
            success=success,
            error_message=error_message
        )

    @staticmethod
    def log_delete(
        usuario: str,
        workspace_id: str,
        workspace_nombre: str,
        videos_count: int,
        accion_videos: str,  # 'mover_general' | 'eliminar'
        success: bool = True,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Registra eliminación de workspace

        Args:
            usuario: Username del usuario
            workspace_id: ID del workspace eliminado
            workspace_nombre: Nombre del workspace
            videos_count: Cantidad de videos afectados
            accion_videos: Qué se hizo con los videos
            success: Si la operación fue exitosa
            error_message: Mensaje de error si falló

        Returns:
            True si se registró correctamente
        """
        return WorkspaceAuditLogger._log_event(
            accion=WorkspaceAuditAction.DELETED,
            usuario=usuario,
            workspace_id=workspace_id,
            workspace_nombre=workspace_nombre,
            cambios={
                'videos_count': videos_count,
                'accion_videos': accion_videos
            },
            success=success,
            error_message=error_message
        )

    @staticmethod
    def log_duplicate(
        usuario: str,
        workspace_original_id: str,
        workspace_original_nombre: str,
        workspace_nuevo_id: str,
        workspace_nuevo_nombre: str,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Registra duplicación de workspace

        Args:
            usuario: Username del usuario
            workspace_original_id: ID del workspace original
            workspace_original_nombre: Nombre del workspace original
            workspace_nuevo_id: ID del workspace duplicado
            workspace_nuevo_nombre: Nombre del workspace duplicado
            success: Si la operación fue exitosa
            error_message: Mensaje de error si falló

        Returns:
            True si se registró correctamente
        """
        return WorkspaceAuditLogger._log_event(
            accion=WorkspaceAuditAction.DUPLICATED,
            usuario=usuario,
            workspace_id=workspace_original_id,
            workspace_nombre=workspace_original_nombre,
            cambios={
                'nuevo_workspace_id': workspace_nuevo_id,
                'nuevo_workspace_nombre': workspace_nuevo_nombre
            },
            success=success,
            error_message=error_message
        )

    @staticmethod
    def log_restore(
        usuario: str,
        workspace_id: str,
        workspace_nombre: str,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Registra restauración de workspace (soft delete)

        Args:
            usuario: Username del usuario
            workspace_id: ID del workspace restaurado
            workspace_nombre: Nombre del workspace
            success: Si la operación fue exitosa
            error_message: Mensaje de error si falló

        Returns:
            True si se registró correctamente
        """
        return WorkspaceAuditLogger._log_event(
            accion=WorkspaceAuditAction.RESTORED,
            usuario=usuario,
            workspace_id=workspace_id,
            workspace_nombre=workspace_nombre,
            cambios={},
            success=success,
            error_message=error_message
        )

    @staticmethod
    def _log_event(
        accion: str,
        usuario: str,
        workspace_id: str,
        workspace_nombre: str,
        cambios: Dict[str, Any],
        success: bool,
        error_message: Optional[str]
    ) -> bool:
        """
        Registra un evento de auditoría en la tabla workspace_audit_logs

        Args:
            accion: Tipo de acción
            usuario: Username del usuario
            workspace_id: ID del workspace
            workspace_nombre: Nombre del workspace
            cambios: Diccionario con detalles del cambio
            success: Si la operación fue exitosa
            error_message: Mensaje de error si falló

        Returns:
            True si se registró correctamente
        """
        try:
            request_context = WorkspaceAuditLogger._get_request_context()

            audit_log = {
                'timestamp': datetime.now().isoformat(),
                'usuario': usuario,
                'accion': accion,
                'workspace_id': workspace_id,
                'workspace_nombre': workspace_nombre,
                'cambios': cambios,
                'success': success,
                **request_context
            }

            if error_message:
                audit_log['error_message'] = error_message

            db = SessionLocal()
            try:
                db.add(WorkspaceAuditModel(
                    id=str(uuid.uuid4()),
                    usuario=usuario,
                    workspace_id=workspace_id,
                    accion=accion,
                    data=audit_log,
                ))
                db.commit()
            finally:
                db.close()

            logger.info(f"📝 Auditoría registrada: {accion} - {workspace_nombre} por {usuario}")
            return True

        except Exception as e:
            logger.error(f"❌ Error registrando auditoría: {e}", exc_info=True)
            return False

    @staticmethod
    def get_workspace_history(
        workspace_id: str,
        limit: int = 50
    ) -> list:
        """
        Obtiene historial de auditoría de un workspace

        Args:
            workspace_id: ID del workspace
            limit: Cantidad máxima de registros

        Returns:
            Lista de eventos de auditoría ordenados por timestamp descendente
        """
        try:
            db = SessionLocal()
            try:
                rows = (
                    db.query(WorkspaceAuditModel)
                    .filter(WorkspaceAuditModel.workspace_id == workspace_id)
                    .order_by(WorkspaceAuditModel.created_at.desc())
                    .limit(limit)
                    .all()
                )
                return [r.data for r in rows]
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error obteniendo historial de auditoría: {e}")
            return []

    @staticmethod
    def get_user_history(
        usuario: str,
        limit: int = 100
    ) -> list:
        """
        Obtiene historial de auditoría de un usuario

        Args:
            usuario: Username del usuario
            limit: Cantidad máxima de registros

        Returns:
            Lista de eventos de auditoría ordenados por timestamp descendente
        """
        try:
            db = SessionLocal()
            try:
                rows = (
                    db.query(WorkspaceAuditModel)
                    .filter(WorkspaceAuditModel.usuario == usuario)
                    .order_by(WorkspaceAuditModel.created_at.desc())
                    .limit(limit)
                    .all()
                )
                return [r.data for r in rows]
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error obteniendo historial de usuario: {e}")
            return []
