"""
Servicio de limpieza de archivos huérfanos.

Este servicio se encarga de limpiar archivos que ya no están asociados
a ningún video en el sistema (archivos huérfanos).
"""

import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Protocol, Optional

logger = logging.getLogger(__name__)


class VideoRepositoryProtocol(Protocol):
    """Protocolo para el repositorio de videos"""
    def listar_todos(self) -> List[Any]:
        ...
    def obtener(self, video_id: str) -> Optional[Any]:
        ...


class StorageProtocol(Protocol):
    """Protocolo para el almacenamiento en la nube"""
    def listar_archivos(self, prefix: str = "") -> List[str]:
        ...
    def eliminar(self, ruta: str) -> bool:
        ...


class CleanupService:
    """
    Servicio para limpiar archivos huérfanos del sistema.
    
    Los archivos huérfanos son aquellos que existen en el sistema de archivos
    o en el almacenamiento en la nube, pero que ya no están asociados a ningún
    video en la base de datos.
    """
    
    def __init__(
        self,
        video_repository: VideoRepositoryProtocol,
        upload_folder: str,
        storage_adapter: Optional[StorageProtocol] = None,
        max_age_hours: int = 24
    ):
        """
        Inicializa el servicio de limpieza.
        
        Args:
            video_repository: Repositorio para consultar videos
            upload_folder: Carpeta local de uploads
            storage_adapter: Adaptador de almacenamiento en la nube (opcional)
            max_age_hours: Edad máxima en horas para considerar un archivo huérfano
        """
        self.video_repository = video_repository
        self.upload_folder = Path(upload_folder)
        self.storage_adapter = storage_adapter
        self.max_age_hours = max_age_hours
    
    def limpiar_archivos_locales(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        Limpia archivos huérfanos del sistema de archivos local.
        
        Args:
            dry_run: Si es True, solo simula la limpieza sin eliminar archivos
            
        Returns:
            Dict con estadísticas de la limpieza
        """
        resultado = {
            "archivos_analizados": 0,
            "archivos_huerfanos": 0,
            "archivos_eliminados": 0,
            "espacio_liberado_bytes": 0,
            "errores": [],
            "dry_run": dry_run
        }
        
        if not self.upload_folder.exists():
            logger.warning(f"Carpeta de uploads no existe: {self.upload_folder}")
            return resultado
        
        # Obtener IDs de videos existentes
        try:
            videos = self.video_repository.listar_todos()
            video_ids = set()
            for video in videos:
                video_ids.add(video.id)
                # También agregar el nombre de archivo si existe
                if hasattr(video, 'nombre_archivo') and video.nombre_archivo:
                    video_ids.add(Path(video.nombre_archivo).stem)
        except Exception as e:
            logger.error(f"Error obteniendo videos: {e}")
            resultado["errores"].append(f"Error obteniendo videos: {e}")
            return resultado
        
        # Tiempo límite para considerar huérfanos
        tiempo_limite = datetime.now() - timedelta(hours=self.max_age_hours)
        
        # Escanear archivos en uploads
        extensiones_video = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}
        
        for archivo in self.upload_folder.iterdir():
            if not archivo.is_file():
                continue
                
            resultado["archivos_analizados"] += 1
            
            # Verificar si es un archivo de video
            if archivo.suffix.lower() not in extensiones_video:
                continue
            
            # Extraer ID del nombre del archivo (formato: uuid.extension)
            archivo_id = archivo.stem
            
            # Verificar si el archivo está asociado a un video
            if archivo_id in video_ids:
                continue
            
            # Verificar si el archivo es lo suficientemente viejo
            try:
                stat = archivo.stat()
                fecha_creacion = datetime.fromtimestamp(stat.st_mtime)
                
                if fecha_creacion > tiempo_limite:
                    # Archivo demasiado reciente, puede estar siendo procesado
                    logger.debug(f"Archivo reciente, omitiendo: {archivo.name}")
                    continue
                
                resultado["archivos_huerfanos"] += 1
                resultado["espacio_liberado_bytes"] += stat.st_size
                
                if not dry_run:
                    try:
                        archivo.unlink()
                        resultado["archivos_eliminados"] += 1
                        logger.info(f"Archivo huérfano eliminado: {archivo.name}")
                    except Exception as e:
                        error_msg = f"Error eliminando {archivo.name}: {e}"
                        logger.error(error_msg)
                        resultado["errores"].append(error_msg)
                else:
                    logger.info(f"[DRY RUN] Se eliminaría: {archivo.name}")
                    
            except Exception as e:
                error_msg = f"Error procesando {archivo.name}: {e}"
                logger.error(error_msg)
                resultado["errores"].append(error_msg)
        
        return resultado
    
    def limpiar_archivos_cloud(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        Limpia archivos huérfanos del almacenamiento en la nube.
        
        Args:
            dry_run: Si es True, solo simula la limpieza sin eliminar archivos
            
        Returns:
            Dict con estadísticas de la limpieza
        """
        resultado = {
            "archivos_analizados": 0,
            "archivos_huerfanos": 0,
            "archivos_eliminados": 0,
            "errores": [],
            "dry_run": dry_run
        }
        
        if not self.storage_adapter:
            logger.warning("No hay adaptador de almacenamiento en la nube configurado")
            return resultado
        
        # Obtener IDs de videos existentes
        try:
            videos = self.video_repository.listar_todos()
            video_ids = set(video.id for video in videos)
        except Exception as e:
            logger.error(f"Error obteniendo videos: {e}")
            resultado["errores"].append(f"Error obteniendo videos: {e}")
            return resultado
        
        # Listar archivos en el bucket
        try:
            archivos_cloud = self.storage_adapter.listar_archivos("videos/")
        except Exception as e:
            logger.error(f"Error listando archivos en la nube: {e}")
            resultado["errores"].append(f"Error listando archivos: {e}")
            return resultado
        
        for archivo_path in archivos_cloud:
            resultado["archivos_analizados"] += 1
            
            # Extraer ID del nombre del archivo
            archivo_nombre = Path(archivo_path).stem
            
            if archivo_nombre in video_ids:
                continue
            
            resultado["archivos_huerfanos"] += 1
            
            if not dry_run:
                try:
                    if self.storage_adapter.eliminar(archivo_path):
                        resultado["archivos_eliminados"] += 1
                        logger.info(f"Archivo cloud huérfano eliminado: {archivo_path}")
                    else:
                        resultado["errores"].append(f"No se pudo eliminar: {archivo_path}")
                except Exception as e:
                    error_msg = f"Error eliminando {archivo_path}: {e}"
                    logger.error(error_msg)
                    resultado["errores"].append(error_msg)
            else:
                logger.info(f"[DRY RUN] Se eliminaría en cloud: {archivo_path}")
        
        return resultado
    
    def ejecutar_limpieza_completa(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        Ejecuta limpieza completa de archivos huérfanos (local y cloud).
        
        Args:
            dry_run: Si es True, solo simula la limpieza
            
        Returns:
            Dict con estadísticas combinadas
        """
        logger.info(f"Iniciando limpieza completa (dry_run={dry_run})")
        
        resultado_local = self.limpiar_archivos_locales(dry_run)
        resultado_cloud = self.limpiar_archivos_cloud(dry_run)
        
        return {
            "local": resultado_local,
            "cloud": resultado_cloud,
            "resumen": {
                "total_archivos_analizados": (
                    resultado_local["archivos_analizados"] + 
                    resultado_cloud["archivos_analizados"]
                ),
                "total_huerfanos": (
                    resultado_local["archivos_huerfanos"] + 
                    resultado_cloud["archivos_huerfanos"]
                ),
                "total_eliminados": (
                    resultado_local["archivos_eliminados"] + 
                    resultado_cloud["archivos_eliminados"]
                ),
                "dry_run": dry_run
            }
        }


def get_cleanup_service(
    video_repository: VideoRepositoryProtocol,
    upload_folder: str = "./uploads",
    storage_adapter: Optional[StorageProtocol] = None
) -> CleanupService:
    """
    Factory function para obtener una instancia del servicio de limpieza.
    
    Args:
        video_repository: Repositorio de videos
        upload_folder: Carpeta de uploads
        storage_adapter: Adaptador de almacenamiento en la nube
        
    Returns:
        CleanupService configurado
    """
    return CleanupService(
        video_repository=video_repository,
        upload_folder=upload_folder,
        storage_adapter=storage_adapter
    )
