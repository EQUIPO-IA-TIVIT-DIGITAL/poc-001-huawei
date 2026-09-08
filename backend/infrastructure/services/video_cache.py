"""
Cache de análisis de video basado en hash SHA-256.
Evita reprocesar videos idénticos ya analizados.
"""
import hashlib
import logging
import json
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Cache TTL: 24 horas (retención máxima de videos)
CACHE_TTL_SECONDS = 24 * 3600


class VideoAnalysisCache:
    """
    Cache de análisis basado en hash del archivo de video.
    Solo reutiliza si el video es exactamente el mismo (mismo hash).
    
    Backend: Redis (si disponible), con fallback a memoria.
    """

    def __init__(self):
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._redis = None
        self._init_redis()

    def _init_redis(self):
        """Intenta conectar a Redis para cache persistente"""
        try:
            import os
            from redis import Redis
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
            self._redis = Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3)
            self._redis.ping()
            logger.info("✅ VideoAnalysisCache conectado a Redis")
        except Exception as e:
            logger.warning(f"⚠️ Redis no disponible para cache, usando memoria: {e}")
            self._redis = None

    def compute_hash(self, video_path: str, sample_size: int = 2 * 1024 * 1024) -> str:
        """
        Calcula SHA-256 del video usando los primeros N bytes + tamaño total.
        Combinación rápida y confiable para deteccion de duplicados exactos.
        
        Args:
            video_path: Ruta al archivo de video
            sample_size: Bytes a leer para hash (default: 2MB)
            
        Returns:
            Hash SHA-256 como hex string
        """
        import os
        hasher = hashlib.sha256()

        file_size = os.path.getsize(video_path)
        hasher.update(str(file_size).encode())

        with open(video_path, 'rb') as f:
            # Leer primer bloque
            data = f.read(sample_size)
            hasher.update(data)

            # Si el archivo tiene más datos, leer el último bloque también
            if file_size > sample_size * 2:
                f.seek(-sample_size, 2)
                data = f.read(sample_size)
                hasher.update(data)

        return hasher.hexdigest()

    def get_cached_analysis(self, video_hash: str) -> Optional[Dict[str, Any]]:
        """
        Busca un análisis previo en cache por hash del video.
        
        Returns:
            Dict con resultado del análisis o None si no existe/expirado
        """
        cache_key = f"video_analysis:{video_hash}"

        # Intentar Redis primero
        if self._redis:
            try:
                data = self._redis.get(cache_key)
                if data:
                    cached = json.loads(data)
                    if time.time() - cached.get("cached_at", 0) < CACHE_TTL_SECONDS:
                        logger.info(f"✅ Cache HIT (Redis) para hash {video_hash[:12]}...")
                        return cached.get("result")
                    else:
                        self._redis.delete(cache_key)
            except Exception as e:
                logger.warning(f"Error leyendo cache Redis: {e}")

        # Fallback a memoria
        if cache_key in self._memory_cache:
            cached = self._memory_cache[cache_key]
            if time.time() - cached.get("cached_at", 0) < CACHE_TTL_SECONDS:
                logger.info(f"✅ Cache HIT (memory) para hash {video_hash[:12]}...")
                return cached.get("result")
            else:
                del self._memory_cache[cache_key]

        return None

    def store_analysis(self, video_hash: str, result: Dict[str, Any]) -> None:
        """
        Almacena un resultado de análisis en cache.
        
        Args:
            video_hash: Hash SHA-256 del video
            result: Resultado completo del análisis
        """
        cache_key = f"video_analysis:{video_hash}"
        
        cache_entry = {
            "cached_at": time.time(),
            "result": result
        }

        # Guardar en Redis
        if self._redis:
            try:
                self._redis.setex(
                    cache_key,
                    CACHE_TTL_SECONDS,
                    json.dumps(cache_entry, default=str)
                )
                logger.info(f"💾 Análisis cacheado en Redis para hash {video_hash[:12]}...")
            except Exception as e:
                logger.warning(f"Error guardando en Redis cache: {e}")

        # Siempre guardar en memoria también
        self._memory_cache[cache_key] = cache_entry

        # Limpieza de memoria si crece mucho
        if len(self._memory_cache) > 500:
            self._cleanup_memory_cache()

    def invalidate_by_video_hash(self, video_hash: str) -> bool:
        """
        Elimina el cache de un video específico por su hash.
        
        Returns:
            True si se encontró y eliminó, False si no existía
        """
        cache_key = f"video_analysis:{video_hash}"
        deleted = False

        if self._redis:
            try:
                result = self._redis.delete(cache_key)
                if result:
                    deleted = True
                    logger.info(f"🗑️ Cache Redis eliminado para hash {video_hash[:12]}...")
            except Exception as e:
                logger.warning(f"Error eliminando cache Redis: {e}")

        if cache_key in self._memory_cache:
            del self._memory_cache[cache_key]
            deleted = True
            logger.info(f"🗑️ Cache memoria eliminado para hash {video_hash[:12]}...")

        return deleted

    def invalidate_all(self) -> int:
        """
        Elimina TODOS los caches de análisis de video.
        
        Returns:
            Número de entradas eliminadas
        """
        count = 0
        if self._redis:
            try:
                keys = self._redis.keys("video_analysis:*")
                if keys:
                    count = self._redis.delete(*keys)
                    logger.info(f"🗑️ {count} entradas de cache eliminadas de Redis")
            except Exception as e:
                logger.warning(f"Error limpiando cache Redis: {e}")

        mem_count = len(self._memory_cache)
        self._memory_cache.clear()
        count += mem_count
        return count

    def _cleanup_memory_cache(self):
        """Limpia entradas expiradas del cache en memoria"""
        now = time.time()
        expired = [
            k for k, v in self._memory_cache.items()
            if now - v.get("cached_at", 0) > CACHE_TTL_SECONDS
        ]
        for k in expired:
            del self._memory_cache[k]
        
        # Si aún hay muchas, eliminar las más antiguas
        if len(self._memory_cache) > 300:
            sorted_keys = sorted(
                self._memory_cache.keys(),
                key=lambda k: self._memory_cache[k].get("cached_at", 0)
            )
            for k in sorted_keys[:100]:
                del self._memory_cache[k]


# Singleton
_cache_instance = None

def get_video_analysis_cache() -> VideoAnalysisCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = VideoAnalysisCache()
    return _cache_instance
