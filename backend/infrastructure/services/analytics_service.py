"""
Servicio de Analytics y Reportes - AccessFan
Genera estadísticas y reportes de uso del sistema
OPTIMIZADO: Usa caché Redis para reducir carga en la base de datos
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

import logging
logger = logging.getLogger(__name__)

from domain.entities import EstadoVideo
from infrastructure.services.cache_queries import get_cache_queries


# TTLs para caché de analytics (en segundos)
TTL_VIDEO_SUMMARY = 300      # 5 minutos
TTL_USER_SUMMARY = 300       # 5 minutos
TTL_DAILY_STATS = 600        # 10 minutos
TTL_REJECTION_STATS = 600    # 10 minutos


@dataclass
class VideoStats:
    """Estadísticas de videos"""

    total: int = 0
    aprobados: int = 0
    rechazados: int = 0
    en_revision: int = 0
    pendientes: int = 0


@dataclass
class DailyStats:
    """Estadísticas diarias"""

    fecha: str = ""
    subidos: int = 0
    aprobados: int = 0
    rechazados: int = 0


@dataclass
class RejectionReason:
    """Razón de rechazo con conteo"""

    reason: str = ""
    count: int = 0
    percentage: float = 0.0


class AnalyticsService:
    """
    Servicio singleton para generar analytics y reportes
    OPTIMIZADO con caché Redis
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
        self._video_repo = None
        self._user_repo = None
        self._cache = None
    
    def _get_cache(self):
        """Lazy loading del servicio de caché"""
        if self._cache is None:
            self._cache = get_cache_queries()
        return self._cache

    def _get_video_repo(self):
        """Lazy loading del repositorio de videos"""
        if self._video_repo is None:
            from infrastructure.dependencies import get_video_repository

            self._video_repo = get_video_repository()
        return self._video_repo

    def _get_user_repo(self):
        """Lazy loading del repositorio de usuarios"""
        if self._user_repo is None:
            from infrastructure.dependencies import get_user_repository

            self._user_repo = get_user_repository()
        return self._user_repo

    # ===== Estadísticas Generales =====

    def get_video_summary(self) -> Dict[str, Any]:
        """
        Obtiene resumen general de videos
        OPTIMIZADO: Usa caché Redis (TTL: 5 minutos)

        Returns:
            dict: Estadísticas generales de videos
        """
        # Intentar obtener del caché primero
        cache = self._get_cache()
        cached = cache.get_cached_analytics('video', 'summary')
        if cached:
            return cached
        
        # Calcular estadísticas
        video_repo = self._get_video_repo()
        all_videos = video_repo.obtener_todos()

        stats = VideoStats(total=len(all_videos))

        for video in all_videos:
            if video.estado == EstadoVideo.APROBADO:
                stats.aprobados += 1
            elif video.estado == EstadoVideo.RECHAZADO:
                stats.rechazados += 1
            elif video.estado == EstadoVideo.COMPLETADO:
                # Verificar resultado IA en completados
                if video.metadatos_ia.get("resultado_ia") == "RECHAZADO":
                    stats.rechazados += 1
                else:
                    # Asumimos aprobado si está completado y no rechazado
                    stats.aprobados += 1
            elif video.estado == EstadoVideo.EN_REVISION:
                stats.en_revision += 1
            elif video.estado == EstadoVideo.PENDIENTE:
                stats.pendientes += 1

        # Calcular tasas
        tasa_aprobacion = (
            (stats.aprobados / stats.total * 100) if stats.total > 0 else 0
        )
        tasa_rechazo = (stats.rechazados / stats.total * 100) if stats.total > 0 else 0

        result = {
            "total_videos": stats.total,
            "aprobados": stats.aprobados,
            "rechazados": stats.rechazados,
            "en_revision": stats.en_revision,
            "pendientes": stats.pendientes,
            "tasa_aprobacion": round(tasa_aprobacion, 2),
            "tasa_rechazo": round(tasa_rechazo, 2),
            "fecha_calculo": datetime.now().isoformat(),
        }
        
        # Guardar en caché
        cache.cache_analytics('video', 'summary', result, ttl=TTL_VIDEO_SUMMARY)
        return result

    def get_user_summary(self) -> Dict[str, Any]:
        """
        Obtiene resumen de usuarios
        OPTIMIZADO: Usa caché Redis (TTL: 5 minutos)

        Returns:
            dict: Estadísticas de usuarios
        """
        # Intentar obtener del caché primero
        cache = self._get_cache()
        cached = cache.get_cached_analytics('user', 'summary')
        if cached:
            return cached
        
        user_repo = self._get_user_repo()
        all_users = user_repo.obtener_todos()

        total_users = len(all_users)
        active_users = sum(1 for u in all_users if u.activo)

        result = {
            "total_usuarios": total_users,
            "usuarios_activos": active_users,
            "usuarios_inactivos": total_users - active_users,
            "socios": total_users,
            "fecha_calculo": datetime.now().isoformat(),
        }
        
        # Guardar en caché
        cache.cache_analytics('user', 'summary', result, ttl=TTL_USER_SUMMARY)
        return result

    # ===== Estadísticas Temporales =====

    def get_daily_stats(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Obtiene estadísticas diarias de los últimos N días
        OPTIMIZADO: Usa caché Redis (TTL: 10 minutos)

        Args:
            days: Número de días a analizar

        Returns:
            list: Lista de estadísticas por día
        """
        # Intentar obtener del caché primero
        cache = self._get_cache()
        cache_key = f"daily_{days}"
        cached = cache.get_cached_analytics('stats', cache_key)
        if cached:
            return cached
        
        video_repo = self._get_video_repo()
        all_videos = video_repo.obtener_todos()

        # Inicializar estructura para los últimos N días
        daily_data = {}
        today = datetime.now().date()

        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.isoformat()
            daily_data[date_str] = {
                "fecha": date_str,
                "subidos": 0,
                "aprobados": 0,
                "rechazados": 0,
                "en_revision": 0,
            }

        # Contar videos por día
        for video in all_videos:
            if hasattr(video, "fecha_creacion") and video.fecha_creacion:
                try:
                    video_date = video.fecha_creacion.date().isoformat()
                    if video_date in daily_data:
                        daily_data[video_date]["subidos"] += 1

                        if video.estado == EstadoVideo.APROBADO:
                            daily_data[video_date]["aprobados"] += 1
                        elif video.estado == EstadoVideo.RECHAZADO:
                            daily_data[video_date]["rechazados"] += 1
                        elif video.estado == EstadoVideo.COMPLETADO:
                            if video.metadatos_ia.get("resultado_ia") == "RECHAZADO":
                                daily_data[video_date]["rechazados"] += 1
                            else:
                                daily_data[video_date]["aprobados"] += 1
                        elif video.estado == EstadoVideo.EN_REVISION:
                            daily_data[video_date]["en_revision"] += 1
                except Exception as e:
                    logger.debug(f"Error processing video date: {e}")

        # Ordenar por fecha descendente
        result = sorted(daily_data.values(), key=lambda x: x["fecha"], reverse=True)
        
        # Guardar en caché
        cache.cache_analytics('stats', cache_key, result, ttl=TTL_DAILY_STATS)
        return result

    def get_hourly_stats(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Obtiene estadísticas por hora de las últimas N horas

        Args:
            hours: Número de horas a analizar

        Returns:
            list: Lista de estadísticas por hora
        """
        video_repo = self._get_video_repo()
        all_videos = video_repo.obtener_todos()

        hourly_data = defaultdict(lambda: {"hora": "", "subidos": 0})
        now = datetime.now()

        for video in all_videos:
            if hasattr(video, "fecha_creacion") and video.fecha_creacion:
                try:
                    diff = now - video.fecha_creacion
                    if diff.total_seconds() <= hours * 3600:
                        hour_key = video.fecha_creacion.strftime("%Y-%m-%d %H:00")
                        hourly_data[hour_key]["hora"] = hour_key
                        hourly_data[hour_key]["subidos"] += 1
                except Exception as e:
                    logger.debug(f"Error processing video timestamp: {e}")

        return sorted(hourly_data.values(), key=lambda x: x["hora"], reverse=True)

    # ===== Análisis de Rechazos =====

    def get_rejection_reasons(self) -> List[Dict[str, Any]]:
        """
        Obtiene las razones de rechazo más comunes

        Returns:
            list: Lista de razones ordenadas por frecuencia
        """
        video_repo = self._get_video_repo()
        all_videos = video_repo.obtener_todos()

        reasons = defaultdict(int)
        total_rechazados = 0

        for video in all_videos:
            if video.estado == EstadoVideo.RECHAZADO or (
                video.estado == EstadoVideo.COMPLETADO
                and video.metadatos_ia.get("resultado_ia") == "RECHAZADO"
            ):
                total_rechazados += 1
                reason = video.metadatos_ia.get(
                    "razon_rechazo", "Razón no especificada"
                )

                # Categorizar razones
                reason_category = self._categorize_reason(reason)
                reasons[reason_category] += 1

        # Calcular porcentajes
        result = []
        for reason, count in reasons.items():
            percentage = (count / total_rechazados * 100) if total_rechazados > 0 else 0
            result.append(
                {"reason": reason, "count": count, "percentage": round(percentage, 2)}
            )

        # Ordenar por conteo descendente
        return sorted(result, key=lambda x: x["count"], reverse=True)

    def _categorize_reason(self, reason: str) -> str:
        """Categoriza una razón de rechazo"""
        reason_lower = reason.lower()

        if (
            "duración" in reason_lower
            or "duracion" in reason_lower
            or "corto" in reason_lower
            or "largo" in reason_lower
        ):
            return "Duración fuera de rango"
        elif (
            "explicito" in reason_lower
            or "explícito" in reason_lower
            or "nsfw" in reason_lower
        ):
            return "Contenido explícito"
        elif (
            "logo" in reason_lower
            or "marca" in reason_lower
            or "competencia" in reason_lower
        ):
            return "Logo de competencia detectado"
        elif (
            "texto" in reason_lower
            or "palabras" in reason_lower
            or "prohibido" in reason_lower
        ):
            return "Texto prohibido detectado"
        elif "violencia" in reason_lower or "arma" in reason_lower:
            return "Contenido violento"
        elif "spam" in reason_lower or "publicidad" in reason_lower:
            return "Spam/Publicidad no autorizada"
        else:
            return "Otras razones"

    # ===== Estadísticas por Usuario =====

    def get_user_video_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Obtiene estadísticas de videos de un usuario específico

        Args:
            user_id: ID del usuario

        Returns:
            dict: Estadísticas del usuario
        """
        video_repo = self._get_video_repo()
        user_videos = video_repo.obtener_por_usuario(user_id)

        stats = {
            "total_videos": len(user_videos),
            "aprobados": 0,
            "rechazados": 0,
            "en_revision": 0,
            "pendientes": 0,
            "duracion_total_segundos": 0,
            "ultimo_video": None,
        }

        for video in user_videos:
            if video.estado == EstadoVideo.APROBADO:
                stats["aprobados"] += 1
            elif video.estado == EstadoVideo.RECHAZADO:
                stats["rechazados"] += 1
            elif video.estado == EstadoVideo.COMPLETADO:
                if video.metadatos_ia.get("resultado_ia") == "RECHAZADO":
                    stats["rechazados"] += 1
                else:
                    stats["aprobados"] += 1
            elif video.estado == EstadoVideo.EN_REVISION:
                stats["en_revision"] += 1
            elif video.estado == EstadoVideo.PENDIENTE:
                stats["pendientes"] += 1

            # Sumar duración
            duracion = video.metadatos_ia.get("duracion_segundos", 0)
            if isinstance(duracion, (int, float)):
                stats["duracion_total_segundos"] += duracion

        # Calcular tasa de aprobación del usuario
        if stats["total_videos"] > 0:
            stats["tasa_aprobacion"] = round(
                stats["aprobados"] / stats["total_videos"] * 100, 2
            )
        else:
            stats["tasa_aprobacion"] = 0.0

        return stats

    def get_top_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Obtiene los usuarios con más videos aprobados

        Args:
            limit: Número máximo de usuarios a retornar

        Returns:
            list: Lista de usuarios con sus estadísticas
        """
        video_repo = self._get_video_repo()
        user_repo = self._get_user_repo()
        all_videos = video_repo.obtener_todos()

        user_stats = defaultdict(lambda: {"total": 0, "aprobados": 0})

        for video in all_videos:
            user_id = video.usuario
            user_stats[user_id]["total"] += 1
            if video.estado == EstadoVideo.APROBADO or (
                video.estado == EstadoVideo.COMPLETADO
                and video.metadatos_ia.get("resultado_ia") != "RECHAZADO"
            ):
                user_stats[user_id]["aprobados"] += 1

        # Crear lista con información de usuario
        result = []
        for user_id, stats in user_stats.items():
            usuario = user_repo.obtener_por_id(user_id)
            result.append(
                {
                    "user_id": user_id,
                    "nombre": usuario.nombre_completo if usuario else "Desconocido",
                    "total_videos": stats["total"],
                    "videos_aprobados": stats["aprobados"],
                    "tasa_aprobacion": round(
                        stats["aprobados"] / stats["total"] * 100, 2
                    )
                    if stats["total"] > 0
                    else 0,
                }
            )

        # Ordenar por videos aprobados
        result.sort(key=lambda x: x["videos_aprobados"], reverse=True)
        return result[:limit]

    # ===== Reportes =====

    def generate_full_report(self) -> Dict[str, Any]:
        """
        Genera un reporte completo del sistema

        Returns:
            dict: Reporte completo con todas las métricas
        """
        return {
            "fecha_generacion": datetime.now().isoformat(),
            "periodo": "Últimos 7 días",
            "resumen_videos": self.get_video_summary(),
            "resumen_usuarios": self.get_user_summary(),
            "estadisticas_diarias": self.get_daily_stats(7),
            "razones_rechazo": self.get_rejection_reasons(),
            "top_usuarios": self.get_top_users(5),
        }

    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """
        Obtiene métricas rápidas para el dashboard

        Returns:
            dict: Métricas principales para mostrar en dashboard
        """
        video_summary = self.get_video_summary()
        user_summary = self.get_user_summary()

        return {
            # KPIs principales
            "total_videos": video_summary["total_videos"],
            "videos_pendientes": video_summary["en_revision"]
            + video_summary["pendientes"],
            "tasa_aprobacion": video_summary["tasa_aprobacion"],
            "total_usuarios": user_summary["total_usuarios"],
            # Métricas secundarias
            "videos_hoy": self._count_videos_today(),
            "rechazos_hoy": self._count_rejections_today(),
            # Alertas
            "alertas": self._generate_alerts(),
        }

    def _count_videos_today(self) -> int:
        """Cuenta videos subidos hoy"""
        video_repo = self._get_video_repo()
        all_videos = video_repo.obtener_todos()
        today = datetime.now().date()

        count = 0
        for video in all_videos:
            if hasattr(video, "fecha_creacion") and video.fecha_creacion:
                try:
                    if video.fecha_creacion.date() == today:
                        count += 1
                except Exception as e:
                    logger.debug(f"Error checking video date: {e}")
        return count

    def _count_rejections_today(self) -> int:
        """Cuenta rechazos de hoy"""
        video_repo = self._get_video_repo()
        all_videos = video_repo.obtener_todos()
        today = datetime.now().date()

        count = 0
        for video in all_videos:
            if video.estado == EstadoVideo.RECHAZADO or (
                video.estado == EstadoVideo.COMPLETADO
                and video.metadatos_ia.get("resultado_ia") == "RECHAZADO"
            ):
                if hasattr(video, "fecha_creacion") and video.fecha_creacion:
                    try:
                        if video.fecha_creacion.date() == today:
                            count += 1
                    except Exception as e:
                        logger.debug(f"Error checking rejection date: {e}")
        return count

    def _generate_alerts(self) -> List[Dict[str, str]]:
        """Genera alertas basadas en métricas"""
        alerts = []
        video_summary = self.get_video_summary()

        # Alerta: muchos videos pendientes
        if video_summary["en_revision"] > 10:
            alerts.append(
                {
                    "type": "warning",
                    "message": f"{video_summary['en_revision']} videos pendientes de revisión manual",
                }
            )

        # Alerta: alta tasa de rechazo
        if video_summary["tasa_rechazo"] > 50:
            alerts.append(
                {
                    "type": "danger",
                    "message": f"Tasa de rechazo alta: {video_summary['tasa_rechazo']}%",
                }
            )

        return alerts


# Singleton instance
from typing import Optional as Opt

_analytics_service: Opt[AnalyticsService] = None


def get_analytics_service() -> AnalyticsService:
    """Obtiene la instancia singleton del servicio de analytics"""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service
