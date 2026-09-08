"""
Servicio de Thumbnails y Vista Previa - AccessFan
Genera thumbnails y previews de videos
"""
import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime


class ThumbnailService:
    """
    Servicio singleton para generar thumbnails de videos
    Usa FFmpeg para extraer frames
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # Directorio de thumbnails
        self.thumbnails_dir = os.getenv('THUMBNAILS_DIR', '/app/thumbnails')
        self._ensure_directory_exists()
        
        # Verificar FFmpeg
        self.ffmpeg_available = self._check_ffmpeg()
    
    def _ensure_directory_exists(self):
        """Crea el directorio de thumbnails si no existe"""
        Path(self.thumbnails_dir).mkdir(parents=True, exist_ok=True)
    
    def _check_ffmpeg(self) -> bool:
        """Verifica si FFmpeg está disponible"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("⚠️  FFmpeg no disponible. Thumbnails deshabilitados.")
            return False
    
    def generate_thumbnail(
        self,
        video_path: str,
        video_id: str,
        timestamp: float = 1.0,
        size: Tuple[int, int] = (320, 180)
    ) -> Optional[str]:
        """
        Genera un thumbnail de un video
        
        Args:
            video_path: Ruta al archivo de video
            video_id: ID único del video
            timestamp: Segundo del video para capturar (default: 1s)
            size: Tamaño del thumbnail (ancho, alto)
            
        Returns:
            str: Ruta al thumbnail generado o None si falla
        """
        if not self.ffmpeg_available:
            print(f"⚠️  FFmpeg no disponible, no se puede generar thumbnail")
            return None
        
        if not os.path.exists(video_path):
            print(f"⚠️  Video no encontrado: {video_path}")
            return None
        
        try:
            # Nombre del thumbnail
            thumbnail_filename = f"{video_id}_thumb.jpg"
            thumbnail_path = os.path.join(self.thumbnails_dir, thumbnail_filename)
            
            # Comando FFmpeg para extraer frame
            cmd = [
                'ffmpeg',
                '-y',  # Sobreescribir si existe
                '-ss', str(timestamp),  # Timestamp
                '-i', video_path,  # Video de entrada
                '-vframes', '1',  # Solo 1 frame
                '-vf', f'scale={size[0]}:{size[1]}',  # Redimensionar
                '-q:v', '2',  # Calidad (2 = alta)
                thumbnail_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and os.path.exists(thumbnail_path):
                print(f"✅ Thumbnail generado: {thumbnail_path}")
                return thumbnail_path
            else:
                print(f"❌ Error generando thumbnail: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print(f"⏱️  Timeout generando thumbnail para {video_id}")
            return None
        except Exception as e:
            print(f"❌ Error generando thumbnail: {e}")
            return None
    
    def generate_multiple_thumbnails(
        self,
        video_path: str,
        video_id: str,
        count: int = 4,
        size: Tuple[int, int] = (160, 90)
    ) -> List[str]:
        """
        Genera múltiples thumbnails a diferentes tiempos del video
        
        Args:
            video_path: Ruta al archivo de video
            video_id: ID único del video
            count: Número de thumbnails a generar
            size: Tamaño de cada thumbnail
            
        Returns:
            list: Lista de rutas a los thumbnails generados
        """
        if not self.ffmpeg_available:
            return []
        
        # Obtener duración del video
        duration = self._get_video_duration(video_path)
        if duration <= 0:
            return []
        
        thumbnails = []
        interval = duration / (count + 1)
        
        for i in range(count):
            timestamp = interval * (i + 1)
            thumbnail_filename = f"{video_id}_thumb_{i+1}.jpg"
            thumbnail_path = os.path.join(self.thumbnails_dir, thumbnail_filename)
            
            try:
                cmd = [
                    'ffmpeg',
                    '-y',
                    '-ss', str(timestamp),
                    '-i', video_path,
                    '-vframes', '1',
                    '-vf', f'scale={size[0]}:{size[1]}',
                    '-q:v', '3',
                    thumbnail_path
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                
                if result.returncode == 0 and os.path.exists(thumbnail_path):
                    thumbnails.append(thumbnail_path)
                    
            except Exception as e:
                print(f"⚠️  Error generando thumbnail {i+1}: {e}")
        
        return thumbnails
    
    def generate_animated_preview(
        self,
        video_path: str,
        video_id: str,
        duration: int = 5,
        fps: int = 8,
        size: Tuple[int, int] = (320, 180)
    ) -> Optional[str]:
        """
        Genera un GIF animado de vista previa
        
        Args:
            video_path: Ruta al archivo de video
            video_id: ID único del video
            duration: Duración del GIF en segundos
            fps: Frames por segundo
            size: Tamaño del GIF
            
        Returns:
            str: Ruta al GIF generado o None
        """
        if not self.ffmpeg_available:
            return None
        
        try:
            gif_filename = f"{video_id}_preview.gif"
            gif_path = os.path.join(self.thumbnails_dir, gif_filename)
            
            # Obtener duración real y calcular inicio
            video_duration = self._get_video_duration(video_path)
            start_time = max(0, (video_duration - duration) / 2)  # Centrar el GIF
            
            cmd = [
                'ffmpeg',
                '-y',
                '-ss', str(start_time),
                '-t', str(duration),
                '-i', video_path,
                '-vf', f'fps={fps},scale={size[0]}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse',
                '-loop', '0',
                gif_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0 and os.path.exists(gif_path):
                print(f"✅ Preview GIF generado: {gif_path}")
                return gif_path
            else:
                print(f"❌ Error generando preview GIF: {result.stderr}")
                return None
                
        except Exception as e:
            print(f"❌ Error generando preview: {e}")
            return None
    
    def _get_video_duration(self, video_path: str) -> float:
        """Obtiene la duración del video en segundos"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return float(result.stdout.strip())
            return 0
            
        except Exception:
            return 0
    
    def get_thumbnail_url(self, video_id: str) -> Optional[str]:
        """
        Obtiene la URL del thumbnail de un video
        
        Args:
            video_id: ID del video
            
        Returns:
            str: URL relativa del thumbnail o None
        """
        thumbnail_filename = f"{video_id}_thumb.jpg"
        thumbnail_path = os.path.join(self.thumbnails_dir, thumbnail_filename)
        
        if os.path.exists(thumbnail_path):
            return f"/thumbnails/{thumbnail_filename}"
        return None
    
    def get_preview_url(self, video_id: str) -> Optional[str]:
        """
        Obtiene la URL del GIF de preview
        
        Args:
            video_id: ID del video
            
        Returns:
            str: URL relativa del preview o None
        """
        gif_filename = f"{video_id}_preview.gif"
        gif_path = os.path.join(self.thumbnails_dir, gif_filename)
        
        if os.path.exists(gif_path):
            return f"/thumbnails/{gif_filename}"
        return None
    
    def delete_thumbnails(self, video_id: str) -> bool:
        """
        Elimina todos los thumbnails de un video
        
        Args:
            video_id: ID del video
            
        Returns:
            bool: True si se eliminaron correctamente
        """
        try:
            deleted = False
            for ext in ['_thumb.jpg', '_preview.gif'] + [f'_thumb_{i}.jpg' for i in range(1, 10)]:
                path = os.path.join(self.thumbnails_dir, f"{video_id}{ext}")
                if os.path.exists(path):
                    os.remove(path)
                    deleted = True
            return deleted
        except Exception as e:
            print(f"❌ Error eliminando thumbnails: {e}")
            return False
    
    def get_video_metadata(self, video_path: str) -> dict:
        """
        Obtiene metadatos del video usando FFprobe
        
        Args:
            video_path: Ruta al video
            
        Returns:
            dict: Metadatos del video
        """
        metadata = {
            'duration': 0,
            'width': 0,
            'height': 0,
            'codec': '',
            'fps': 0,
            'bitrate': 0,
            'size_bytes': 0
        }
        
        if not os.path.exists(video_path):
            return metadata
        
        # Obtener tamaño del archivo
        metadata['size_bytes'] = os.path.getsize(video_path)
        
        try:
            # Obtener información detallada con FFprobe
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                video_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                
                # Formato
                if 'format' in data:
                    metadata['duration'] = float(data['format'].get('duration', 0))
                    metadata['bitrate'] = int(data['format'].get('bit_rate', 0))
                
                # Streams de video
                for stream in data.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        metadata['width'] = stream.get('width', 0)
                        metadata['height'] = stream.get('height', 0)
                        metadata['codec'] = stream.get('codec_name', '')
                        
                        # FPS
                        fps_str = stream.get('r_frame_rate', '0/1')
                        if '/' in fps_str:
                            num, den = fps_str.split('/')
                            if int(den) > 0:
                                metadata['fps'] = round(int(num) / int(den), 2)
                        break
                        
        except Exception as e:
            print(f"⚠️  Error obteniendo metadatos: {e}")
        
        return metadata


# Singleton instance
_thumbnail_service: Optional[ThumbnailService] = None


def get_thumbnail_service() -> ThumbnailService:
    """Obtiene la instancia singleton del servicio de thumbnails"""
    global _thumbnail_service
    if _thumbnail_service is None:
        _thumbnail_service = ThumbnailService()
    return _thumbnail_service
