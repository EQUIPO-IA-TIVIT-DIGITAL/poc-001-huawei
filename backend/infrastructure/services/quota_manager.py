"""
Gestión de Cuotas de APIs Externas
Controla límites de rate y concurrencia para Gemini y Video Intelligence

Implementación distribuida con Redis:
  - Gemini RPM: sliding window ZSET (compartida entre instancias)
  - Video Intelligence concurrencia: contador INCR/DECR (compartido entre instancias)
  - Fallback in-process para cuando Redis no está disponible
"""

import logging
import time
import uuid
from threading import Semaphore, Lock
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Claves Redis compartidas entre instancias
_REDIS_KEY_GEMINI_RPM = "quota:gemini_rpm"
_REDIS_KEY_VIDEO_CONCURRENT = "quota:video_intel_concurrent"
_REDIS_VIDEO_CONC_MAX = 8
_REDIS_VIDEO_CONC_TTL = 300  # 5 min safety TTL


class RateLimiter:
    """
    Rate limiter con ventana deslizante (in-process fallback)
    
    Permite max_calls llamadas por period segundos
    """
    
    def __init__(self, max_calls: int, period: int):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()
        self.lock = Lock()
    
    def acquire(self, blocking: bool = True, timeout: float = None) -> bool:
        start_time = time.time()
        
        while True:
            with self.lock:
                now = time.time()
                while self.calls and self.calls[0] < now - self.period:
                    self.calls.popleft()
                
                if len(self.calls) < self.max_calls:
                    self.calls.append(now)
                    return True
                
                if not blocking:
                    return False
                
                if timeout is not None:
                    if time.time() - start_time >= timeout:
                        return False
            
            time.sleep(0.1)
    
    def get_wait_time(self) -> float:
        with self.lock:
            now = time.time()
            while self.calls and self.calls[0] < now - self.period:
                self.calls.popleft()
            
            if len(self.calls) < self.max_calls:
                return 0.0
            
            return max(0.0, self.calls[0] + self.period - now)


