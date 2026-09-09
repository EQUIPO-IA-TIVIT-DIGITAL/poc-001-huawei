"""
Gestión de Archivos Temporales con Cleanup Automático
Context managers para garantizar limpieza de recursos
"""

import os
import shutil
import tempfile
import logging
from contextlib import contextmanager
from typing import Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


@contextmanager
def temporary_video_clip(video_path: str, start_time: float, end_time: float):
    """
    Context manager para clips de video temporales
    
    Garantiza la limpieza del clip incluso si hay excepciones
    
    Args:
        video_path: Ruta del video original
        start_time: Tiempo de inicio en segundos
        end_time: Tiempo de fin en segundos
    
    Yields:
        str: Ruta del clip temporal
    
    Example:
        with temporary_video_clip(video_path, 10.0, 20.0) as clip_path:
            frames = extract_frames(clip_path)
            analyze(frames)
        # clip_path se elimina automáticamente aquí
    """
    temp_file = None
    try:
        # Crear archivo temporal
        fd, temp_file = tempfile.mkstemp(suffix='.mp4', prefix='clip_')
        os.close(fd)
        
        # Extraer clip con ffmpeg
        import subprocess
        duration = end_time - start_time
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-ss', str(start_time),
            '-t', str(duration),
            '-c', 'copy',
            '-y',
            temp_file
        ]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Error extrayendo clip: {result.stderr.decode()}")
        
        logger.debug(f"📹 Clip temporal creado: {temp_file} ({duration:.1f}s)")
        yield temp_file
        
    finally:
        # Cleanup garantizado
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                logger.debug(f"🧹 Clip temporal eliminado: {temp_file}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar clip temporal: {e}")


@contextmanager
def temporary_directory(prefix: str = 'temp_', cleanup: bool = True):
    """
    Context manager para directorios temporales
    
    Args:
        prefix: Prefijo del nombre del directorio
        cleanup: Si True, elimina el directorio al salir
    
    Yields:
        str: Ruta del directorio temporal
    
    Example:
        with temporary_directory(prefix='frames_') as temp_dir:
            extract_frames_to(temp_dir)
            process_frames(temp_dir)
        # temp_dir se elimina automáticamente aquí
    """
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=prefix)
        logger.debug(f"📁 Directorio temporal creado: {temp_dir}")
        yield temp_dir
        
    finally:
        if cleanup and temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"🧹 Directorio temporal eliminado: {temp_dir}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar directorio temporal: {e}")


@contextmanager
def temporary_frames(video_clip_path: str, num_frames: int = 5):
    """
    Context manager para frames temporales extraídos de un video
    
    Args:
        video_clip_path: Ruta del clip de video
        num_frames: Número de frames a extraer
    
    Yields:
        List[str]: Lista de rutas de frames extraídos
    
    Example:
        with temporary_frames(clip_path, num_frames=5) as frames:
            for frame in frames:
                analyze(frame)
        # frames se eliminan automáticamente aquí
    """
    frame_paths = []
    temp_dir = None
    
    try:
        # Crear directorio temporal para frames
        temp_dir = tempfile.mkdtemp(prefix='frames_')
        
        # Extraer frames
        import cv2
        cap = cv2.VideoCapture(video_clip_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if total_frames < num_frames:
            num_frames = max(1, total_frames)
        
        frame_indices = [int(i * total_frames / num_frames) for i in range(num_frames)]
        
        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            
            if ret:
                frame_path = os.path.join(temp_dir, f"frame_{idx:04d}.jpg")
                cv2.imwrite(frame_path, frame)
                frame_paths.append(frame_path)
        
        cap.release()
        
        logger.debug(f"🎞️  {len(frame_paths)} frames extraídos a {temp_dir}")
        yield frame_paths
        
    finally:
        # Cleanup garantizado
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"🧹 Frames temporales eliminados: {temp_dir}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar frames: {e}")


@contextmanager
def temporary_download(storage_uri: str, suffix: str = '.mp4'):
    """
    Context manager para descargar archivo de almacenamiento temporalmente
    
    Args:
        storage_uri: URI del archivo (s3://bucket/path, file://path, o bucket/key)
        suffix: Extensión del archivo
    
    Yields:
        str: Ruta local del archivo descargado
    """
    temp_file = None
    try:
        fd, temp_file = tempfile.mkstemp(suffix=suffix, prefix='download_')
        os.close(fd)
        
        from infrastructure.dependencies import get_storage_adapter
        storage = get_storage_adapter()
        
        if not storage or not storage.is_available():
            raise RuntimeError("Storage no disponible")
        
        blob_name = storage_uri
        if "://" in storage_uri:
            parts = storage_uri.split("://", 1)[1]
            if "/" in parts:
                blob_name = parts.split("/", 1)[1]
        
        logger.info(f"Descargando {storage_uri} a {temp_file}...")
        
        if hasattr(storage, '_get_client'):
            storage._get_client().download_file(storage.bucket, blob_name, temp_file)
        elif hasattr(storage, 'descargar_archivo'):
            storage.descargar_archivo(blob_name, temp_file)
        else:
            import shutil
            from pathlib import Path
            shutil.copy2(str(Path(storage.base_dir) / blob_name), temp_file)
        
        if not os.path.exists(temp_file):
            raise RuntimeError(f"No se pudo descargar {storage_uri}")
        
        file_size = os.path.getsize(temp_file)
        logger.info(f"Descargado: {file_size / 1024 / 1024:.1f} MB")
        
        yield temp_file
        
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                logger.debug(f"Descarga temporal eliminada: {temp_file}")
            except Exception as e:
                logger.warning(f"No se pudo eliminar descarga temporal: {e}")


class TempFileTracker:
    """
    Rastrea archivos temporales para cleanup al finalizar procesamiento
    
    Útil cuando no se puede usar context managers
    """
    
    def __init__(self):
        self.tracked_files: List[str] = []
        self.tracked_dirs: List[str] = []
    
    def track_file(self, file_path: str):
        """Registra un archivo para eliminación posterior"""
        if file_path and file_path not in self.tracked_files:
            self.tracked_files.append(file_path)
            logger.debug(f"📝 Archivo rastreado: {file_path}")
    
    def track_directory(self, dir_path: str):
        """Registra un directorio para eliminación posterior"""
        if dir_path and dir_path not in self.tracked_dirs:
            self.tracked_dirs.append(dir_path)
            logger.debug(f"📝 Directorio rastreado: {dir_path}")
    
    def cleanup(self):
        """Elimina todos los archivos y directorios rastreados"""
        total_removed = 0
        
        # Eliminar archivos
        for file_path in self.tracked_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    total_removed += 1
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar {file_path}: {e}")
        
        # Eliminar directorios
        for dir_path in self.tracked_dirs:
            try:
                if os.path.exists(dir_path):
                    shutil.rmtree(dir_path)
                    total_removed += 1
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar {dir_path}: {e}")
        
        logger.info(f"🧹 Cleanup completado: {total_removed} items eliminados")
        
        # Limpiar listas
        self.tracked_files.clear()
        self.tracked_dirs.clear()
    
    def __enter__(self):
        """Permite usar como context manager"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup automático al salir del contexto"""
        self.cleanup()
        return False
