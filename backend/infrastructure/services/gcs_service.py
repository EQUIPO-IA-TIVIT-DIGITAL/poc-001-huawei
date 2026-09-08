"""
Servicio para gestionar subidas directas a Google Cloud Storage usando Signed URLs
"""
from google.cloud import storage
from datetime import datetime, timedelta
import os
import uuid
from werkzeug.utils import secure_filename

_ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
}


import logging
logger = logging.getLogger(__name__)


def _build_signing_credentials():
    """
    Retorna credenciales aptas para firmar Signed URLs.

    - Si las credenciales ADC ya tienen clave privada (Service Account JSON)
      se devuelven tal cual.
    - Si son credenciales de usuario (ADC con `gcloud auth login`), se crea
      un firmante impersonado usando el rol serviceAccountTokenCreator, de
      modo que no se necesita ningún archivo JSON en local.
    """
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError

    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    # Si ya puede firmar (p.ej. SA con clave privada) no hacemos nada más
    if hasattr(credentials, 'service_account_email') and hasattr(credentials, 'sign_bytes'):
        return credentials, project

    # Credenciales de usuario → impersonar la SA configurada
    sa_email = os.getenv(
        'GCS_SIGNING_SERVICE_ACCOUNT',
        'tivit-mira-sa@tivit-mira-prd.iam.gserviceaccount.com'
    )
    logger.info(
        "ADC credentials cannot sign URLs directly; "
        f"impersonating service account: {sa_email}"
    )
    from google.auth import impersonated_credentials
    target_credentials = impersonated_credentials.Credentials(
        source_credentials=credentials,
        target_principal=sa_email,
        target_scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
        lifetime=3600,
    )
    return target_credentials, project


class GCSService:
    """Servicio para gestionar uploads a GCS con Signed URLs"""

    def __init__(self):
        """Inicializa el cliente de GCS con credenciales aptas para firmar."""
        signing_credentials, _ = _build_signing_credentials()
        self.signing_credentials = signing_credentials
        self.client = storage.Client(credentials=signing_credentials)
        self.bucket_name = os.getenv('GCS_BUCKET_NAME', 'cu002-videos-prod-cu02')
        self.bucket = self.client.bucket(self.bucket_name)

    def generate_upload_url(self, filename: str, content_type: str, user_id: int) -> dict:
        """
        Genera URL firmada para subida directa a GCS
        
        Args:
            filename: Nombre del archivo original
            content_type: ignorado — el MIME se deriva de la extensión validada
            user_id: ID del usuario que sube el archivo
        
        Returns:
            {
                'upload_url': URL firmada (válida 1 hora),
                'blob_name': Ruta completa en GCS,
                'public_url': URL pública del archivo
            }
        """
        # Sanitizar nombre y validar extensión en el servidor
        safe_name = secure_filename(filename)
        if not safe_name:
            raise ValueError("Nombre de archivo inválido")
        file_extension = os.path.splitext(safe_name)[1].lower()
        if file_extension not in _ALLOWED_VIDEO_EXTENSIONS:
            raise ValueError(
                f"Extensión no permitida: {file_extension!r}. "
                f"Permitidas: {', '.join(_ALLOWED_VIDEO_EXTENSIONS)}"
            )
        # Derivar content_type del servidor, nunca del cliente
        server_content_type = _ALLOWED_VIDEO_EXTENSIONS[file_extension]
        # Generar nombre único para evitar colisiones
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        # Organizar por usuario y mes para mejor gestión
        current_date = datetime.now()
        blob_name = f"videos/{user_id}/{current_date.strftime('%Y%m')}/{unique_filename}"
        
        blob = self.bucket.blob(blob_name)
        
        # Generar URL firmada con método PUT (content_type derivado del servidor)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=1),
            method="PUT",
            content_type=server_content_type
        )
        
        return {
            'upload_url': url,
            'blob_name': blob_name,
            'public_url': f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}",
            'bucket': self.bucket_name,
            'content_type': server_content_type,
        }
    
    def generate_download_url(self, blob_name: str, expiration_minutes: int = 60) -> str:
        """
        Genera URL firmada para descarga/visualización
        
        Args:
            blob_name: Ruta del archivo en GCS
            expiration_minutes: Minutos de validez de la URL
        
        Returns:
            URL firmada para descarga
        """
        blob = self.bucket.blob(blob_name)
        
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET"
        )
        
        return url
    
    def check_blob_exists(self, blob_name: str) -> bool:
        """
        Verifica si un archivo existe en GCS
        
        Args:
            blob_name: Ruta del archivo en GCS
        
        Returns:
            True si existe, False si no
        """
        blob = self.bucket.blob(blob_name)
        return blob.exists()
    
    def delete_blob(self, blob_name: str) -> bool:
        """
        Elimina un archivo de GCS
        
        Args:
            blob_name: Ruta del archivo en GCS
        
        Returns:
            True si se eliminó correctamente
        """
        try:
            blob = self.bucket.blob(blob_name)
            blob.delete()
            return True
        except Exception as e:
            logger.info(f"Error deleting blob {blob_name}: {e}")
            return False
    
    def get_blob_metadata(self, blob_name: str) -> dict:
        """
        Obtiene metadata de un archivo en GCS
        
        Args:
            blob_name: Ruta del archivo en GCS
        
        Returns:
            Diccionario con metadata del archivo
        """
        blob = self.bucket.blob(blob_name)
        blob.reload()
        
        return {
            'name': blob.name,
            'size': blob.size,
            'content_type': blob.content_type,
            'created': blob.time_created,
            'updated': blob.updated,
            'md5_hash': blob.md5_hash
        }