class APIQuotaManager:
    """
    Gestiona cuotas de APIs externas (Gemini, Video Intelligence).
    
    Usa Redis para sincronización distribuida entre instancias Gunicorn.
    Fallback automático a primitivas in-process si Redis no está disponible.
    
    Límites de Gemini Flash 1.5:
    - 1000 solicitudes por minuto (RPM) → conservador: 800
    
    Límites de Video Intelligence:
    - 2000 solicitudes por minuto
    - 10 solicitudes concurrentes recomendadas → conservador: 8
    """
    
    def __init__(self):
        # Límites configurados
        self.gemini_rpm_limit = 800
        self.video_intel_rpm_limit = 1600

        # Fallbacks in-process
        self.gemini_rpm = RateLimiter(max_calls=self.gemini_rpm_limit, period=60)
        self.video_intel_rpm = RateLimiter(max_calls=self.video_intel_rpm_limit, period=60)
        self.video_intel_concurrent = Semaphore(8)
        
        # Estadísticas
        self.stats = {
            'gemini_calls': 0,
            'gemini_rejections': 0,
            'video_intel_calls': 0,
            'video_intel_rejections': 0,
            'last_reset': datetime.utcnow()
        }
        self.stats_lock = Lock()

    def _get_redis(self):
        """Obtiene conexión Redis compartida. Retorna None si no disponible."""
        try:
            from infrastructure.services.job_queue import get_redis_connection
            return get_redis_connection()
        except Exception:
            return None

    def acquire_gemini(self, blocking: bool = True, timeout: float = 30.0) -> bool:
        """
        Adquiere cuota para llamada a Gemini usando sliding window ZSET en Redis.
        Fallback a RateLimiter in-process si Redis no está disponible.
        
        Raises:
            QuotaExceededException: Si no se pudo adquirir en el timeout
        """
        redis = self._get_redis()
        if redis:
            try:
                start = time.time()
                while True:
                    now = time.time()
                    pipe = redis.pipeline()
                    pipe.zremrangebyscore(_REDIS_KEY_GEMINI_RPM, 0, now - 60)
                    pipe.zcard(_REDIS_KEY_GEMINI_RPM)
                    _, count = pipe.execute()

                    if count < self.gemini_rpm_limit:
                        member = f"{now}:{uuid.uuid4().hex[:8]}"
                        redis.zadd(_REDIS_KEY_GEMINI_RPM, {member: now})
                        redis.expire(_REDIS_KEY_GEMINI_RPM, 65)
                        with self.stats_lock:
                            self.stats['gemini_calls'] += 1
                        logger.debug(f"✅ Cuota Gemini (Redis) adquirida (slot {count + 1}/{self.gemini_rpm_limit})")
                        return True

                    if not blocking or (time.time() - start) >= timeout:
                        break
                    time.sleep(0.1)

                # Expirado o no-blocking: registrar y levantar
                with self.stats_lock:
                    self.stats['gemini_rejections'] += 1
                raise QuotaExceededException(
                    f"Límite de Gemini alcanzado (Redis). Reintenta en ~{60 - (time.time() % 60):.0f}s"
                )
            except QuotaExceededException:
                raise
            except Exception as redis_err:
                logger.warning(f"⚠️ Redis quota Gemini no disponible, usando local: {redis_err}")

        # Fallback in-process
        acquired = self.gemini_rpm.acquire(blocking=blocking, timeout=timeout)
        with self.stats_lock:
            if acquired:
                self.stats['gemini_calls'] += 1
                logger.debug(f"✅ Cuota Gemini (local) adquirida (total: {self.stats['gemini_calls']})")
            else:
                self.stats['gemini_rejections'] += 1
                logger.warning(f"⚠️ Cuota Gemini (local) agotada. Espera: {self.gemini_rpm.get_wait_time():.1f}s")

        if not acquired:
            raise QuotaExceededException(
                f"Límite de Gemini alcanzado. Espera: {self.gemini_rpm.get_wait_time():.1f}s"
            )
        return True

    def acquire_video_intelligence(self, blocking: bool = True, timeout: float = 30.0) -> bool:
        """
        Adquiere cuota para llamada a Video Intelligence.
        Concurrencia controlada con contador INCR/DECR en Redis (distribuido).
        
        Raises:
            QuotaExceededException: Si no se pudo adquirir
        """
        # RPM check (in-process, sin penalidad en scaling)
        rpm_acquired = self.video_intel_rpm.acquire(blocking=blocking, timeout=timeout)
        if not rpm_acquired:
            with self.stats_lock:
                self.stats['video_intel_rejections'] += 1
            raise QuotaExceededException(
                f"Límite de Video Intelligence RPM alcanzado. "
                f"Espera: {self.video_intel_rpm.get_wait_time():.1f}s"
            )

        # Concurrencia distribuida con Redis
        redis = self._get_redis()
        if redis:
            try:
                count = redis.incr(_REDIS_KEY_VIDEO_CONCURRENT)
                redis.expire(_REDIS_KEY_VIDEO_CONCURRENT, _REDIS_VIDEO_CONC_TTL)
                if count <= _REDIS_VIDEO_CONC_MAX:
                    with self.stats_lock:
                        self.stats['video_intel_calls'] += 1
                    logger.debug(f"✅ Cuota Video Intelligence (Redis) adquirida ({count}/{_REDIS_VIDEO_CONC_MAX})")
                    return True
                # Slot lleno: revertir incremento
                redis.decr(_REDIS_KEY_VIDEO_CONCURRENT)
                with self.stats_lock:
                    self.stats['video_intel_rejections'] += 1
                raise QuotaExceededException(
                    f"Límite de concurrencia de Video Intelligence alcanzado ({_REDIS_VIDEO_CONC_MAX} activos)"
                )
            except QuotaExceededException:
                raise
            except Exception as redis_err:
                logger.warning(f"⚠️ Redis concurrencia Video Intelligence no disponible, usando local: {redis_err}")

        # Fallback in-process Semaphore
        concurrent_acquired = self.video_intel_concurrent.acquire(blocking=False)
        if not concurrent_acquired:
            with self.stats_lock:
                self.stats['video_intel_rejections'] += 1
            raise QuotaExceededException(
                "Límite de concurrencia de Video Intelligence alcanzado (local)"
            )
        with self.stats_lock:
            self.stats['video_intel_calls'] += 1
        logger.debug("✅ Cuota Video Intelligence (local) adquirida")
        return True

    def release_video_intelligence(self):
        """Libera slot de concurrencia de Video Intelligence (Redis o local)."""
        redis = self._get_redis()
        if redis:
            try:
                redis.decr(_REDIS_KEY_VIDEO_CONCURRENT)
                logger.debug("🔓 Slot de Video Intelligence (Redis) liberado")
                return
            except Exception as redis_err:
                logger.warning(f"⚠️ Redis release Video Intelligence no disponible: {redis_err}")
        self.video_intel_concurrent.release()
        logger.debug("🔓 Slot de Video Intelligence (local) liberado")

    def get_statistics(self) -> dict:
        """Retorna estadísticas de uso incluyendo estado Redis si disponible."""
        with self.stats_lock:
            uptime = (datetime.utcnow() - self.stats['last_reset']).total_seconds()
            base = {
                **self.stats,
                'uptime_seconds': uptime,
                'gemini_rpm_limit': self.gemini_rpm_limit,
                'video_intel_rpm_limit': self.video_intel_rpm_limit,
                'gemini_wait_time': self.gemini_rpm.get_wait_time(),
                'video_intel_wait_time': self.video_intel_rpm.get_wait_time(),
                'gemini_rpm_current': len(self.gemini_rpm.calls),
                'video_intel_rpm_current': len(self.video_intel_rpm.calls),
            }

        redis = self._get_redis()
        if redis:
            try:
                now = time.time()
                pipe = redis.pipeline()
                pipe.zcount(_REDIS_KEY_GEMINI_RPM, now - 60, '+inf')
                pipe.get(_REDIS_KEY_VIDEO_CONCURRENT)
                gemini_redis, video_conc_redis = pipe.execute()
                base['gemini_rpm_current_redis'] = int(gemini_redis or 0)
                base['video_intel_concurrent_redis'] = int(video_conc_redis or 0)
                base['video_intel_concurrent_max'] = _REDIS_VIDEO_CONC_MAX
            except Exception:
                pass

        return base

    def reset_statistics(self):
        """Reinicia estadísticas."""
        with self.stats_lock:
            self.stats = {
                'gemini_calls': 0,
                'gemini_rejections': 0,
                'video_intel_calls': 0,
                'video_intel_rejections': 0,
                'last_reset': datetime.utcnow()
            }
            logger.info("📊 Estadísticas de cuotas reiniciadas")


