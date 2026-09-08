import os
import sys
from pathlib import Path

# añade backend al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from alembic import context
from dotenv import load_dotenv

load_dotenv()

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

# url desde env DATABASE_URL (si postgres) o sqlite
db_url = os.getenv("DATABASE_URL", "sqlite:///./cu002.db")
config.set_main_option("sqlalchemy.url", db_url)

from infrastructure.db.base import Base  # type: ignore
import infrastructure.db.models  # noqa: F401 ensure models registered

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine
    connectable = create_engine(config.get_main_option("sqlalchemy.url"), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
