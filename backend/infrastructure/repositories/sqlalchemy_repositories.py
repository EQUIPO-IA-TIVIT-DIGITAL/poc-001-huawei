"""
SQLAlchemy repos — local offline (Postgres/SQLite + pgvector)
Implementan VideoRepositoryProtocol / UserRepositoryProtocol sobre SessionLocal.
Mapean domain/entities.py <-> infrastructure/db/models.py
"""
import hashlib
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import tuple_
from domain.entities import Video, EstadoVideo, Usuario, RolUsuario
from infrastructure.db.session import SessionLocal, engine
from infrastructure.db.models import VideoModel, UserModel, WorkspaceModel

logger = logging.getLogger(__name__)


def _video_to_entity(m: VideoModel) -> Video:
    estado = EstadoVideo(m.estado) if m.estado in [e.value for e in EstadoVideo] else EstadoVideo.PENDIENTE
    v = Video(
        id=m.id,
        usuario=m.usuario,
        ruta_archivo=m.s3_uri or m.storage_uri or "",
        descripcion=m.descripcion or m.titulo or "",
        metadatos_ia=m.metadatos or {},
        estado=estado,
        nombre_archivo=m.titulo or "",
        workspace_id=m.workspace_id or "general",
        fecha_creacion=m.created_at.isoformat() if m.created_at else None,
    )
    # campos extra no en dataclass -> metadatos
    if m.s3_uri:
        v.metadatos_ia["s3_uri"] = m.s3_uri
    if m.storage_uri:
        v.metadatos_ia["storage_uri"] = m.storage_uri
    return v


def _usuario_to_entity(m: UserModel) -> Usuario:
    # Usuario dataclass en entities.py usa username, email, password_hash, etc.
    # Construcción tolerante: entidades validan via __post_init__
    try:
        return Usuario(
            id=m.id,
            username=m.username,
            email=m.email,
            nombre_completo=m.nombre_completo or m.username,
            rol=RolUsuario(m.rol) if m.rol in [r.value for r in RolUsuario] else RolUsuario.SOCIO,
            activo=m.activo,
            password_hash=m.password_hash,
        )
    except Exception:
        # fallback mínimo
        u = Usuario.__new__(Usuario)  # type: ignore
        u.id = m.id; u.username = m.username; u.email = m.email
        u.nombre_completo = m.nombre_completo; u.rol = RolUsuario.SOCIO; u.activo = m.activo
        u.password_hash = m.password_hash
        return u