class QuotaExceededException(Exception):
    """Excepción cuando se excede la cuota de una API"""
    pass


# Instancia global singleton
_quota_manager = None

def get_quota_manager() -> APIQuotaManager:
    """Retorna instancia singleton del gestor de cuotas"""
    global _quota_manager
    if _quota_manager is None:
        _quota_manager = APIQuotaManager()
        logger.info("✅ APIQuotaManager inicializado (Redis distribuido con fallback in-process)")
    return _quota_manager

    """
    Rate limiter con ventana deslizante
    
    Permite max_calls llamadas por period segundos
    """
    
    def __init__(self, max_calls: int, period: int):
        """
        Args:
            max_calls: Número máximo de llamadas permitidas
            period: Periodo en segundos
        """
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()
        self.lock = Lock()
    
    def acquire(self, blocking: bool = True, timeout: float = None) -> bool:
        """
        Intenta adquirir permiso para hacer una llamada
        
        Args:
            blocking: Si True, espera hasta poder adquirir
            timeout: Tiempo máximo de espera (None = infinito)
        
        Returns:
            True si se adquirió el permiso, False si no
        """
        start_time = time.time()
        
        while True:
            with self.lock:
                now = time.time()
                
                # Limpiar llamadas antiguas (fuera de la ventana)
                while self.calls and self.calls[0] < now - self.period:
                    self.calls.popleft()
                
                # Si hay espacio, agregar la llamada
                if len(self.calls) < self.max_calls:
                    self.calls.append(now)
                    return True
                
                # Si no es blocking, retornar False
                if not blocking:
                    return False
                
                # Verificar timeout
                if timeout is not None:
                    elapsed = time.time() - start_time
                    if elapsed >= timeout:
                        return False
            
            # Esperar un poco antes de reintentar
            time.sleep(0.1)
    
    def get_wait_time(self) -> float:
        """
        Retorna el tiempo de espera estimado en segundos
        """
        with self.lock:
            now = time.time()
            
            # Limpiar llamadas antiguas
            while self.calls and self.calls[0] < now - self.period:
                self.calls.popleft()
            
            if len(self.calls) < self.max_calls:
                return 0.0
            
            # Tiempo hasta que expire la llamada más antigua
            oldest_call = self.calls[0]
            wait_time = (oldest_call + self.period) - now
            return max(0.0, wait_time)


