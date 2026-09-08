"""
filesystem_storage_adapter — Fallback sin MinIO (dev offline puro)
Guarda en ./uploads/videos/<id>.mp4, genera URLs relativas /socio/media/<id>
"""
import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FilesystemStorageAdapter:
    def __init__(self, base_dir: Optional[str | Path] = None):
        from config.app_config import AppConfig
        self.base_dir = Path(base_dir or Path(__file__).parent.parent.parent / "uploads")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "videos").mkdir(parents=True, exist_ok=True)
        self.bucket = getattr(AppConfig, "S3_BUCKET", "cu002-videos")

    def is_available(self) -> bool:
        return self.base_dir.exists()

    # IStorageAdapter
    def subir_archivo(self, archivo_local: str, destino: str) -> str:
        return self.upload_file(archivo_local, destino) or ""
    def descargar_archivo(self, origen: str, archivo_local: str) -> bool:
        try:
            shutil.copy2(self.base_dir / origen, archivo_local)
            return True
        except Exception:
            return False
    def eliminar_archivo(self, ruta: str) -> bool:
        return self.delete_file(ruta)
    def obtener_url_firmada(self, ruta: str, expiracion_minutos: int = 60) -> str:
        return f"/socio/media/{Path(ruta).stem}"

    # Protocol
    def upload_video(self, file_path: str | Path, video_id: str, content_type: str = "video/mp4", metadata=None) -> Optional[str]:
        ext = Path(file_path).suffix or ".mp4"
        dest = self.base_dir / "videos" / f"{video_id}{ext}"
        try:
            shutil.copy2(str(file_path), str(dest))
            return f"file://{dest}"
        except Exception as e:
            logger.error("Filesystem upload fallo %s: %s", file_path, e)
            return None

    def upload_file(self, local_path: str, blob_name: str, content_type=None, return_signed_url=False) -> Optional[str]:
        dest = self.base_dir / blob_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(local_path, str(dest))
            return f"file://{dest}"
        except Exception as e:
            logger.error("Filesystem upload_file fallo: %s", e)
            return None

    def upload_from_bytes(self, data: bytes, blob_path: str, content_type="image/jpeg", metadata=None) -> Optional[str]:
        dest = self.base_dir / blob_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_bytes(data)
            return f"file://{dest}"
        except Exception:
            return None

    def generate_signed_url(self, blob_name: str, expiration_minutes=None) -> Optional[str]:
        # sin S3, retorna proxy path
        stem = Path(blob_name).stem
        return f"/socio/media/{stem}"

    def generate_signed_url_from_gcs_uri(self, gcs_uri: str, expiration_minutes=60) -> Optional[str]:
        return self.generate_signed_url(gcs_uri, expiration_minutes)

    def delete_video(self, video_id: str, extension="mp4") -> bool:
        return self.delete_file(f"videos/{video_id}.{extension}")

    def delete_file(self, blob_name: str) -> bool:
        p = self.base_dir / blob_name
        try:
            if p.exists():
                p.unlink()
            return True
        except Exception:
            return False

    def video_exists(self, video_id: str, extension="mp4") -> bool:
        return (self.base_dir / "videos" / f"{video_id}.{extension}").exists()
    def get_video_metadata(self, video_id: str, extension="mp4") -> Optional[dict]:
        p = self.base_dir / "videos" / f"{video_id}.{extension}"
        if not p.exists():
            return None
        return {"size": p.stat().st_size}
    def list_videos(self, prefix=None) -> list[str]:
        return [str(p.relative_to(self.base_dir)) for p in (self.base_dir / "videos").glob("*")]
    def get_storage_stats(self) -> dict:
        vids = list((self.base_dir / "videos").glob("*"))
        return {"bucket": str(self.base_dir), "count": len(vids), "size_bytes": sum(p.stat().st_size for p in vids)}
    def get_gcs_uri(self, gcs_path: str) -> str:
        return f"file://{self.base_dir / gcs_path}"
    def download_video(self, video_id: str, destination_path: str, extension="mp4") -> Optional[str]:
        src = self.base_dir / "videos" / f"{video_id}.{extension}"
        try:
            shutil.copy2(str(src), destination_path)
            return destination_path
        except Exception:
            return None
    def get_signed_url(self, gcs_path: str, expiration_minutes=60) -> Optional[str]:
        return self.generate_signed_url(gcs_path, expiration_minutes)