class SQLAlchemyVideoRepository:
    """Video repo local — cubre VideoRepositoryProtocol + métodos legacy usados en blueprints."""

    # Protocol
    def save_video(self, video: Any) -> bool:
        return bool(self.guardar(video))

    def get_video(self, id: str) -> Optional[Video]:
        return self.obtener_por_id(id)

    def get_all_videos(self, limit: int = 100) -> list:
        return self.obtener_todos(limit)

    def get_videos_by_socio(self, socio_id: str) -> list:
        return self.obtener_por_usuario(socio_id)

    def delete_video(self, id: str) -> bool:
        return self.eliminar(id)

    def guardar(self, video: Video) -> Video:
        from sqlalchemy import select
        db = SessionLocal()
        try:
            mid = getattr(video, "id", None) or getattr(video, "video_id", None)
            m = db.get(VideoModel, mid) if mid else None
            if m is None:
                m = VideoModel(id=mid or video.id)
                db.add(m)
            m.usuario = getattr(video, "usuario", "") or getattr(video, "user", "")
            m.workspace_id = getattr(video, "workspace_id", "general")
            m.titulo = getattr(video, "nombre_archivo", "") or getattr(video, "titulo", "")[:300]
            m.descripcion = getattr(video, "descripcion", "") or ""
            est = getattr(video, "estado", EstadoVideo.PENDIENTE)
            m.estado = est.value if hasattr(est, "value") else str(est)
            m.metadatos = getattr(video, "metadatos_ia", {}) or {}
            m.s3_uri = getattr(video, "ruta_archivo", "") or m.metadatos.get("s3_uri", "")
            m.storage_uri = m.metadatos.get("storage_uri", "")
            m.duracion_segundos = float(getattr(video, "duracion_segundos", 0) or m.metadatos.get("duracion_segundos", 0) or 0)
            db.commit()
            db.refresh(m)
            return _video_to_entity(m)
        except Exception as e:
            db.rollback()
            logger.error("SQL video guardar fallo: %s", e)
            raise
        finally:
            db.close()

    def obtener_por_id(self, video_id: str) -> Optional[Video]:
        db = SessionLocal()
        try:
            m = db.get(VideoModel, video_id)
            return _video_to_entity(m) if m else None
        finally:
            db.close()

    def obtener_todos(self, limit: int = 100) -> list[Video]:
        db = SessionLocal()
        try:
            rows = db.query(VideoModel).order_by(VideoModel.created_at.desc()).limit(limit).all()
            return [_video_to_entity(r) for r in rows]
        finally:
            db.close()

    def obtener_todos_paginado(self, limit: int = 20, cursor: Optional[str] = None):
        # Cursor opaco "created_at|id" coherente con el orden (created_at DESC, id DESC).
        # Evita duplicados/omisiones que causaba filtrar por id con orden por fecha.
        import base64
        import json as _json

        def _decode_cursor(raw: str):
            try:
                data = _json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
                return datetime.fromisoformat(data["created_at"]), data["id"]
            except Exception:
                return None, None

        db = SessionLocal()
        try:
            q = db.query(VideoModel).order_by(
                VideoModel.created_at.desc(), VideoModel.id.desc()
            )
            if cursor:
                cur_dt, cur_id = _decode_cursor(cursor)
                if cur_dt is not None:
                    # keyset: fila estrictamente "anterior" en el orden declarado
                    q = q.filter(
                        tuple_(VideoModel.created_at, VideoModel.id) < (cur_dt, cur_id)
                    )
            rows = q.limit(limit + 1).all()

            next_cursor = None
            if len(rows) > limit:
                rows = rows[:limit]
                last = rows[-1]
                payload = _json.dumps(
                    {"created_at": last.created_at.isoformat(), "id": last.id}
                )
                next_cursor = base64.urlsafe_b64encode(payload.encode()).decode()
            return [_video_to_entity(r) for r in rows], next_cursor
        finally:
            db.close()

    def obtener_por_usuario(self, usuario: str) -> list[Video]:
        db = SessionLocal()
        try:
            rows = db.query(VideoModel).filter(VideoModel.usuario == usuario).order_by(VideoModel.created_at.desc()).all()
            return [_video_to_entity(r) for r in rows]
        finally:
            db.close()

    def obtener_por_usuario_y_workspace(self, usuario: str, workspace_id: str) -> list[Video]:
        db = SessionLocal()
        try:
            rows = db.query(VideoModel).filter(VideoModel.usuario == usuario, VideoModel.workspace_id == workspace_id).all()
            return [_video_to_entity(r) for r in rows]
        finally:
            db.close()

    def obtener_por_estado(self, estado: EstadoVideo) -> list[Video]:
        val = estado.value if hasattr(estado, "value") else str(estado)
        db = SessionLocal()
        try:
            rows = db.query(VideoModel).filter(VideoModel.estado == val).all()
            return [_video_to_entity(r) for r in rows]
        finally:
            db.close()

    def obtener_pendientes(self) -> list[Video]:
        return self.obtener_por_estado(EstadoVideo.PENDIENTE)

    def eliminar(self, video_id: str) -> bool:
        db = SessionLocal()
        try:
            m = db.get(VideoModel, video_id)
            if not m:
                return False
            db.delete(m)
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    def actualizar_estado(self, video_id: str, nuevo_estado: EstadoVideo) -> bool:
        db = SessionLocal()
        try:
            m = db.get(VideoModel, video_id)
            if not m:
                return False
            m.estado = nuevo_estado.value if hasattr(nuevo_estado, "value") else str(nuevo_estado)
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    def contar_total(self) -> int:
        db = SessionLocal()
        try:
            return db.query(VideoModel).count()
        finally:
            db.close()

    def obtener_estadisticas(self) -> dict:
        total = self.contar_total()
        db = SessionLocal()
        try:
            from sqlalchemy import func
            rows = db.query(VideoModel.estado, func.count()).group_by(VideoModel.estado).all()
            by_estado = {k: v for k, v in rows}
            return {"videos": {"total": total, **by_estado}, "total": total}
        finally:
            db.close()

    def sync_videos_from_disk(self, upload_dir: str, usuario: str, workspace_id=None) -> dict:
        return {"synced": 0, "skipped": 0}