class APIQuotaManager:
    """
    Gestiona cuotas de APIs externas (Gemini, Video Intelligence)
    
    Límites de Gemini Flash 1.5:
    - 1000 solicitudes por minuto (RPM)
    - 4 millones de tokens por minuto (TPM)
    
    Límites de Video Intelligence:
    - 2000 solicitudes por minuto
    - 10 solicitudes concurrentes recomendadas
    """
    
    def __init__(self):
        # Gemini Flash 1.5 limits (conservador: 80% del límite)
        self.gemini_rpm_limit = 800  # 80% de 1000 RPM
        self.gemini_rpm = RateLimiter(max_calls=self.gemini_rpm_limit, period=60)
        
        # Video Intelligence limits (conservador)
        self.video_intel_rpm_limit = 1600  # 80% de 2000 RPM
        self.video_intel_rpm = RateLimiter(max_calls=self.video_intel_rpm_limit, period=60)
        self.video_intel_concurrent = Semaphore(8)  # Max 8 concurrent
        
        # Estadísticas
        self.stats = {
            'gemini_calls': 0,
            'gemini_rejections': 0,
            'video_intel_calls': 0,
            'video_intel_rejections': 0,
            'last_reset': datetime.utcnow()
        }
        self.stats_lock = Lock()
    
    def acquire_gemini(self, blocking: bool = True, timeout: float = 30.0) -> bool:
        """
        Adquiere cuota para llamada a Gemini
        
        Args:
            blocking: Si True, espera hasta adquirir
            timeout: Tiempo máximo de espera
        
        Returns:
            True si se adquirió, False si no
        
        Raises:
            QuotaExceededException: Si no se pudo adquirir en el timeout
        """
        acquired = self.gemini_rpm.acquire(blocking=blocking, timeout=timeout)
        
        with self.stats_lock:
            if acquired:
                self.stats['gemini_calls'] += 1
                logger.debug(f"✅ Cuota Gemini adquirida (total: {self.stats['gemini_calls']})")
            else:
                self.stats['gemini_rejections'] += 1
                wait_time = self.gemini_rpm.get_wait_time()
                logger.warning(f"⚠️ Cuota Gemini agotada. Espera: {wait_time:.1f}s")
        
        if not acquired:
            raise QuotaExceededException(
                f"Límite de Gemini alcanzado. "
                f"Espera estimada: {self.gemini_rpm.get_wait_time():.1f}s"
            )
        
        return True
    
    def acquire_video_intelligence(self, blocking: bool = True, timeout: float = 30.0) -> bool:
        """
        Adquiere cuota para llamada a Video Intelligence
        
        Args:
            blocking: Si True, espera hasta adquirir
            timeout: Tiempo máximo de espera
        
        Returns:
            True si se adquirió, False si no
        
        Raises:
            QuotaExceededException: Si no se pudo adquirir
        """
        # Primero verificar RPM
        rpm_acquired = self.video_intel_rpm.acquire(blocking=blocking, timeout=timeout)
        if not rpm_acquired:
            with self.stats_lock:
                self.stats['video_intel_rejections'] += 1
            raise QuotaExceededException(
                f"Límite de Video Intelligence RPM alcanzado. "
                f"Espera: {self.video_intel_rpm.get_wait_time():.1f}s"
            )
        
        # Luego verificar concurrencia
        concurrent_acquired = self.video_intel_concurrent.acquire(blocking=False)
        if not concurrent_acquired:
            with self.stats_lock:
                self.stats['video_intel_rejections'] += 1
            raise QuotaExceededException(
                "Límite de concurrencia de Video Intelligence alcanzado"
            )
        
        with self.stats_lock:
            self.stats['video_intel_calls'] += 1
            logger.debug(f"✅ Cuota Video Intelligence adquirida (total: {self.stats['video_intel_calls']})")
        
        return True
    
    def release_video_intelligence(self):
        """Libera slot de concurrencia de Video Intelligence"""
        self.video_intel_concurrent.release()
        logger.debug("🔓 Slot de Video Intelligence liberado")
    
    def get_statistics(self) -> dict:
        """Retorna estadísticas de uso"""
        with self.stats_lock:
            uptime = (datetime.utcnow() - self.stats['last_reset']).total_seconds()
            return {
                **self.stats,
                'uptime_seconds': uptime,
                'gemini_rpm_current': len(self.gemini_rpm.calls),
                'gemini_rpm_limit': self.gemini_rpm_limit,
                'video_intel_rpm_current': len(self.video_intel_rpm.calls),
                'video_intel_rpm_limit': self.video_intel_rpm_limit,
                'gemini_wait_time': self.gemini_rpm.get_wait_time(),
                'video_intel_wait_time': self.video_intel_rpm.get_wait_time(),
            }
    
    def reset_statistics(self):
        """Reinicia estadísticas"""
        with self.stats_lock:
            self.stats = {
                'gemini_calls': 0,
                'gemini_rejections': 0,
                'video_intel_calls': 0,
                'video_intel_rejections': 0,
                'last_reset': datetime.utcnow()
            }
            logger.info("📊 Estadísticas de cuotas reiniciadas")


class QuotaExceededException(Exception):
    """Excepción cuando se excede la cuota de una API"""
    pass


# Instancia global singleton
_quota_manager = None

def get_quota_manager() -> APIQuotaManager:
    """Retorna instancia singleton del gestor de cuotas"""
    global _quota_manager
    if _quota_manager is None:
        _quota_manager = APIQuotaManager()
        logger.info("✅ APIQuotaManager inicializado")
    return _quota_manager
