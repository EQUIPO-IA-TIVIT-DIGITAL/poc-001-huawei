"""
Infraestructura de Repositorios - Persistencia de datos
Usa Firestore como backend principal
"""
from .user_repository import UsuarioRepositoryMemory, UsuarioRepositoryFirestore
from .video_repository import VideoRepositoryMemory, VideoRepositoryFirestore

__all__ = [
    'UsuarioRepositoryMemory', 
    'UsuarioRepositoryFirestore',
    'VideoRepositoryMemory',
    'VideoRepositoryFirestore'
]