class SQLAlchemyUserRepository:
    def guardar(self, usuario: Usuario):
        return self.guardar_atomic(usuario)[2]

    def guardar_atomic(self, usuario: Usuario):
        db = SessionLocal()
        try:
            norm = (usuario.username or "").lower().strip()
            # dedup username
            existing = db.query(UserModel).filter(UserModel.username_normalized == norm).first()
            if existing and getattr(usuario, "id", None) != existing.id:
                return False, "username_exists", None
            m = None
            if getattr(usuario, "id", None):
                m = db.get(UserModel, usuario.id)
            if m is None and norm:
                m = db.query(UserModel).filter(UserModel.username_normalized == norm).first()
            if m is None:
                m = UserModel(id=getattr(usuario, "id", None) or __import__("uuid").uuid4().hex)
                db.add(m)
            m.username = usuario.username
            m.username_normalized = norm
            m.email = getattr(usuario, "email", "")
            m.email_normalized = (m.email or "").lower().strip()
            m.password_hash = getattr(usuario, "password_hash", "") or getattr(usuario, "password", "")
            m.nombre_completo = getattr(usuario, "nombre_completo", "") or usuario.username
            m.rol = getattr(usuario, "rol", RolUsuario.SOCIO).value if hasattr(getattr(usuario, "rol", RolUsuario.SOCIO), "value") else str(getattr(usuario, "rol", "socio"))
            m.activo = getattr(usuario, "activo", True)
            db.commit()
            db.refresh(m)
            return True, None, _usuario_to_entity(m)
        except Exception as e:
            db.rollback()
            logger.error("SQL user guardar fallo: %s", e)
            return False, str(e), None
        finally:
            db.close()

    def obtener_por_id(self, usuario_id: str) -> Optional[Usuario]:
        db = SessionLocal()
        try:
            m = db.get(UserModel, usuario_id)
            return _usuario_to_entity(m) if m else None
        finally:
            db.close()

    def obtener_por_username(self, username: str) -> Optional[Usuario]:
        db = SessionLocal()
        try:
            m = db.query(UserModel).filter(UserModel.username_normalized == username.lower().strip()).first()
            return _usuario_to_entity(m) if m else None
        finally:
            db.close()

    def obtener_por_email(self, email: str) -> Optional[Usuario]:
        db = SessionLocal()
        try:
            m = db.query(UserModel).filter(UserModel.email_normalized == email.lower().strip()).first()
            return _usuario_to_entity(m) if m else None
        finally:
            db.close()

    def obtener_todos(self) -> list[Usuario]:
        db = SessionLocal()
        try:
            return [_usuario_to_entity(r) for r in db.query(UserModel).all()]
        finally:
            db.close()

    def obtener_socios(self) -> list[Usuario]:
        return self.obtener_todos()

    def existe_username(self, username: str) -> bool:
        return self.obtener_por_username(username) is not None

    def existe_email(self, email: str) -> bool:
        return self.obtener_por_email(email) is not None

    def autenticar(self, username: str, password: str) -> Optional[Usuario]:
        u = self.obtener_por_username(username)
        if not u:
            return None
        try:
            # verificar_password está en entities.Usuario
            if hasattr(u, "verificar_password") and u.verificar_password(password):
                return u
            # fallback bcrypt
            import bcrypt
            if bcrypt.checkpw(password.encode(), u.password_hash.encode()):
                return u
        except Exception:
            pass
        return None

    def eliminar(self, usuario_id: str) -> bool:
        db = SessionLocal()
        try:
            m = db.get(UserModel, usuario_id)
            if not m:
                return False
            db.delete(m)
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    def contar_total(self) -> int:
        db = SessionLocal()
        try:
            return db.query(UserModel).count()
        finally:
            db.close()

    def contar_por_rol(self, rol: RolUsuario) -> int:
        db = SessionLocal()
        try:
            val = rol.value if hasattr(rol, "value") else str(rol)
            return db.query(UserModel).filter(UserModel.rol == val).count()
        finally:
            db.close()



