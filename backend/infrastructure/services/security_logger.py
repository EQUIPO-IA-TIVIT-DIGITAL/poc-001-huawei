"""
Logger Especializado para Análisis de Video de Seguridad
Proporciona trazabilidad completa del pipeline de procesamiento
"""
import json
import logging
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from functools import wraps
import time
import traceback
from logging.handlers import RotatingFileHandler


class _SecurityJsonFormatter(logging.Formatter):
    """JSON formatter para producción que incluye video_id y phase."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "video_id": getattr(record, "video_id", "-"),
            "phase": getattr(record, "phase", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class SecurityAnalysisLogger:
    """
    Logger dedicado para el análisis de videos de seguridad.
    Emite a stdout por defecto; archivo local solo si SECURITY_LOG_TO_FILE=true.
    """
    
    _instance: Optional['SecurityAnalysisLogger'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self.log_dir = os.getenv('SECURITY_LOG_DIR', './logs/security')
        self.log_level = os.getenv('SECURITY_LOG_LEVEL', 'DEBUG')
        self.max_bytes = int(os.getenv('SECURITY_LOG_MAX_BYTES', str(20 * 1024 * 1024)))
        self.backup_count = int(os.getenv('SECURITY_LOG_BACKUP_COUNT', '10'))
        self.force_flush = os.getenv('SECURITY_LOG_FORCE_FLUSH', 'false').lower() == 'true'
        self.log_to_file = os.getenv('SECURITY_LOG_TO_FILE', 'false').lower() == 'true'
        
        # Logger principal
        self.logger = logging.getLogger('security_analysis')
        self.logger.setLevel(getattr(logging, self.log_level.upper(), logging.DEBUG))
        self.logger.handlers = []  # Limpiar handlers previos
        
        # Formato detallado para archivo
        detailed_format = (
            '%(asctime)s | %(levelname)-8s | '
            '[%(video_id)s] | %(phase)s | %(message)s'
        )
        date_format = '%Y-%m-%d %H:%M:%S'
        
        if self.log_to_file:
            os.makedirs(self.log_dir, exist_ok=True)
            main_log_file = os.path.join(self.log_dir, 'security_analysis.log')
            file_handler = RotatingFileHandler(
                main_log_file,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
                encoding='utf-8',
            )
            file_handler.setFormatter(logging.Formatter(detailed_format, date_format))
            file_handler.setLevel(getattr(logging, self.log_level.upper(), logging.DEBUG))
            self.logger.addHandler(file_handler)
        
        # Handler de consola - respeta SECURITY_LOG_LEVEL
        console_handler = logging.StreamHandler(sys.stdout)
        _env = os.getenv('FLASK_ENV', 'development')
        if _env == 'production':
            console_handler.setFormatter(_SecurityJsonFormatter())
        else:
            console_format = '%(asctime)s | %(levelname)-8s | [%(video_id)s] %(message)s'
            console_handler.setFormatter(logging.Formatter(console_format, date_format))
        console_handler.setLevel(getattr(logging, self.log_level.upper(), logging.DEBUG))
        self.logger.addHandler(console_handler)
        
        if self.log_to_file:
            error_log_file = os.path.join(self.log_dir, 'security_errors.log')
            error_handler = RotatingFileHandler(
                error_log_file,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
                encoding='utf-8',
            )
            error_handler.setFormatter(logging.Formatter(detailed_format, date_format))
            error_handler.setLevel(logging.ERROR)
            self.logger.addHandler(error_handler)
        
        # Forzar flush inmediato
        if self.force_flush:
            for handler in self.logger.handlers:
                if hasattr(handler, 'stream'):
                    handler.stream.flush()
        
        # Contexto actual
        self._current_video_id = 'SYSTEM'
        self._current_phase = 'INIT'
        self._phase_start_times: Dict[str, float] = {}
        
    def set_context(self, video_id: str, phase: str = None):
        """Establece el contexto actual para los logs"""
        self._current_video_id = video_id
        if phase:
            self._current_phase = phase
    
    def _get_extra(self) -> Dict[str, str]:
        """Obtiene información extra para el log"""
        return {
            'video_id': self._current_video_id,
            'phase': self._current_phase
        }
    
    def start_phase(self, phase: str, description: str = ""):
        """Marca el inicio de una fase del pipeline"""
        self._current_phase = phase
        self._phase_start_times[phase] = time.time()
        
        separator = "=" * 60
        self.logger.info(separator, extra=self._get_extra())
        self.logger.info(f"🚀 INICIANDO: {phase}", extra=self._get_extra())
        if description:
            self.logger.info(f"   {description}", extra=self._get_extra())
        self.logger.info(separator, extra=self._get_extra())
        self._flush()
    
    def end_phase(self, phase: str, success: bool = True, details: str = ""):
        """Marca el fin de una fase del pipeline"""
        elapsed = 0
        if phase in self._phase_start_times:
            elapsed = time.time() - self._phase_start_times[phase]
            del self._phase_start_times[phase]
        
        status = "✅ COMPLETADO" if success else "❌ FALLIDO"
        self.logger.info(f"{status}: {phase} ({elapsed:.2f}s)", extra=self._get_extra())
        if details:
            self.logger.info(f"   Detalles: {details}", extra=self._get_extra())
        self._flush()
    
    def _flush(self):
        """Forzar flush de todos los handlers"""
        if not self.force_flush:
            return
        for handler in self.logger.handlers:
            handler.flush()
        sys.stdout.flush()
        sys.stderr.flush()
    
    def debug(self, message: str):
        """Log de nivel DEBUG"""
        self.logger.debug(message, extra=self._get_extra())
        self._flush()
    
    def info(self, message: str):
        """Log de nivel INFO"""
        self.logger.info(message, extra=self._get_extra())
        self._flush()
    
    def warning(self, message: str):
        """Log de nivel WARNING"""
        self.logger.warning(message, extra=self._get_extra())
        self._flush()
    
    def error(self, message: str, exc_info: bool = False):
        """Log de nivel ERROR"""
        self.logger.error(message, extra=self._get_extra(), exc_info=exc_info)
        self._flush()
    
    def critical(self, message: str, exc_info: bool = True):
        """Log de nivel CRITICAL"""
        self.logger.critical(message, extra=self._get_extra(), exc_info=exc_info)
        self._flush()
    
    def log_exception(self, message: str):
        """Log de excepción con traceback completo"""
        self.logger.error(message, extra=self._get_extra())
        self.logger.error(f"Traceback:\n{traceback.format_exc()}", extra=self._get_extra())
    
    def log_video_info(self, video_data: Dict[str, Any]):
        """Log de información del video"""
        self.info("📹 INFORMACIÓN DEL VIDEO:")
        self.info(f"   ID: {video_data.get('id', 'N/A')}")
        self.info(f"   Cámara: {video_data.get('nombre_camara', 'N/A')}")
        self.info(f"   Ubicación: {video_data.get('ubicacion', 'N/A')}")
        self.info(f"   Duración: {video_data.get('duracion_segundos', 0):.1f}s")
        storage_path = video_data.get('storage_path', 'N/A')
        storage_filename = storage_path.split('/')[-1] if storage_path and storage_path != 'N/A' else storage_path
        self.info(f"   Storage file: {storage_filename}")
    
    def log_motion_detection(self, num_segments: int, segments: list):
        """Log de resultados de detección de movimiento"""
        self.info(f"🎯 MOVIMIENTO DETECTADO: {num_segments} segmentos")
        for i, seg in enumerate(segments[:10]):  # Mostrar max 10
            start = seg.get('timestamp_inicio', 0)
            end = seg.get('timestamp_fin', 0)
            duration = seg.get('duracion', 0)
            self.debug(f"   Segmento {i+1}: {start:.1f}s - {end:.1f}s (duración: {duration:.1f}s)")
        if num_segments > 10:
            self.debug(f"   ... y {num_segments - 10} segmentos más")
    
    def log_classification(self, clip_index: int, clasificacion: str, confianza: float, descripcion: str):
        """Log de clasificación de un clip"""
        icon = {
            'NORMAL': '🟢',
            'SOSPECHOSO': '🟡',
            'IMPORTANTE': '🔴'
        }.get(clasificacion.upper(), '⚪')
        
        self.info(f"{icon} Clip {clip_index}: {clasificacion} (confianza: {confianza:.2f})")
        if descripcion:
            self.debug(f"   Descripción: {descripcion[:100]}...")
    
    def log_statistics(self, stats: Dict[str, Any]):
        """Log de estadísticas finales"""
        self.info("📊 ESTADÍSTICAS FINALES:")
        self.info(f"   Eventos totales: {stats.get('eventos_totales', 0)}")
        self.info(f"   🟢 Normales: {stats.get('eventos_normales', 0)}")
        self.info(f"   🟡 Sospechosos: {stats.get('eventos_sospechosos', 0)}")
        self.info(f"   🔴 Importantes: {stats.get('eventos_importantes', 0)}")
    
    def log_progress(self, current: int, total: int, description: str = ""):
        """Log de progreso"""
        percentage = (current / total * 100) if total > 0 else 0
        bar_length = 20
        filled = int(bar_length * current / total) if total > 0 else 0
        bar = '█' * filled + '░' * (bar_length - filled)
        
        self.info(f"   [{bar}] {percentage:.0f}% ({current}/{total}) {description}")
    
    def get_log_file_path(self) -> str:
        """Retorna la ruta del archivo de log principal"""
        return os.path.join(self.log_dir, 'security_analysis.log')
    
    def get_session_log_path(self, video_id: str) -> str:
        """Retorna la ruta del archivo de log para un video específico"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return os.path.join(self.log_dir, f'session_{video_id}_{timestamp}.log')


