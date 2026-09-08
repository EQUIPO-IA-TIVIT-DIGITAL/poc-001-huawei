"""initial local 32B — pgvector + tablas espejo firestore"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "001_initial_local_32b"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    # videos
    op.create_table("videos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("usuario", sa.String(120), index=True),
        sa.Column("workspace_id", sa.String(64), index=True),
        sa.Column("titulo", sa.String(300)),
        sa.Column("descripcion", sa.Text),
        sa.Column("estado", sa.String(32), index=True),
        sa.Column("resultado_ia", sa.Text),
        sa.Column("razon_rechazo", sa.Text),
        sa.Column("gcs_uri", sa.String(500)),
        sa.Column("s3_uri", sa.String(500)),
        sa.Column("duracion_segundos", sa.Float),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("metadatos", sa.JSON),
    )
    op.create_table("users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(80), unique=True, index=True),
        sa.Column("username_normalized", sa.String(80), unique=True, index=True),
        sa.Column("email", sa.String(200), index=True),
        sa.Column("email_normalized", sa.String(200), index=True),
        sa.Column("password_hash", sa.String(200)),
        sa.Column("nombre_completo", sa.String(200)),
        sa.Column("rol", sa.String(32)),
        sa.Column("activo", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table("workspaces",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("usuario", sa.String(120), index=True),
        sa.Column("nombre", sa.String(200)),
        sa.Column("descripcion", sa.Text),
        sa.Column("categoria", sa.String(64)),
        sa.Column("nivel_tolerancia", sa.String(32)),
        sa.Column("eliminado", sa.Boolean, index=True, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table("operational_analyses",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("usuario", sa.String(120), index=True),
        sa.Column("analysis_type", sa.String(64)),
        sa.Column("estado", sa.String(32), index=True),
        sa.Column("s3_uri", sa.String(500)),
        sa.Column("custom_context", sa.Text),
        sa.Column("result", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table("operational_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("analysis_id", sa.String(64), index=True),
        sa.Column("timestamp_start", sa.Float, index=True),
        sa.Column("timestamp_end", sa.Float),
        sa.Column("event_type", sa.String(64)),
        sa.Column("description", sa.Text),
        sa.Column("metadata_json", sa.JSON),
    )
    op.create_table("audio_analyses",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("usuario", sa.String(120), index=True),
        sa.Column("estado", sa.String(32), index=True),
        sa.Column("s3_uri", sa.String(500)),
        sa.Column("language", sa.String(16)),
        sa.Column("result", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table("audio_segments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("analysis_id", sa.String(64), index=True),
        sa.Column("start_time", sa.Float, index=True),
        sa.Column("end_time", sa.Float),
        sa.Column("text", sa.Text),
        sa.Column("speaker", sa.String(64)),
        sa.Column("embedding", Vector(1024)),
    )
    op.create_table("security_videos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("usuario", sa.String(120), index=True),
        sa.Column("estado", sa.String(32), index=True),
        sa.Column("s3_uri", sa.String(500)),
        sa.Column("result", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table("security_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("video_id", sa.String(64), index=True),
        sa.Column("timestamp", sa.Float, index=True),
        sa.Column("event_type", sa.String(64)),
        sa.Column("description", sa.Text),
        sa.Column("risk_level", sa.String(16)),
        sa.Column("metadata_json", sa.JSON),
    )
    # HNSW index para bge-m3
    op.execute("CREATE INDEX audio_segments_embedding_idx ON audio_segments USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)")

def downgrade():
    for t in ["security_events","security_videos","audio_segments","audio_analyses","operational_events","operational_analyses","workspaces","users","videos"]:
        op.drop_table(t)
