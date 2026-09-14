"""
Infraestructura de Repositorios - Persistencia de datos
Implementación única: PostgreSQL/SQLite vía SQLAlchemy.

Aliases legacy mantenidos por compatibilidad con imports existentes;
todos resuelven a las implementaciones SQLAlchemy.
"""
from .sqlalchemy_repositories import (
    SQLAlchemyVideoRepository,
    SQLAlchemyUserRepository,
    VideoRepositoryMemory,
    VideoRepositoryFirestore,
    UsuarioRepositoryMemory,
    UsuarioRepositoryFirestore,
)

__all__ = [
    'SQLAlchemyVideoRepository',
    'SQLAlchemyUserRepository',
    # Aliases deprecados (eliminables cuando no queden referencias)
    'VideoRepositoryMemory',
    'VideoRepositoryFirestore',
    'UsuarioRepositoryMemory',
    'UsuarioRepositoryFirestore',
]
