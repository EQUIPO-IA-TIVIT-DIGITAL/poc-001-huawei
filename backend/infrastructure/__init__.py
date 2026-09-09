"""
Capa de Infraestructura - Clean Architecture
Implementaciones locales para almacenamiento, datos, colas e IA.
"""
from .dependencies import (
    get_storage_adapter,
    get_database_adapter,
    get_user_repository,
    get_video_processor,
    get_ai_service,
    get_ai_adapter,
    get_task_queue,
    verificar_conexion_local,
    init_dependencies
)

from .rate_limiter import (
    LOGIN_LIMIT,
    REGISTRO_LIMIT,
    UPLOAD_LIMIT,
    API_LIMIT
)

__all__ = [
    # Dependency Injection
    'get_storage_adapter',
    'get_database_adapter',
    'get_user_repository',
    'get_video_processor',
    'get_ai_service',
    'get_ai_adapter',
    'get_task_queue',
    'verificar_conexion_local',
    'init_dependencies',
    # Rate Limiting
    'LOGIN_LIMIT',
    'REGISTRO_LIMIT',
    'UPLOAD_LIMIT',
    'API_LIMIT',
]
