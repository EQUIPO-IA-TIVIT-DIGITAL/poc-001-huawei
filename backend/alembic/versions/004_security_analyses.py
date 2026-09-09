"""create security analyses"""
from alembic import op
import sqlalchemy as sa


revision = "004_security_analyses"
down_revision = "003_rename_videos_storage_uri"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "security_analyses",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("video_id", sa.String(64), index=True),
        sa.Column("contexto", sa.Text),
        sa.Column("modo", sa.String(16)),
        sa.Column("estado", sa.String(32), index=True),
        sa.Column("usuario_id", sa.String(64), index=True),
        sa.Column("username", sa.String(120), index=True),
        sa.Column("fecha_solicitud", sa.String(64)),
        sa.Column("resultado", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("security_analyses")
