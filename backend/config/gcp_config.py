"""
Configuración centralizada para Google Cloud Platform
Carga variables de entorno y proporciona acceso a configuración GCP
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()


class GCPConfig:
    """
    Configuración de Google Cloud Platform

    Carga variables de entorno y proporciona valores por defecto
    """

    # Project Configuration
    PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "tivit-mira-prd")
    REGION: str = os.getenv("GCP_REGION", "us-central1")

    # Cloud Storage
    BUCKET_NAME: str = os.getenv("GCP_BUCKET_NAME", "tivit-mira-prd-videos")
    BUCKET_VIDEOS_FOLDER: str = "videos/"
    BUCKET_THUMBNAILS_FOLDER: str = "thumbnails/"
    
    # Storage Lifecycle Optimization
    STORAGE_CLASS_STANDARD: str = "STANDARD"
    STORAGE_CLASS_NEARLINE: str = "NEARLINE"
    STORAGE_CLASS_COLDLINE: str = "COLDLINE"
    
    LIFECYCLE_NEARLINE_DAYS: int = int(os.getenv("GCP_LIFECYCLE_NEARLINE_DAYS", "30"))
    LIFECYCLE_COLDLINE_DAYS: int = int(os.getenv("GCP_LIFECYCLE_COLDLINE_DAYS", "90"))
    LIFECYCLE_DELETE_TEMP_DAYS: int = int(os.getenv("GCP_LIFECYCLE_DELETE_TEMP_DAYS", "7"))

    # Firestore
    FIRESTORE_COLLECTION_VIDEOS: str = "videos"
    FIRESTORE_COLLECTION_USERS: str = "users"
    FIRESTORE_COLLECTION_LOGS: str = "logs"

    # Video Intelligence API
    VIDEO_INTELLIGENCE_FEATURES: list = [
        "LABEL_DETECTION",
        "EXPLICIT_CONTENT_DETECTION",
        "LOGO_RECOGNITION",
        "TEXT_DETECTION",
    ]

    # Signed URLs (tiempo de expiración)
    SIGNED_URL_EXPIRATION_MINUTES: int = 60

    @classmethod
    def validate_config(cls) -> tuple[bool, list[str]]:
        """
        Valida que la configuración GCP esté completa
        Returns: tuple: (is_valid: bool, errors: list[str])
        """
        errors = []

        if not cls.PROJECT_ID:
            errors.append("GCP_PROJECT_ID no está configurado")

        if not cls.BUCKET_NAME:
            errors.append("GCP_BUCKET_NAME no está configurado")

        return len(errors) == 0, errors

    @classmethod
    def is_gcp_enabled(cls) -> bool:
        """
        Verifica si GCP está habilitado y configurado correctamente
        Al usar Application Default Credentials, consideramos GCP habilitado por defecto.
        Returns: bool: True si la config mínima existe
        """
        is_valid, _ = cls.validate_config()
        return is_valid

    @classmethod
    def get_bucket_url(cls, filename: str, folder: str = None) -> str:
        """Genera URL pública de un archivo en el bucket"""
        if folder:
            return f"gs://{cls.BUCKET_NAME}/{folder}/{filename}"
        return f"gs://{cls.BUCKET_NAME}/{filename}"

    @classmethod
    def get_video_path(cls, video_id: str, extension: str = "mp4") -> str:
        """Genera la ruta completa de un video en GCS"""
        filename = f"{video_id}.{extension}"
        return f"{cls.BUCKET_VIDEOS_FOLDER}{filename}"

    @classmethod
    def get_config_summary(cls) -> dict:
        """Obtiene un resumen de la configuración GCP"""
        is_valid, errors = cls.validate_config()

        return {
            "enabled": cls.is_gcp_enabled(),
            "valid": is_valid,
            "errors": errors,
            "project_id": cls.PROJECT_ID,
            "region": cls.REGION,
            "bucket_name": cls.BUCKET_NAME,
            "firestore_collections": {
                "videos": cls.FIRESTORE_COLLECTION_VIDEOS,
                "users": cls.FIRESTORE_COLLECTION_USERS,
                "logs": cls.FIRESTORE_COLLECTION_LOGS,
            },
        }

# Exportar instancia única de configuración
config = GCPConfig()
