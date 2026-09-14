import os
import json
import uuid
import time
from pathlib import Path
import logging

from flask import current_app
from werkzeug.utils import secure_filename

from domain.entities import Video, EstadoVideo, ReglaNegocioException
from infrastructure.dependencies import (
    get_video_repository,
    get_storage_adapter,
)

logger = logging.getLogger(__name__)

SIGNED_URL_CACHE_TTL_SECONDS = int(os.environ.get("SIGNED_URL_CACHE_TTL_SECONDS", "45"))
_SIGNED_URL_CACHE: dict[str, dict] = {}

class SocioVideoService:
    """
    Servicio de aplicación para las operaciones del Socio (AccessFan)
    Extrae la lógica de negocio del controlador obeso (app_socio.py)
    """
    
    def __init__(self):
        self.video_repo = get_video_repository()
        
    def get_formatted_video_details(self, video_id: str, usuario_actual: str) -> dict:
        video = self.video_repo.obtener_por_id(video_id)
        if not video:
            raise ValueError("Video no encontrado")

        if video.usuario != usuario_actual:
            raise PermissionError("No autorizado")

        metadatos = video.metadatos_ia or {}

        # Si el video aún no finalizó, retornar datos parciales con lo disponible
        if not self._is_video_finalized(video.estado):
            nombre_archivo = getattr(video, "nombre_archivo", None) or metadatos.get("nombre_archivo", "video.mp4")
            return {
                "id": video.id,
                "titulo": metadatos.get("titulo") or Path(nombre_archivo).stem if nombre_archivo else f"Video {video.id[:8]}",
                "descripcion": video.descripcion,
                "estado": video.estado.value,
                "video_url": None,
                "fecha_carga": getattr(video, "fecha_creacion", None) or metadatos.get("fecha_procesamiento"),
                "fecha_procesamiento": metadatos.get("fecha_procesamiento"),
                "resultado_ia": None,
                "confianza": 0,
                "razon": None,
                "analisis": None,
                "shots": [],
                "texto_detectado": [],
                "labels": [],
                "duracion_segundos": metadatos.get("duracion_segundos", 0),
                "razon_rechazo": "",
                "en_progreso": True,
                "metadatos_ia": {
                    "titulo": metadatos.get("titulo"),
                    "nombre_archivo": nombre_archivo,
                    "progreso": metadatos.get("progreso", {}),
                    "resultado_ia": None,
                    "confianza_ia": 0,
                },
            }

        # 1. Normalizar shots
        shots = self._normalize_shots(metadatos)
        
        # 2. Generar URL firmada
        video_url = self._generate_signed_url(metadatos, video)
        
        # 3. Extraer y formatear análisis
        analisis = self._extract_text_analysis(metadatos)
        
        # 4. Construir DTO
        return self._build_details_dto(video, metadatos, video_url, analisis, shots)
        
    def format_user_videos_list(self, usuario: str) -> list:
        videos_usuario = self.video_repo.obtener_por_usuario(usuario)
        
        workspace_names = {}
        workspace_ids_needed = set()
        for video in videos_usuario:
            ws_id = getattr(video, "workspace_id", None)
            if ws_id:
                workspace_ids_needed.add(ws_id)
        
        from infrastructure.repositories.workspace_repository import WorkspaceRepository
        ws_repo = WorkspaceRepository()
        for ws_id in workspace_ids_needed:
            try:
                ws = ws_repo.obtener_por_id(ws_id)
                if ws:
                    workspace_names[ws_id] = ws.nombre
            except Exception:
                pass

        videos_response = []
        for video in videos_usuario:
            nombre_archivo = getattr(video, "nombre_archivo", None) or video.metadatos_ia.get("nombre_archivo", "video.mp4")
            titulo = Path(nombre_archivo).stem if nombre_archivo else f"Video {video.id[:8]}"
            ws_id = getattr(video, "workspace_id", None)

            videos_response.append({
                "id": video.id,
                "titulo": titulo,
                "descripcion": video.descripcion,
                "nombre_archivo": nombre_archivo,
                "estado": video.estado.value,
                "descripcion_estado": self._obtener_descripcion_estado(video.estado),
                "resultado_ia": video.metadatos_ia.get("resultado_ia"),
                "confianza_ia": video.metadatos_ia.get("confianza_ia"),
                "decision_automatica": video.metadatos_ia.get("decision_automatica", True),
                "fecha_subida": getattr(video, "fecha_creacion", None) 
                    or video.metadatos_ia.get("fecha_procesamiento")
                    or video.metadatos_ia.get("upload_date"),
                "created_at": getattr(video, "fecha_creacion", None)
                    or video.metadatos_ia.get("fecha_procesamiento"),
                "razon_rechazo": video.metadatos_ia.get("razon_rechazo"),
                "razon_revision": video.metadatos_ia.get("razon_revision"),
                "sugerencia_ia": video.metadatos_ia.get("sugerencia_ia"),
                "analisis_ia": video.metadatos_ia.get("analisis_ia"),
                "thumbnail_url": f"/thumbnail/{video.id}",
                "workspace_id": ws_id,
                "workspace_nombre": workspace_names.get(ws_id, "Sin proyecto") if ws_id else "Sin proyecto",
            })
        return videos_response

    # --- Métodos Privados --- 

    def _normalize_shots(self, metadatos: dict) -> list:
        shots = []
        shots_raw = metadatos.get("shots", [])
        for s in shots_raw:
            shots.append({
                "start_time": s.get("start_time", 0),
                "end_time": s.get("end_time", 0),
                "start_formatted": s.get("start_formatted", ""),
                "end_formatted": s.get("end_formatted", ""),
                "shot_number": s.get("shot_number", 0),
            })
            
        vi_data = metadatos.get("video_intelligence", {})
        vi_shots = vi_data.get("shots", [])
        if not shots and vi_shots:
            for s in vi_shots:
                shots.append({
                    "start_time": s.get("start_time", 0),
                    "end_time": s.get("end_time", 0),
                    "start_formatted": s.get("start_formatted", ""),
                    "end_formatted": s.get("end_formatted", ""),
                    "shot_number": s.get("shot_number", 0),
                })
        return shots

    def _generate_signed_url(self, metadatos: dict, video: Video) -> str:
        # Usar endpoint proxy del backend — no requiere Signed URLs ni Service Account key
        return f"/socio/media/{video.id}"

    def _is_video_finalized(self, estado: EstadoVideo) -> bool:
        return estado in {
            EstadoVideo.COMPLETADO,
            EstadoVideo.APROBADO,
            EstadoVideo.RECHAZADO,
            EstadoVideo.ERROR,
        }

    def _extract_text_analysis(self, metadatos: dict) -> str:
        analisis = metadatos.get("analisis_ia_texto")
        if not analisis and isinstance(metadatos.get("analisis_ia"), dict):
            analisis = metadatos.get("analisis_ia", {}).get("analisis_detallado", "")
        if not analisis and isinstance(metadatos.get("analisis_ia"), str):
            analisis = metadatos.get("analisis_ia")
        return analisis

    def _build_details_dto(self, video: Video, metadatos: dict, video_url: str, analisis: str, shots: list) -> dict:
        vi_data = metadatos.get("video_intelligence", {})
        video_data = {
            "id": video.id,
            "titulo": metadatos.get("titulo", video.descripcion) or "Sin título",
            "descripcion": video.descripcion,
            "estado": video.estado.value,
            "video_url": video_url,
            "fecha_carga": metadatos.get("fecha_procesamiento"),
            "fecha_procesamiento": metadatos.get("fecha_procesamiento"),
            "resultado_ia": metadatos.get("resultado_ia"),
            "confianza": metadatos.get("confianza_ia", metadatos.get("confianza_decision", 0)),
            "razon": metadatos.get("razon_decision") or metadatos.get("razon_rechazo") or metadatos.get("razon_aprobacion"),
            "analisis": analisis,
            "shots": shots,
            "texto_detectado": metadatos.get("texto_detectado", metadatos.get("ocr_text", [])),
            "labels": metadatos.get("labels", metadatos.get("etiquetas", [])),
            "duracion_segundos": metadatos.get("duracion_segundos", 0),
            "razon_rechazo": metadatos.get("razon_rechazo", ""),
            "metadatos_ia": {
                "titulo": metadatos.get("titulo"),
                "nombre_archivo": metadatos.get("nombre_archivo"),
                "duracion_segundos": metadatos.get("duracion_segundos", 0),
                "storage_uri": metadatos.get("storage_uri"),
                "video_url": video_url,
                "resultado_ia": metadatos.get("resultado_ia"),
                "confianza_ia": metadatos.get("confianza_ia", 0),
                "razon_decision": metadatos.get("razon_decision"),
                "razon_rechazo": metadatos.get("razon_rechazo", ""),
                "analisis_ia": metadatos.get("analisis_ia"),
                "video_intelligence": {"labels": vi_data.get("labels", []), "text": vi_data.get("text", [])} if vi_data else None,
                "progreso": metadatos.get("progreso", {}),
            },
        }
        if hasattr(video, "created_at") and video.created_at:
            video_data["fecha_carga"] = video.created_at
        return video_data

    def _obtener_descripcion_estado(self, estado: EstadoVideo) -> str:
        descripciones = {
            EstadoVideo.PENDIENTE: "Tu video está pendiente de procesamiento",
            EstadoVideo.PROCESANDO: "Tu video se está procesando",
            EstadoVideo.COMPLETADO: "¡Tu video ha sido aprobado!",
            EstadoVideo.ERROR: "Tu video fue rechazado por no cumplir con los estándares",
            EstadoVideo.EN_REVISION: "Tu video está siendo revisado manualmente por nuestro equipo",
            EstadoVideo.APROBADO: "¡Tu video ha sido aprobado definitivamente!",
            EstadoVideo.RECHAZADO: "Tu video ha sido rechazado tras la revisión",
        }
        return descripciones.get(estado, "Estado desconocido")
