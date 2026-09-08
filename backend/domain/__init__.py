"""
Capa de Dominio - Clean Architecture
Contiene entidades y reglas de negocio puras sin dependencias externas
"""
from .entities import (
    Video, 
    EstadoVideo, 
    RolUsuario,
    Usuario,
    ReglaNegocioException
)

__all__ = [
    'Video', 
    'EstadoVideo', 
    'RolUsuario',
    'Usuario',
    'ReglaNegocioException'
]
