"""
Cache Queries - Funciones de caché para queries frecuentes
Reduce carga en la base de datos cacheando datos de alta lectura
"""
from typing import Optional, List, Dict, Any
from .redis_cache import get_cache_instance, cached


# TTLs para diferentes tipos de datos (en segundos)
TTL_SIGNED_URL = 3500       # 58 minutos (URLs expiran en 1 hora)
TTL_USER_DATA = 300         # 5 minutos
TTL_VIDEO_LIST = 60         # 1 minuto
TTL_VIDEO_METADATA = 120    # 2 minutos
TTL_WORKSPACE = 180         # 3 minutos
TTL_ANALYTICS = 600         # 10 minutos


class CacheQueries:
    """
    Wrapper para queries cacheados a la base de datos
    """
    
    def __init__(self):
        self.cache = get_cache_instance()
    
    # =====================================
    # SIGNED URLS CACHE
    # =====================================
    
    def get_cached_upload_url(self, video_id: str) -> Optional[str]:
        """
        Obtiene URL de upload cacheada
        
        Args:
            video_id: ID del video
            
        Returns:
            URL firmada o None
        """
        return self.cache.get(f"upload_url:{video_id}")
    
    def cache_upload_url(self, video_id: str, url: str, ttl: int = TTL_SIGNED_URL) -> bool:
        """
        Cachea URL de upload
        
        Args:
            video_id: ID del video
            url: URL firmada
            ttl: Tiempo de vida
            
        Returns:
            True si se guardó
        """
        return self.cache.set(f"upload_url:{video_id}", url, ttl)
    
    def get_cached_download_url(self, video_path: str) -> Optional[str]:
        """
        Obtiene URL de descarga cacheada
        
        Args:
            video_path: Path del video en el almacenamiento
            
        Returns:
            URL firmada o None
        """
        key = f"download_url:{video_path.replace('/', ':')}"
        return self.cache.get(key)
    
    def cache_download_url(self, video_path: str, url: str, ttl: int = TTL_SIGNED_URL) -> bool:
        """
        Cachea URL de descarga
        
        Args:
            video_path: Path del video en el almacenamiento
            url: URL firmada
            ttl: Tiempo de vida
            
        Returns:
            True si se guardó
        """
        key = f"download_url:{video_path.replace('/', ':')}"
        return self.cache.set(key, url, ttl)
    
    # =====================================
    # USER DATA CACHE
    # =====================================
    
    def get_cached_user(self, user_id: str) -> Optional[Dict]:
        """
        Obtiene datos de usuario cacheados
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Datos del usuario o None
        """
        return self.cache.get(f"user:{user_id}")
    
    def cache_user(self, user_id: str, user_data: Dict, ttl: int = TTL_USER_DATA) -> bool:
        """
        Cachea datos de usuario
        
        Args:
            user_id: ID del usuario
            user_data: Datos del usuario
            ttl: Tiempo de vida
            
        Returns:
            True si se guardó
        """
        return self.cache.set(f"user:{user_id}", user_data, ttl)
    
    def invalidate_user(self, user_id: str) -> bool:
        """
        Invalida cache de usuario (después de actualización)
        
        Args:
            user_id: ID del usuario
            
        Returns:
            True si se invalidó
        """
        return self.cache.delete(f"user:{user_id}")
    
    # =====================================
    # VIDEO LIST CACHE
    # =====================================
    
    def get_cached_video_list(self, workspace_id: str, page: int = 1, limit: int = 20) -> Optional[Dict]:
        """
        Obtiene lista de videos cacheada
        
        Args:
            workspace_id: ID del workspace
            page: Número de página
            limit: Elementos por página
            
        Returns:
            Lista de videos o None
        """
        return self.cache.get(f"videos:{workspace_id}:{page}:{limit}")
    
    def cache_video_list(self, workspace_id: str, videos: Dict, page: int = 1, limit: int = 20, ttl: int = TTL_VIDEO_LIST) -> bool:
        """
        Cachea lista de videos
        
        Args:
            workspace_id: ID del workspace
            videos: Lista de videos con metadata
            page: Número de página
            limit: Elementos por página
            ttl: Tiempo de vida
            
        Returns:
            True si se guardó
        """
        return self.cache.set(f"videos:{workspace_id}:{page}:{limit}", videos, ttl)
    
    def invalidate_video_list(self, workspace_id: str) -> int:
        """
        Invalida todas las listas de videos de un workspace
        
        Args:
            workspace_id: ID del workspace
            
        Returns:
            Número de claves eliminadas
        """
        return self.cache.delete_pattern(f"videos:{workspace_id}:*")
    
    # =====================================
    # VIDEO METADATA CACHE
    # =====================================
    
    def get_cached_video(self, video_id: str) -> Optional[Dict]:
        """
        Obtiene metadata de video cacheada
        
        Args:
            video_id: ID del video
            
        Returns:
            Metadata del video o None
        """
        return self.cache.get(f"video:{video_id}")
    
    def cache_video(self, video_id: str, video_data: Dict, ttl: int = TTL_VIDEO_METADATA) -> bool:
        """
        Cachea metadata de video
        
        Args:
            video_id: ID del video
            video_data: Metadata del video
            ttl: Tiempo de vida
            
        Returns:
            True si se guardó
        """
        return self.cache.set(f"video:{video_id}", video_data, ttl)
    
    def invalidate_video(self, video_id: str) -> bool:
        """
        Invalida cache de video
        
        Args:
            video_id: ID del video
            
        Returns:
            True si se invalidó
        """
        return self.cache.delete(f"video:{video_id}")
    
    # =====================================
    # WORKSPACE CACHE
    # =====================================
    
    def get_cached_workspace(self, workspace_id: str) -> Optional[Dict]:
        """
        Obtiene datos de workspace cacheados
        
        Args:
            workspace_id: ID del workspace
            
        Returns:
            Datos del workspace o None
        """
        return self.cache.get(f"workspace:{workspace_id}")
    
    def cache_workspace(self, workspace_id: str, workspace_data: Dict, ttl: int = TTL_WORKSPACE) -> bool:
        """
        Cachea datos de workspace
        
        Args:
            workspace_id: ID del workspace
            workspace_data: Datos del workspace
            ttl: Tiempo de vida
            
        Returns:
            True si se guardó
        """
        return self.cache.set(f"workspace:{workspace_id}", workspace_data, ttl)
    
    def invalidate_workspace(self, workspace_id: str) -> bool:
        """
        Invalida cache de workspace
        
        Args:
            workspace_id: ID del workspace
            
        Returns:
            True si se invalidó
        """
        # Invalidar workspace y sus videos
        self.cache.delete(f"workspace:{workspace_id}")
        self.invalidate_video_list(workspace_id)
        return True
    
    def get_cached_user_workspaces(self, user_id: str) -> Optional[List[Dict]]:
        """
        Obtiene lista de workspaces de usuario cacheada
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Lista de workspaces o None
        """
        return self.cache.get(f"user_workspaces:{user_id}")
    
    def cache_user_workspaces(self, user_id: str, workspaces: List[Dict], ttl: int = TTL_WORKSPACE) -> bool:
        """
        Cachea lista de workspaces de usuario
        
        Args:
            user_id: ID del usuario
            workspaces: Lista de workspaces
            ttl: Tiempo de vida
            
        Returns:
            True si se guardó
        """
        return self.cache.set(f"user_workspaces:{user_id}", workspaces, ttl)
    
    def invalidate_user_workspaces(self, user_id: str) -> bool:
        """
        Invalida cache de workspaces de usuario
        
        Args:
            user_id: ID del usuario
            
        Returns:
            True si se invalidó
        """
        return self.cache.delete(f"user_workspaces:{user_id}")
    
    # =====================================
    # ANALYTICS CACHE
    # =====================================
    
    def get_cached_analytics(self, scope: str, scope_id: str) -> Optional[Dict]:
        """
        Obtiene analytics cacheados
        
        Args:
            scope: Tipo de scope (user, workspace, global)
            scope_id: ID del scope
            
        Returns:
            Analytics o None
        """
        return self.cache.get(f"analytics:{scope}:{scope_id}")
    
    def cache_analytics(self, scope: str, scope_id: str, analytics: Dict, ttl: int = TTL_ANALYTICS) -> bool:
        """
        Cachea analytics
        
        Args:
            scope: Tipo de scope
            scope_id: ID del scope
            analytics: Datos de analytics
            ttl: Tiempo de vida
            
        Returns:
            True si se guardó
        """
        return self.cache.set(f"analytics:{scope}:{scope_id}", analytics, ttl)
    
    # =====================================
    # ESTADÍSTICAS
    # =====================================
    
    def get_stats(self) -> Dict:
        """
        Obtiene estadísticas del cache
        
        Returns:
            Diccionario con estadísticas
        """
        return self.cache.get_stats()


# Singleton
_cache_queries_instance: Optional[CacheQueries] = None


def get_cache_queries() -> CacheQueries:
    """
    Obtiene instancia singleton de CacheQueries
    
    Returns:
        Instancia de CacheQueries
    """
    global _cache_queries_instance
    if _cache_queries_instance is None:
        _cache_queries_instance = CacheQueries()
    return _cache_queries_instance
