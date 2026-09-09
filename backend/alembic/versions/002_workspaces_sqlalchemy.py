"""migrate workspaces to sqlalchemy: new columns + audit/ai tables"""
from alembic import op
import sqlalchemy as sa

revision = "002_workspaces_sqlalchemy"
down_revision = "001_initial_local_32b"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("workspaces", sa.Column("es_general", sa.Boolean, server_default="false", index=True))
    op.add_column("workspaces", sa.Column("metadatos", sa.JSON, nullable=True))
    op.create_table("workspace_audit_logs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("usuario", sa.String(120), index=True),
        sa.Column("workspace_id", sa.String(64), index=True),
        sa.Column("accion", sa.String(64)),
        sa.Column("data", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )
    op.create_table("ai_usage_logs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("usuario", sa.String(120), index=True),
        sa.Column("fecha", sa.String(16), index=True),
        sa.Column("data", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table("ai_daily_limits",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("usuario", sa.String(120), index=True),
        sa.Column("fecha", sa.String(16), index=True),
        sa.Column("requests_count", sa.Integer, server_default="0"),
        sa.Column("tokens_count", sa.Integer, server_default="0"),
        sa.Column("total_cost_usd", sa.Float, server_default="0"),
        sa.Column("last_updated", sa.String(64), server_default=""),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table("ai_response_cache",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("prompt_hash", sa.String(64), index=True),
        sa.Column("model", sa.String(64), index=True),
        sa.Column("response", sa.JSON),
        sa.Column("timestamp", sa.String(64), index=True),
        sa.Column("expires_at", sa.String(64), server_default=""),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

def downgrade():
    op.drop_table("ai_response_cache")
    op.drop_table("ai_daily_limits")
    op.drop_table("ai_usage_logs")
    op.drop_table("workspace_audit_logs")
    op.drop_column("workspaces", "metadatos")
    op.drop_column("workspaces", "es_general")
