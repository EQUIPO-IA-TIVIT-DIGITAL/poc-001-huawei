"""
Infraestructura de Repositorios - Persistencia de datos
Implementación única: PostgreSQL/SQLite vía SQLAlchemy.
"""
from .sqlalchemy_repositories import (
    SQLAlchemyVideoRepository,
    SQLAlchemyUserRepository,
)

__all__ = [
    'SQLAlchemyVideoRepository',
    'SQLAlchemyUserRepository',
]
