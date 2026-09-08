"""
Servicio de Gestión de Índices para Videos de Seguridad
Maneja la creación, almacenamiento y carga de índices ligeros en GCS
Arquitectura Lazy: indexar rápido, analizar on-demand
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ClipIndexEntry:
    """Entrada de un clip en el índice"""
    id: str
    timestamp_inicio: float
    timestamp_fin: float
    duracion: float
    ruta_clip: str
    ruta_frame: str
    motion_intensity: float
    clasificacion_rapida: str  # NORMAL, SOSPECHOSO, IMPORTANTE
    descripcion_basica: str
    confianza: float
    tags_rapidos: List[str]
    analisis_profundo: Optional[str]  # 'pending' | 'completed' | None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario serializable"""
        return asdict(self)


@dataclass
class VideoIndexMetadata:
    """Metadata del índice de un video"""
    video_id: str
    nombre_camara: str
    ubicacion: str
    fecha_grabacion: str
    duracion_total: float
    fps: float
    estado: str
    fecha_indexado: str
    tiempo_procesamiento: float
    costo_indexado: float
    total_clips: int
    clips_por_clasificacion: Dict[str, int]
    distribucion_horaria: Dict[str, int]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario serializable"""
        return asdict(self)


class SecurityIndexManager:
    """
    Gestiona índices ligeros de videos de seguridad
    
    Responsabilidades:
    - Crear índices estructurados (index.json)
    - Guardar/cargar desde GCS
    - Validar integridad
    - Proporcionar estadísticas básicas
    """
    
    def __init__(self):
        """Inicializa el gestor de índices"""
        self.gcs_storage = None
        self._init_storage()
    
    def _init_storage(self):
        """Inicializa el servicio de GCS"""
        try:
            from infrastructure.adapters.gcp_storage import GCSStorageAdapter
            self.gcs_storage = GCSStorageAdapter()
            logger.info("✅ GCS Storage inicializado para índices")
        except Exception as e:
            logger.error(f"❌ Error inicializando GCS Storage: {e}")
    
    def create_index(
        self,
        video_id: str,
        video_metadata: Dict[str, Any],
        clips: List[Dict[str, Any]],
        processing_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Crea un índice estructurado de un video
        
        Args:
            video_id: ID del video
            video_metadata: Info del video (cámara, ubicación, etc)
            clips: Lista de clips procesados
            processing_stats: Estadísticas de procesamiento
        
        Returns:
            Índice completo como diccionario
        """
        logger.info(f"📝 Creando índice para video: {video_id}")
        
        # Convertir clips a formato de índice
        clips_indexados = []
        for clip in clips:
            clip_entry = ClipIndexEntry(
                id=clip.get('id', f"clip_{len(clips_indexados):03d}"),
                timestamp_inicio=clip.get('timestamp_inicio', 0.0),
                timestamp_fin=clip.get('timestamp_fin', 0.0),
                duracion=clip.get('duracion', 0.0),
                ruta_clip=clip.get('clip_path_gcs', ''),
                ruta_frame=clip.get('frame_path', ''),
                motion_intensity=clip.get('motion_intensity', 0.0),
                clasificacion_rapida=clip.get('clasificacion', 'NORMAL'),
                descripcion_basica=clip.get('descripcion_gemini', ''),
                confianza=clip.get('confianza', 0.0),
                tags_rapidos=clip.get('tags', []),
                analisis_profundo=None
            )
            clips_indexados.append(clip_entry.to_dict())
        
        # Calcular estadísticas básicas
        estadisticas = self._calculate_basic_stats(clips_indexados)
        
        # Crear metadata del índice
        metadata = VideoIndexMetadata(
            video_id=video_id,
            nombre_camara=video_metadata.get('nombre_camara', ''),
            ubicacion=video_metadata.get('ubicacion', ''),
            fecha_grabacion=video_metadata.get('fecha_grabacion', ''),
            duracion_total=video_metadata.get('duracion_segundos', 0.0),
            fps=video_metadata.get('fps', 30.0),
            estado='INDEXED',
            fecha_indexado=datetime.utcnow().isoformat(),
            tiempo_procesamiento=processing_stats.get('tiempo_segundos', 0.0),
            costo_indexado=processing_stats.get('costo_estimado', 0.0),
            total_clips=len(clips_indexados),
            clips_por_clasificacion=estadisticas['por_clasificacion'],
            distribucion_horaria=estadisticas['distribucion_horaria']
        )
        
        # Construir índice completo
        index = {
            'version': '1.0',
            'tipo': 'security_video_index',
            'metadata': metadata.to_dict(),
            'clips': clips_indexados,
            'estadisticas_basicas': estadisticas
        }
        
        logger.info(f"✅ Índice creado: {len(clips_indexados)} clips")
        return index
    
    def save_index_to_gcs(self, video_id: str, index_data: Dict[str, Any]) -> str:
        """
        Guarda el índice en GCS
        
        Args:
            video_id: ID del video
            index_data: Datos del índice
        
        Returns:
            Ruta GCS del índice guardado
        """
        if not self.gcs_storage:
            logger.error("❌ GCS Storage no disponible")
            raise RuntimeError("GCS Storage no inicializado")
        
        # Ruta en GCS
        gcs_path = f"security_videos/{video_id}/metadata/index.json"
        
        try:
            # Serializar a JSON
            json_content = json.dumps(index_data, indent=2, ensure_ascii=False)
            
            # Subir a GCS
            blob = self.gcs_storage.upload_json(
                gcs_path,
                index_data,
                content_type='application/json'
            )
            
            full_path = f"gs://{self.gcs_storage.bucket_name}/{gcs_path}"
            logger.info(f"✅ Índice guardado en: {full_path}")
            return full_path
            
        except Exception as e:
            logger.error(f"❌ Error guardando índice: {e}")
            raise
    
    def load_index_from_gcs(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Carga un índice desde GCS
        
        Args:
            video_id: ID del video
        
        Returns:
            Índice como diccionario o None si no existe
        """
        if not self.gcs_storage:
            logger.error("❌ GCS Storage no disponible")
            return None
        
        gcs_path = f"security_videos/{video_id}/metadata/index.json"
        
        try:
            # Descargar y parsear
            index_data = self.gcs_storage.download_json(gcs_path)
            
            if index_data:
                logger.info(f"✅ Índice cargado: {video_id}")
                return index_data
            else:
                logger.warning(f"⚠️ Índice no encontrado: {video_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error cargando índice: {e}")
            return None
    
    def get_clips_by_classification(
        self, 
        index_data: Dict[str, Any], 
        clasificacion: str
    ) -> List[Dict[str, Any]]:
        """
        Filtra clips por clasificación
        
        Args:
            index_data: Índice del video
            clasificacion: NORMAL, SOSPECHOSO, IMPORTANTE
        
        Returns:
            Lista de clips filtrados
        """
        clips = index_data.get('clips', [])
        return [
            clip for clip in clips 
            if clip.get('clasificacion_rapida', '').upper() == clasificacion.upper()
        ]
    
    def get_clips_by_timerange(
        self,
        index_data: Dict[str, Any],
        inicio_segundos: float,
        fin_segundos: float
    ) -> List[Dict[str, Any]]:
        """
        Filtra clips por rango temporal
        
        Args:
            index_data: Índice del video
            inicio_segundos: Tiempo de inicio (segundos)
            fin_segundos: Tiempo de fin (segundos)
        
        Returns:
            Lista de clips en el rango
        """
        clips = index_data.get('clips', [])
        return [
            clip for clip in clips
            if clip.get('timestamp_inicio', 0) >= inicio_segundos
            and clip.get('timestamp_fin', 0) <= fin_segundos
        ]
    
    def get_clips_by_tags(
        self,
        index_data: Dict[str, Any],
        tags: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Filtra clips que contengan alguno de los tags
        
        Args:
            index_data: Índice del video
            tags: Lista de tags a buscar
        
        Returns:
            Lista de clips que coinciden
        """
        clips = index_data.get('clips', [])
        tags_lower = [tag.lower() for tag in tags]
        
        matching_clips = []
        for clip in clips:
            clip_tags = clip.get('tags_rapidos', [])
            clip_tags_lower = [tag.lower() for tag in clip_tags]
            
            # Si algún tag coincide
            if any(tag in clip_tags_lower for tag in tags_lower):
                matching_clips.append(clip)
        
        return matching_clips
    
    def _calculate_basic_stats(self, clips: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcula estadísticas básicas de los clips"""
        stats = {
            'total_clips': len(clips),
            'por_clasificacion': {
                'NORMAL': 0,
                'SOSPECHOSO': 0,
                'IMPORTANTE': 0
            },
            'distribucion_horaria': {
                '00-06': 0,
                '06-12': 0,
                '12-18': 0,
                '18-24': 0
            },
            'duracion_total_clips': 0.0,
            'motion_intensity_promedio': 0.0
        }
        
        for clip in clips:
            # Conteo por clasificación
            clasificacion = clip.get('clasificacion_rapida', 'NORMAL').upper()
            if clasificacion in stats['por_clasificacion']:
                stats['por_clasificacion'][clasificacion] += 1
            
            # Distribución horaria
            timestamp = clip.get('timestamp_inicio', 0)
            hora = int((timestamp / 3600) % 24)
            
            if 0 <= hora < 6:
                stats['distribucion_horaria']['00-06'] += 1
            elif 6 <= hora < 12:
                stats['distribucion_horaria']['06-12'] += 1
            elif 12 <= hora < 18:
                stats['distribucion_horaria']['12-18'] += 1
            else:
                stats['distribucion_horaria']['18-24'] += 1
            
            # Duración y motion
            stats['duracion_total_clips'] += clip.get('duracion', 0)
            stats['motion_intensity_promedio'] += clip.get('motion_intensity', 0)
        
        # Promedios
        if len(clips) > 0:
            stats['motion_intensity_promedio'] /= len(clips)
        
        return stats
    
    def validate_index(self, index_data: Dict[str, Any]) -> bool:
        """
        Valida la integridad de un índice
        
        Args:
            index_data: Índice a validar
        
        Returns:
            True si el índice es válido
        """
        required_keys = ['version', 'tipo', 'metadata', 'clips']
        
        for key in required_keys:
            if key not in index_data:
                logger.error(f"❌ Índice inválido: falta clave '{key}'")
                return False
        
        clips = index_data.get('clips', [])
        if not isinstance(clips, list):
            logger.error("❌ Índice inválido: 'clips' no es una lista")
            return False
        
        logger.info("✅ Índice validado correctamente")
        return True


# Singleton
_index_manager = None

def get_index_manager() -> SecurityIndexManager:
    """Obtiene la instancia única del gestor de índices"""
    global _index_manager
    if _index_manager is None:
        _index_manager = SecurityIndexManager()
    return _index_manager
