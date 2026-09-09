"""rename videos gcs URI column to storage URI"""
from alembic import op
import sqlalchemy as sa


revision = "003_rename_videos_storage_uri"
down_revision = "002_workspaces_sqlalchemy"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "videos" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("videos")}
    if "gcs_uri" in columns and "storage_uri" not in columns:
        with op.batch_alter_table("videos") as batch_op:
            batch_op.alter_column("gcs_uri", new_column_name="storage_uri")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "videos" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("videos")}
    if "storage_uri" in columns and "gcs_uri" not in columns:
        with op.batch_alter_table("videos") as batch_op:
            batch_op.alter_column("storage_uri", new_column_name="gcs_uri")
