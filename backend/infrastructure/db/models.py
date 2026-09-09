"""
SQLAlchemy models — local offline 32B
Tablas espejo de las colecciones de dominio. pgvector para embeddings.
"""
from sqlalchemy import String, Integer, Float, Boolean, Text, DateTime, JSON, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from infrastructure.db.base import Base
import uuid
from datetime import datetime

def gen_id() -> str:
    return str(uuid.uuid4())

class VideoModel(Base):
    __tablename__ = "videos"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_id)
    usuario: Mapped[str] = mapped_column(String(120), index=True)
    workspace_id: Mapped[str] = mapped_column(String(64), index=True, default="general")
    titulo: Mapped[str] = mapped_column(String(300), default="")
    descripcion: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(String(32), default="PENDIENTE", index=True)
    resultado_ia: Mapped[str] = mapped_column(Text, default="")
    razon_rechazo: Mapped[str] = mapped_column(Text, default="")
    storage_uri: Mapped[str] = mapped_column(String(500), default="")
    s3_uri: Mapped[str] = mapped_column(String(500), default="")
    duracion_segundos: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    metadatos: Mapped[dict] = mapped_column(JSON, default=dict)

class UserModel(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_id)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    username_normalized: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(200), index=True)
    email_normalized: Mapped[str] = mapped_column(String(200), index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    nombre_completo: Mapped[str] = mapped_column(String(200), default="")
    rol: Mapped[str] = mapped_column(String(32), default="socio")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class WorkspaceModel(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_id)
    usuario: Mapped[str] = mapped_column(String(120), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    categoria: Mapped[str] = mapped_column(String(64), default="general")
    nivel_tolerancia: Mapped[str] = mapped_column(String(32), default="medio")
    es_general: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    eliminado: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    metadatos: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

class WorkspaceAuditModel(Base):
    __tablename__ = "workspace_audit_logs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_id)
    usuario: Mapped[str] = mapped_column(String(120), index=True)
    workspace_id: Mapped[str] = mapped_column(String(64), index=True)
    accion: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

class AIUsageLogModel(Base):
    __tablename__ = "ai_usage_logs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_id)
    usuario: Mapped[str] = mapped_column(String(120), index=True)
    fecha: Mapped[str] = mapped_column(String(16), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class AIDailyLimitModel(Base):
    __tablename__ = "ai_daily_limits"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)  # usuario_fecha
    usuario: Mapped[str] = mapped_column(String(120), index=True)
    fecha: Mapped[str] = mapped_column(String(16), index=True)
    requests_count: Mapped[int] = mapped_column(Integer, default=0)
    tokens_count: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    last_updated: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class AIResponseCacheModel(Base):
    __tablename__ = "ai_response_cache"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_id)
    prompt_hash: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(64), index=True)
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class OperationalAnalysisModel(Base):
    __tablename__ = "operational_analyses"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario: Mapped[str] = mapped_column(String(120), index=True)
    analysis_type: Mapped[str] = mapped_column(String(64))
    estado: Mapped[str] = mapped_column(String(32), default="PENDIENTE", index=True)
    s3_uri: Mapped[str] = mapped_column(String(500), default="")
    custom_context: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

class OperationalEventModel(Base):
    __tablename__ = "operational_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_id)
    analysis_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp_start: Mapped[float] = mapped_column(Float, index=True)
    timestamp_end: Mapped[float] = mapped_column(Float)
    event_type: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

class AudioAnalysisModel(Base):
    __tablename__ = "audio_analyses"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario: Mapped[str] = mapped_column(String(120), index=True)
    estado: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    s3_uri: Mapped[str] = mapped_column(String(500), default="")
    language: Mapped[str] = mapped_column(String(16), default="es")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

class AudioSegmentModel(Base):
    __tablename__ = "audio_segments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_id)
    analysis_id: Mapped[str] = mapped_column(String(64), index=True)
    start_time: Mapped[float] = mapped_column(Float, index=True)
    end_time: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text, default="")
    speaker: Mapped[str] = mapped_column(String(64), default="SPEAKER_1")
    embedding: Mapped[list] = mapped_column(Vector(1024), nullable=True)  # bge-m3 1024

class SecurityVideoModel(Base):
    __tablename__ = "security_videos"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario: Mapped[str] = mapped_column(String(120), index=True)
    estado: Mapped[str] = mapped_column(String(32), default="PENDIENTE", index=True)
    s3_uri: Mapped[str] = mapped_column(String(500), default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class SecurityEventModel(Base):
    __tablename__ = "security_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_id)
    video_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[float] = mapped_column(Float, index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(16), default="BAJO")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

class SecurityAnalysisModel(Base):
    __tablename__ = "security_analyses"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_id)
    video_id: Mapped[str] = mapped_column(String(64), index=True)
    contexto: Mapped[str] = mapped_column(Text, default="")
    modo: Mapped[str] = mapped_column(String(16), default="ESTANDAR")
    estado: Mapped[str] = mapped_column(String(32), default="PENDIENTE", index=True)
    usuario_id: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[str] = mapped_column(String(120), index=True)
    fecha_solicitud: Mapped[str] = mapped_column(String(64), default="")
    resultado: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
