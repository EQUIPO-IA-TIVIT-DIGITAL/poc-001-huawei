"""
minio_storage_adapter — S3-compat (boto3) para MinIO / filesystem fallback
Implementa IStorageAdapter + StorageAdapterProtocol (upload_video, is_available, get_signed_url)
"""
import logging
import mimetypes
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class MinioStorageAdapter:
    def __init__(self, config=None):
        # config usa AppConfig.
        try:
            from config.app_config import AppConfig
            cfg = config or AppConfig
            self.endpoint = getattr(cfg, "S3_ENDPOINT", None) or os.getenv("S3_ENDPOINT")
            self.bucket = getattr(cfg, "S3_BUCKET", None) or getattr(cfg, "BUCKET_NAME", "cu002-videos")
            self.access_key = getattr(cfg, "S3_ACCESS_KEY", None) or os.getenv("S3_ACCESS_KEY") or os.getenv("MINIO_ROOT_USER")
            self.secret_key = getattr(cfg, "S3_SECRET_KEY", None) or os.getenv("S3_SECRET_KEY") or os.getenv("MINIO_ROOT_PASSWORD")
            self.region = getattr(cfg, "S3_REGION", "us-east-1")
            self.use_ssl = bool(getattr(cfg, "S3_USE_SSL", False))
        except Exception:
            self.endpoint = os.getenv("S3_ENDPOINT")
            self.bucket = os.getenv("S3_BUCKET", "cu002-videos")
            self.access_key = os.getenv("S3_ACCESS_KEY") or os.getenv("MINIO_ROOT_USER")
            self.secret_key = os.getenv("S3_SECRET_KEY") or os.getenv("MINIO_ROOT_PASSWORD")
            self.region = "us-east-1"
            self.use_ssl = False
        self._client = None

    def _get_client(self):
        missing = [name for name, value in (("S3_ENDPOINT", self.endpoint), ("S3_ACCESS_KEY", self.access_key), ("S3_SECRET_KEY", self.secret_key)) if not value]
        if missing:
            raise RuntimeError(f"MinIO configuration missing required values: {', '.join(missing)}")
        if self._client is None:
            import boto3
            from botocore.config import Config
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                config=Config(signature_version="s3v4"),
                use_ssl=self.use_ssl,
            )
            # ensure bucket exists (idempotent)
            try:
                self._client.head_bucket(Bucket=self.bucket)
            except Exception:
                try:
                    self._client.create_bucket(Bucket=self.bucket)
                    logger.info("MinIO bucket creado: %s", self.bucket)
                except Exception as e:
                    logger.warning("MinIO create_bucket fallo %s: %s", self.bucket, e)
        return self._client

    def is_available(self) -> bool:
        try:
            c = self._get_client()
            c.head_bucket(Bucket=self.bucket)
            return True
        except Exception as e:
            logger.debug("MinIO no disponible %s: %s", self.endpoint, e)
            return False

    # ---- IStorageAdapter compat ----
    def subir_archivo(self, archivo_local: str, destino: str) -> str:
        return self.upload_file(archivo_local, destino) or ""

    def descargar_archivo(self, origen: str, archivo_local: str) -> bool:
        try:
            self._get_client().download_file(self.bucket, origen, archivo_local)
            return True
        except Exception as e:
            logger.error("MinIO download fallo %s: %s", origen, e)
            return False

    def eliminar_archivo(self, ruta: str) -> bool:
        return self.delete_file(ruta)

    def obtener_url_firmada(self, ruta: str, expiracion_minutos: int = 60) -> str:
        return self.generate_signed_url(ruta, expiracion_minutos) or ""

    # ---- Protocolo de almacenamiento ----
    def upload_video(self, file_path: str | Path, video_id: str, content_type: str = "video/mp4", metadata=None) -> Optional[str]:
        key = f"videos/{video_id}{Path(file_path).suffix or '.mp4'}"
        return self.upload_file(str(file_path), key, content_type)

    def upload_from_stream(self, file_stream, video_id: str, content_type: str = "video/mp4", metadata=None) -> Optional[str]:
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".mp4")
        try:
            os.close(fd)
            with open(tmp, "wb") as out:
                out.write(file_stream.read() if hasattr(file_stream, "read") else file_stream)
            return self.upload_video(tmp, video_id, content_type)
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    def upload_from_bytes(self, data: bytes, blob_path: str, content_type: str = "image/jpeg", metadata=None) -> Optional[str]:
        try:
            c = self._get_client()
            c.put_object(Bucket=self.bucket, Key=blob_path, Body=data, ContentType=content_type)
            return f"s3://{self.bucket}/{blob_path}"
        except Exception as e:
            logger.error("MinIO put_object fallo %s: %s", blob_path, e)
            return None

    def upload_file(self, local_path: str, blob_name: str, content_type: Optional[str] = None, return_signed_url: bool = False) -> Optional[str]:
        ct = content_type or mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        try:
            c = self._get_client()
            c.upload_file(local_path, self.bucket, blob_name, ExtraArgs={"ContentType": ct})
            s3uri = f"s3://{self.bucket}/{blob_name}"
            if return_signed_url:
                return self.generate_signed_url(blob_name) or s3uri
            return s3uri
        except Exception as e:
            logger.error("MinIO upload fallo %s -> %s: %s", local_path, blob_name, e)
            return None

    def generate_signed_url(self, blob_name: str, expiration_minutes: Optional[int] = None) -> Optional[str]:
        try:
            exp = int(expiration_minutes or 60) * 60
            return self._get_client().generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": blob_name}, ExpiresIn=exp)
        except Exception as e:
            logger.warning("MinIO presigned fallo %s: %s", blob_name, e)
            return None

    def generate_signed_url_from_storage_uri(self, storage_uri: str, expiration_minutes: int = 60) -> Optional[str]:
        key = storage_uri.split(f"{self.bucket}/")[-1] if self.bucket in storage_uri else storage_uri.split("/")[-1]
        # si es s3://, extrae key
        if "://" in storage_uri:
            parts = storage_uri.split("://", 1)[1]
            # parts = bucket/key
            if "/" in parts:
                key = parts.split("/", 1)[1]
        return self.generate_signed_url(key, expiration_minutes)

    def delete_video(self, video_id: str, extension: str = "mp4") -> bool:
        return self.delete_file(f"videos/{video_id}.{extension}")

    def delete_file(self, blob_name: str) -> bool:
        try:
            self._get_client().delete_object(Bucket=self.bucket, Key=blob_name)
            return True
        except Exception as e:
            logger.error("MinIO delete fallo %s: %s", blob_name, e)
            return False

    def video_exists(self, video_id: str, extension: str = "mp4") -> bool:
        try:
            self._get_client().head_object(Bucket=self.bucket, Key=f"videos/{video_id}.{extension}")
            return True
        except Exception:
            return False

    def get_video_metadata(self, video_id: str, extension: str = "mp4") -> Optional[dict]:
        try:
            r = self._get_client().head_object(Bucket=self.bucket, Key=f"videos/{video_id}.{extension}")
            return {"content_type": r.get("ContentType"), "size": r.get("ContentLength"), "metadata": r.get("Metadata", {})}
        except Exception:
            return None

    def list_videos(self, prefix: Optional[str] = None) -> list[str]:
        try:
            r = self._get_client().list_objects_v2(Bucket=self.bucket, Prefix=prefix or "videos/")
            return [o["Key"] for o in r.get("Contents", [])]
        except Exception:
            return []

    def get_storage_stats(self) -> dict:
        try:
            r = self._get_client().list_objects_v2(Bucket=self.bucket)
            count = r.get("KeyCount", 0)
            size = sum(o.get("Size", 0) for o in r.get("Contents", []))
            return {"bucket": self.bucket, "endpoint": self.endpoint, "count": count, "size_bytes": size}
        except Exception as e:
            return {"bucket": self.bucket, "error": str(e)}

    def get_storage_uri(self, storage_path: str) -> str:
        return f"s3://{self.bucket}/{storage_path.lstrip('/')}"

    def download_video(self, video_id: str, destination_path: str, extension: str = "mp4") -> Optional[str]:
        key = f"videos/{video_id}.{extension}"
        ok = self.descargar_archivo(key, destination_path)
        return destination_path if ok else None

    # alias compat
    def get_signed_url(self, storage_path: str, expiration_minutes: int = 60) -> Optional[str]:
        return self.generate_signed_url(storage_path, expiration_minutes)
