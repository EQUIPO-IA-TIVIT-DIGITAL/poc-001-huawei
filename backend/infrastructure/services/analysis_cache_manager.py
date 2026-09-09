"""
Servicio de Caché de Análisis para Videos de Seguridad
Gestiona análisis on-demand y evita reprocesar clips
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class QueryRecord:
    """Registro de una consulta realizada"""
    fecha: str
    pregunta: str
    clips_analizados: List[str]
    costo: float
    tiempo_respuesta: float
    nivel_analisis: str  # basic | standard | detailed
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClipAnalysis:
    """Análisis completo de un clip"""
    clip_id: str
    analizado_fecha: str
    analizado_por_query: Optional[str]
    video_intelligence: Optional[Dict[str, Any]]
    costo_analisis: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AnalysisCacheManager:
    """
    Gestiona caché de análisis on-demand
    
    Funcionalidades:
    - Guardar análisis de clips procesados
    - Verificar si un clip ya fue analizado
    - Historial de consultas
    - Cálculo de costos acumulados
    """
    
    def __init__(self):
        """Inicializa el gestor de caché"""
        self._storage = None
        self._is_minio = False
        self._init_storage()
    
    def _init_storage(self):
        """Inicializa el servicio de almacenamiento local"""
        try:
            from config.app_config import AppConfig
            backend = getattr(AppConfig, "STORAGE_BACKEND", "filesystem")
            if backend == "minio":
                from infrastructure.adapters.minio_storage_adapter import MinioStorageAdapter
                self._storage = MinioStorageAdapter(AppConfig)
                self._is_minio = True
            else:
                from infrastructure.adapters.filesystem_storage_adapter import FilesystemStorageAdapter
                self._storage = FilesystemStorageAdapter()
            logger.info("Storage inicializado para caché")
        except Exception as e:
            logger.error(f"Error inicializando Storage: {e}")

    def _download_json(self, blob_name: str):
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            if self._is_minio:
                self._storage.download_file(blob_name, tmp_path)
            else:
                import shutil
                from pathlib import Path
                shutil.copy2(str(Path(self._storage.base_dir) / blob_name), tmp_path)
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                return None
            with open(tmp_path, "r", encoding="utf-8") as f:
                return json.load(f)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _upload_json(self, blob_name: str, data):
        json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._storage.upload_from_bytes(json_bytes, blob_name, content_type="application/json")
    
    def load_cache(self, video_id: str) -> Dict[str, Any]:
        """
        Carga el caché de análisis de un video
        
        Args:
            video_id: ID del video
        
        Returns:
            Caché como diccionario (vacío si no existe)
        """
        if hasattr(self, '_local_cache') and video_id in self._local_cache:
            logger.info(f"Caché cargado desde memoria local: {video_id}")
            return self._local_cache[video_id]
        
        if not self._storage:
            logger.warning("Storage no disponible, retornando caché vacío")
            return self._empty_cache()
        
        blob_name = f"security_videos/{video_id}/metadata/analysis_cache.json"
        
        try:
            cache_data = self._download_json(blob_name)
            
            if cache_data:
                logger.info(f"✅ Caché cargado: {video_id} ({len(cache_data.get('clips_analizados', {}))} clips)")
                return cache_data
            else:
                logger.info(f"📝 Caché nuevo para: {video_id}")
                return self._empty_cache()
                
        except Exception as e:
            logger.warning(f"⚠️ Error cargando caché (creando nuevo): {e}")
            return self._empty_cache()
    
    def save_cache(self, video_id: str, cache_data: Dict[str, Any]) -> bool:
        """
        Guarda el caché de análisis en almacenamiento
        
        Args:
            video_id: ID del video
            cache_data: Datos del caché
        
        Returns:
            True si se guardó correctamente
        """
        if not self._storage:
            logger.warning("Storage no disponible, caché no persistido")
            if not hasattr(self, '_local_cache'):
                self._local_cache = {}
            self._local_cache[video_id] = cache_data
            logger.info(f"Caché guardado en memoria local: {video_id}")
            return True
        
        blob_name = f"security_videos/{video_id}/metadata/analysis_cache.json"
        
        try:
            cache_data['ultima_actualizacion'] = datetime.utcnow().isoformat()
            self._upload_json(blob_name, cache_data)
            logger.info(f"Caché guardado: {video_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error guardando caché: {e}")
            return False
    
    def add_query_record(
        self,
        video_id: str,
        pregunta: str,
        clips_analizados: List[str],
        costo: float,
        tiempo_respuesta: float,
        nivel_analisis: str = "standard"
    ) -> bool:
        """
        Registra una consulta realizada
        
        Args:
            video_id: ID del video
            pregunta: Pregunta del usuario
            clips_analizados: IDs de clips analizados
            costo: Costo de la consulta
            tiempo_respuesta: Tiempo en segundos
            nivel_analisis: Nivel de análisis usado
        
        Returns:
            True si se registró correctamente
        """
        cache = self.load_cache(video_id)
        
        query_record = QueryRecord(
            fecha=datetime.utcnow().isoformat(),
            pregunta=pregunta,
            clips_analizados=clips_analizados,
            costo=costo,
            tiempo_respuesta=tiempo_respuesta,
            nivel_analisis=nivel_analisis
        )
        
        cache['queries_realizadas'].append(query_record.to_dict())
        cache['costo_total_queries'] += costo
        cache['total_queries'] += 1
        
        return self.save_cache(video_id, cache)
    
    def add_clip_analysis(
        self,
        video_id: str,
        clip_id: str,
        analysis_data: Dict[str, Any],
        costo: float,
        query_context: Optional[str] = None
    ) -> bool:
        """
        Agrega análisis de un clip al caché
        
        Args:
            video_id: ID del video
            clip_id: ID del clip
            analysis_data: Datos del análisis (Video Intelligence)
            costo: Costo del análisis
            query_context: Consulta que generó este análisis (opcional)
        
        Returns:
            True si se guardó correctamente
        """
        cache = self.load_cache(video_id)
        
        clip_analysis = ClipAnalysis(
            clip_id=clip_id,
            analizado_fecha=datetime.utcnow().isoformat(),
            analizado_por_query=query_context,
            video_intelligence=analysis_data,
            costo_analisis=costo
        )
        
        # Guardar o actualizar
        cache['clips_analizados'][clip_id] = clip_analysis.to_dict()
        cache['costo_total_analisis'] += costo
        
        return self.save_cache(video_id, cache)
    
    def is_clip_analyzed(self, video_id: str, clip_id: str) -> bool:
        """
        Verifica si un clip ya fue analizado
        
        Args:
            video_id: ID del video
            clip_id: ID del clip
        
        Returns:
            True si el clip ya tiene análisis
        """
        cache = self.load_cache(video_id)
        return clip_id in cache.get('clips_analizados', {})
    
    def get_clip_analysis(
        self, 
        video_id: str, 
        clip_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene el análisis de un clip si existe
        
        Args:
            video_id: ID del video
            clip_id: ID del clip
        
        Returns:
            Análisis del clip o None
        """
        cache = self.load_cache(video_id)
        return cache.get('clips_analizados', {}).get(clip_id)
    
    def get_unanalyzed_clips(
        self,
        video_id: str,
        clip_ids: List[str]
    ) -> List[str]:
        """
        Filtra clips que NO han sido analizados
        
        Args:
            video_id: ID del video
            clip_ids: Lista de IDs de clips
        
        Returns:
            Lista de IDs sin analizar
        """
        cache = self.load_cache(video_id)
        analyzed = cache.get('clips_analizados', {})
        
        return [clip_id for clip_id in clip_ids if clip_id not in analyzed]
    
    def get_cache_stats(self, video_id: str) -> Dict[str, Any]:
        """
        Obtiene estadísticas del caché
        
        Args:
            video_id: ID del video
        
        Returns:
            Estadísticas del caché
        """
        cache = self.load_cache(video_id)
        
        return {
            'total_queries': cache.get('total_queries', 0),
            'total_clips_analizados': len(cache.get('clips_analizados', {})),
            'costo_total_queries': cache.get('costo_total_queries', 0.0),
            'costo_total_analisis': cache.get('costo_total_analisis', 0.0),
            'costo_total_acumulado': (
                cache.get('costo_total_queries', 0.0) +
                cache.get('costo_total_analisis', 0.0)
            ),
            'ultima_actualizacion': cache.get('ultima_actualizacion', 'nunca')
        }
    
    def get_query_history(self, video_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene historial de consultas
        
        Args:
            video_id: ID del video
        
        Returns:
            Lista de consultas realizadas
        """
        cache = self.load_cache(video_id)
        return cache.get('queries_realizadas', [])
    
    def _empty_cache(self) -> Dict[str, Any]:
        """Crea estructura de caché vacío"""
        return {
            'version': '1.0',
            'tipo': 'analysis_cache',
            'creado': datetime.utcnow().isoformat(),
            'ultima_actualizacion': datetime.utcnow().isoformat(),
            'queries_realizadas': [],
            'clips_analizados': {},
            'total_queries': 0,
            'costo_total_queries': 0.0,
            'costo_total_analisis': 0.0
        }


# Singleton
_cache_manager = None

def get_cache_manager() -> AnalysisCacheManager:
    """Obtiene la instancia única del gestor de caché"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = AnalysisCacheManager()
    return _cache_manager
