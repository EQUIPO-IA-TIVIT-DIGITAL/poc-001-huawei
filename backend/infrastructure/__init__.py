"""
Capa de Infraestructura - Clean Architecture
Sistema GCP-only: Todas las implementaciones usan Google Cloud Platform
"""
from .dependencies import (
    get_storage_adapter,
    get_firestore_adapter,
    get_user_repository,
    get_video_processor,
    get_ai_service,
    get_gemini_adapter,
    get_cloud_tasks_adapter,
    verificar_conexion_gcp,
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
    'get_firestore_adapter',
    'get_user_repository',
    'get_video_processor',
    'get_ai_service',
    'get_gemini_adapter',
    'get_cloud_tasks_adapter',
    'verificar_conexion_gcp',
    'init_dependencies',
    # Rate Limiting
    'LOGIN_LIMIT',
    'REGISTRO_LIMIT',
    'UPLOAD_LIMIT',
    'API_LIMIT',
]