def get_security_logger() -> SecurityAnalysisLogger:
    """Obtiene la instancia singleton del logger de seguridad"""
    return SecurityAnalysisLogger()


def log_phase(phase_name: str):
    """
    Decorador para loggear automáticamente fases del pipeline
    
    Uso:
        @log_phase("MOTION_DETECTION")
        def detect_motion(self, video):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_security_logger()
            logger.start_phase(phase_name, f"Ejecutando {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                logger.end_phase(phase_name, success=True)
                return result
            except Exception as e:
                logger.end_phase(phase_name, success=False, details=str(e))
                logger.log_exception(f"Error en {phase_name}: {e}")
                raise
        
        return wrapper
    return decorator


# ============================================
# Comandos CLI para ver logs
# ============================================

def tail_security_log(lines: int = 50):
    """Muestra las últimas líneas del log de seguridad"""
    logger = get_security_logger()
    log_path = logger.get_log_file_path()
    
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            return ''.join(all_lines[-lines:])
    return "Log file not found"


def get_video_analysis_status(video_id: str) -> Dict[str, Any]:
    """Obtiene el estado del análisis de un video desde los logs"""
    logger = get_security_logger()
    log_path = logger.get_log_file_path()
    
    status = {
        'video_id': video_id,
        'found': False,
        'phases_completed': [],
        'current_phase': None,
        'errors': [],
        'last_activity': None
    }
    
    if not os.path.exists(log_path):
        return status
    
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            if video_id in line:
                status['found'] = True
                status['last_activity'] = line.split('|')[0].strip()
                
                if 'INICIANDO:' in line:
                    phase = line.split('INICIANDO:')[1].strip()
                    status['current_phase'] = phase
                
                if 'COMPLETADO:' in line:
                    phase = line.split('COMPLETADO:')[1].split('(')[0].strip()
                    if phase not in status['phases_completed']:
                        status['phases_completed'].append(phase)
                
                if 'ERROR' in line or 'FALLIDO' in line:
                    status['errors'].append(line.strip())
    
    return status
