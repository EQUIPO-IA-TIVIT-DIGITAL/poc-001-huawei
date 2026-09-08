"""
Redis Cache Service para CU002
Proporciona caching de queries frecuentes para reducir carga en Cloud SQL/Firestore
"""
import json
import os
import logging
from typing import Optional, Any
from functools import wraps

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis no instalado - cache deshabilitado")

class RedisCache:
    """
    Servicio de cache usando Redis Memorystore
    """
    
    def __init__(self, host: str = None, port: int = 6379, db: int = 0):
        """
        Inicializa conexión a Redis
        
        Args:
            host: IP de Redis Memorystore (ej: 10.0.0.3)
            port: Puerto de Redis (default: 6379)
            db: Número de base de datos Redis (default: 0)
        """
        self.host = host or os.environ.get('REDIS_HOST', 'localhost')
        self.port = port
        self.db = db
        self.client = None
        self.enabled = False
        
        if REDIS_AVAILABLE:
            try:
                redis_url = os.environ.get('REDIS_URL')
                if redis_url:
                    self.client = redis.Redis.from_url(
                        redis_url,
                        socket_timeout=5,
                        socket_connect_timeout=5,
                        decode_responses=True
                    )
                else:
                    self.client = redis.Redis(
                        host=self.host,
                        port=self.port,
                        db=self.db,
                        socket_timeout=5,
                        socket_connect_timeout=5,
                        decode_responses=True
                    )
                # Test connection
                self.client.ping()
                self.enabled = True
                logger.info(f"Redis conectado: {redis_url or f'{self.host}:{self.port}'}")
            except Exception as e:
                logger.warning(f"Redis no disponible: {e}")
                self.enabled = False
    
    def get(self, key: str) -> Optional[Any]:
        """
        Obtiene valor del cache
        
        Args:
            key: Clave del cache
            
        Returns:
            Valor deserializado o None si no existe
        """
        if not self.enabled:
            return None
        
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Redis GET error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Guarda valor en cache
        
        Args:
            key: Clave del cache
            value: Valor a guardar (será serializado a JSON)
            ttl: Tiempo de vida en segundos (default: 5 minutos)
            
        Returns:
            True si se guardó correctamente
        """
        if not self.enabled:
            return False
        
        try:
            serialized = json.dumps(value, default=str)
            self.client.setex(key, ttl, serialized)
            return True
        except Exception as e:
            logger.warning(f"Redis SET error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Elimina clave del cache
        
        Args:
            key: Clave a eliminar
            
        Returns:
            True si se eliminó
        """
        if not self.enabled:
            return False
        
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Redis DELETE error: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """
        Elimina todas las claves que coincidan con un patrón
        
        Args:
            pattern: Patrón de búsqueda (ej: "user:123:*")
            
        Returns:
            Número de claves eliminadas
        """
        if not self.enabled:
            return 0
        
        try:
            keys = self.client.keys(pattern)
            if keys:
                return self.client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Redis DELETE_PATTERN error: {e}")
            return 0
    
    def flush_all(self) -> bool:
        """
        Limpia todo el cache (usar con cuidado)
        
        Returns:
            True si se limpió correctamente
        """
        if not self.enabled:
            return False
        
        try:
            self.client.flushdb()
            return True
        except Exception as e:
            logger.warning(f"Redis FLUSH error: {e}")
            return False
    
    def get_stats(self) -> dict:
        """
        Obtiene estadísticas del cache
        
        Returns:
            Diccionario con estadísticas
        """
        if not self.enabled:
            return {"enabled": False}
        
        try:
            info = self.client.info()
            return {
                "enabled": True,
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "total_keys": self.client.dbsize(),
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(info)
            }
        except Exception as e:
            return {"enabled": True, "error": str(e)}
    
    def _calculate_hit_rate(self, info: dict) -> float:
        """Calcula tasa de aciertos del cache"""
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)


def cached(ttl: int = 300, key_prefix: str = ""):
    """
    Decorador para cachear resultados de funciones
    
    Args:
        ttl: Tiempo de vida en segundos
        key_prefix: Prefijo para la clave del cache
        
    Uso:
        @cached(ttl=600, key_prefix="videos")
        def get_videos(user_id):
            return db.query(...)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Construir clave única
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Intentar obtener del cache
            cache = get_cache_instance()
            cached_value = cache.get(cache_key)
            
            if cached_value is not None:
                return cached_value
            
            # Ejecutar función y cachear resultado
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


# Singleton para la instancia del cache
_cache_instance: Optional[RedisCache] = None


def get_cache_instance() -> RedisCache:
    """
    Obtiene instancia singleton del cache
    
    Returns:
        Instancia de RedisCache
    """
    global _cache_instance
    if _cache_instance is None:
        redis_host = os.environ.get('REDIS_HOST', 'localhost')
        _cache_instance = RedisCache(host=redis_host)
    return _cache_instance


def init_cache(host: str, port: int = 6379) -> RedisCache:
    """
    Inicializa el cache con configuración específica
    
    Args:
        host: IP de Redis
        port: Puerto de Redis
        
    Returns:
        Instancia de RedisCache
    """
    global _cache_instance
    _cache_instance = RedisCache(host=host, port=port)
    return _cache_instance
