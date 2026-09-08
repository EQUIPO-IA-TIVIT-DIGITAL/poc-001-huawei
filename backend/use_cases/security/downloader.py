import os
import shutil
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class SecurityVideoDownloader:
    """Extrae la lógica de caché y descarga (Responsabilidad Única)"""
    MAX_CACHE_SIZE_BYTES = 5 * 1024 * 1024 * 1024

    def __init__(self, optimized_processor):
        self.optimized_processor = optimized_processor

    def download_or_get_cached(self, video_id: str, ruta_gcs: str) -> str:
        cached_path = self.get_cached_video_path(video_id)
        if cached_path:
            return cached_path
        
        local_video_path = self.optimized_processor.download_from_gcs(ruta_gcs)
        self.cache_video(video_id, local_video_path)
        return local_video_path

    def get_cached_video_path(self, video_id: str) -> Optional[str]:
        cache_dir = "/tmp/video_cache"
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
        
        cache_path = os.path.join(cache_dir, f"{video_id}.mp4")
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
            os.utime(cache_path, None)
            return cache_path
        return None

    def cache_video(self, video_id: str, video_path: str):
        try:
            cache_dir = "/tmp/video_cache"
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir, exist_ok=True)
            
            cache_path = os.path.join(cache_dir, f"{video_id}.mp4")
            if not os.path.exists(cache_path):
                file_size = os.path.getsize(video_path) if os.path.exists(video_path) else 0
                self.evict_cache_lru(needed_bytes=file_size)
                shutil.copy2(video_path, cache_path)
                logger.info("💾 Video cacheado para futuros reintentos")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo cachear video: {e}")

    def clear_video_cache(self, video_id: str):
        try:
            cache_path = self.get_cached_video_path(video_id)
            if cache_path and os.path.exists(cache_path):
                os.remove(cache_path)
                logger.info("🧹 Video removido del caché")
        except Exception as e:
            logger.warning(f"⚠️ Error limpiando caché: {e}")

    def evict_cache_lru(self, needed_bytes: int = 0):
        cache_dir = "/tmp/video_cache"
        if not os.path.exists(cache_dir):
            return
        try:
            files = []
            total_size = 0
            for f in os.listdir(cache_dir):
                fp = os.path.join(cache_dir, f)
                if os.path.isfile(fp):
                    stat = os.stat(fp)
                    files.append((fp, stat.st_atime, stat.st_size))
                    total_size += stat.st_size
            
            target = self.MAX_CACHE_SIZE_BYTES - needed_bytes
            if total_size <= target:
                return
            
            files.sort(key=lambda x: x[1])
            for fp, _, size in files:
                if total_size <= target:
                    break
                try:
                    os.remove(fp)
                    total_size -= size
                    logger.info(f"🧹 Cache LRU: evicted {os.path.basename(fp)}")
                except OSError:
                    pass
        except Exception as e:
            logger.warning(f"⚠️ Error en cache LRU eviction: {e}")
