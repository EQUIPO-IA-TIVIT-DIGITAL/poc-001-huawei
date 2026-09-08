"""
Adaptador de Cloud Tasks - TIVIT Video
Cola de tareas asíncronas usando Google Cloud Tasks (GCP-only)
"""
import os
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CloudTasksAdapter:
    """
    Adaptador para Google Cloud Tasks (GCP-only)
    
    Proporciona una interfaz para encolar tareas asíncronas en Cloud Tasks.
    
    Configuración requerida en .env:
        GCP_PROJECT_ID=tu-proyecto
        GCP_REGION=us-central1
        CLOUD_TASKS_QUEUE=video-processing
        CLOUD_TASKS_SERVICE_URL=https://tu-servicio.run.app
    """
    
    def __init__(self):
        self.project_id = os.getenv('GCP_PROJECT_ID')
        self.region = os.getenv('GCP_REGION', 'us-central1')
        self.queue_name = os.getenv('CLOUD_TASKS_QUEUE', 'video-processing')
        self.service_url = os.getenv('CLOUD_TASKS_SERVICE_URL')
        
        self._client = None
        self._queue_path = None
        self._initialized = False
        
        self._initialize()
    
    def _initialize(self):
        """Inicializa el cliente de Cloud Tasks"""
        if not self.project_id:
            logger.warning("⚠️ Cloud Tasks: GCP_PROJECT_ID no configurado (servicio opcional)")
            return
        
        if not self.service_url:
            logger.warning("⚠️ Cloud Tasks: CLOUD_TASKS_SERVICE_URL no configurado (servicio opcional)")
            return
        
        try:
            from google.cloud import tasks_v2
            
            self._client = tasks_v2.CloudTasksClient()
            self._queue_path = self._client.queue_path(
                self.project_id, 
                self.region, 
                self.queue_name
            )
            self._initialized = True
            
            logger.info(f"✅ Cloud Tasks inicializado")
            logger.info(f"   Cola: {self._queue_path}")
            logger.info(f"   Service URL: {self.service_url}")
            
        except ImportError:
            logger.error("❌ google-cloud-tasks no instalado. Ejecuta: pip install google-cloud-tasks")
        except Exception as e:
            logger.error(f"❌ Error inicializando Cloud Tasks: {e}")
    
    @property
    def disponible(self) -> bool:
        """Verifica si Cloud Tasks está disponible"""
        return self._initialized and self._client is not None
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna el estado del servicio"""
        return {
            'available': self.disponible,
            'queue': self.queue_name if self.disponible else None,
            'region': self.region if self.disponible else None,
            'service_url': self.service_url if self.disponible else None,
            'project_id': self.project_id
        }
    
    def _crear_task(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        delay_seconds: int = 0
    ) -> Dict[str, Any]:
        """Crea una tarea en Cloud Tasks"""
        if not self.disponible:
            return {
                'success': False,
                'error': 'Cloud Tasks no disponible',
                'backend': 'cloud_tasks'
            }
        
        try:
            from google.cloud import tasks_v2
            from google.protobuf import timestamp_pb2
            
            # Construir URL completa
            url = f"{self.service_url.rstrip('/')}{endpoint}"
            
            # Crear tarea
            worker_token = os.getenv("WORKER_INTERNAL_TOKEN", "")
            headers = {
                "Content-Type": "application/json",
            }
            if worker_token:
                headers["X-Internal-Worker-Token"] = worker_token

            task = {
                'http_request': {
                    'http_method': tasks_v2.HttpMethod.POST,
                    'url': url,
                    'headers': headers,
                    'body': json.dumps(payload).encode('utf-8')
                }
            }
            
            # Agregar delay si se especifica
            if delay_seconds > 0:
                schedule_time = datetime.utcnow() + timedelta(seconds=delay_seconds)
                timestamp = timestamp_pb2.Timestamp()
                timestamp.FromDatetime(schedule_time)
                task['schedule_time'] = timestamp
            
            # Crear la tarea
            response = self._client.create_task(
                parent=self._queue_path,
                task=task
            )
            
            task_name = response.name.split('/')[-1]
            
            logger.info(f"📋 Cloud Task creada: {task_name}")
            
            return {
                'success': True,
                'backend': 'cloud_tasks',
                'task_id': task_name,
                'queue': self.queue_name,
                'endpoint': endpoint,
                'scheduled_delay': delay_seconds
            }
        except Exception as e:
            logger.error(f"❌ Error creando tarea en Cloud Tasks: {e}")
            return {
                'success': False,
                'error': str(e),
                'backend': 'cloud_tasks'
            }

    def create_task(
        self,
        queue_name: str,
        endpoint: str,
        payload: Dict[str, Any],
        delay_seconds: int = 0,
    ) -> str:
        """Compatibility wrapper used by security module.

        Returns the task id on success and raises RuntimeError on failure.
        """
        original_queue = self.queue_name
        try:
            if queue_name and queue_name != self.queue_name:
                self.queue_name = queue_name
                if self.disponible:
                    self._queue_path = self._client.queue_path(
                        self.project_id,
                        self.region,
                        self.queue_name,
                    )

            result = self._crear_task(
                endpoint=endpoint,
                payload=payload,
                delay_seconds=delay_seconds,
            )
            if not result.get("success"):
                raise RuntimeError(result.get("error", "No se pudo crear task"))

            return result.get("task_id", "")
        except Exception as e:
            logger.error(f"❌ Error creando Cloud Task: {e}")
            raise RuntimeError(f"Error creando Cloud Task: {e}")
        finally:
            if self.queue_name != original_queue:
                self.queue_name = original_queue
                if self.disponible:
                    self._queue_path = self._client.queue_path(
                        self.project_id,
                        self.region,
                        self.queue_name,
                    )
    
    def encolar_procesamiento_video(
        self, 
        video_id: str,
        ruta_gcs: str,
        usuario: str,
        nombre_archivo: str,
        delay_seconds: int = 0
    ) -> Dict[str, Any]:
        """
        Encola una tarea de procesamiento de video.
        
        Args:
            video_id: ID único del video
            ruta_gcs: Ruta en Cloud Storage (gs://bucket/path)
            usuario: Usuario que subió el video
            nombre_archivo: Nombre original del archivo
            delay_seconds: Segundos de delay antes de ejecutar
            
        Returns:
            Dict con información de la tarea creada
        """
        payload = {
            'video_id': video_id,
            'ruta_gcs': ruta_gcs,
            'usuario': usuario,
            'nombre_archivo': nombre_archivo,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return self._crear_task(
            endpoint='/tasks/process-video',
            payload=payload,
            delay_seconds=delay_seconds
        )
    
    def encolar_generacion_thumbnail(
        self,
        video_id: str,
        ruta_gcs: str,
        delay_seconds: int = 5
    ) -> Dict[str, Any]:
        """
        Encola generación de thumbnail para un video.
        
        Args:
            video_id: ID del video
            ruta_gcs: Ruta del video en GCS
            delay_seconds: Delay antes de ejecutar
        """
        payload = {
            'video_id': video_id,
            'ruta_gcs': ruta_gcs,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return self._crear_task(
            endpoint='/tasks/generate-thumbnail',
            payload=payload,
            delay_seconds=delay_seconds
        )
    
    def encolar_notificacion(
        self,
        usuario_id: str,
        tipo: str,
        mensaje: str,
        datos: Dict[str, Any] = None,
        delay_seconds: int = 0
    ) -> Dict[str, Any]:
        """
        Encola envío de notificación.
        
        Args:
            usuario_id: ID del usuario a notificar
            tipo: Tipo de notificación (email, push, etc)
            mensaje: Mensaje de la notificación
            datos: Datos adicionales
            delay_seconds: Delay antes de enviar
        """
        payload = {
            'usuario_id': usuario_id,
            'tipo': tipo,
            'mensaje': mensaje,
            'datos': datos or {},
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return self._crear_task(
            endpoint='/tasks/send-notification',
            payload=payload,
            delay_seconds=delay_seconds
        )
    
    def encolar_limpieza(
        self,
        dias_antiguedad: int = 30,
        delay_seconds: int = 0
    ) -> Dict[str, Any]:
        """
        Encola tarea de limpieza de archivos antiguos.
        
        Args:
            dias_antiguedad: Archivos más antiguos que esto serán eliminados
            delay_seconds: Delay antes de ejecutar
        """
        payload = {
            'dias_antiguedad': dias_antiguedad,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return self._crear_task(
            endpoint='/tasks/cleanup',
            payload=payload,
            delay_seconds=delay_seconds
        )
    
    def encolar_tarea_personalizada(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        delay_seconds: int = 0
    ) -> Dict[str, Any]:
        """
        Encola una tarea personalizada.
        
        Args:
            endpoint: Endpoint a llamar (ej: /tasks/mi-tarea)
            payload: Datos a enviar
            delay_seconds: Delay antes de ejecutar
        """
        return self._crear_task(
            endpoint=endpoint,
            payload=payload,
            delay_seconds=delay_seconds
        )


# ============================================
# Singleton
# ============================================
_instance: Optional[CloudTasksAdapter] = None


def get_cloud_tasks_adapter() -> CloudTasksAdapter:
    """Obtiene la instancia singleton del adaptador de Cloud Tasks"""
    global _instance
    if _instance is None:
        _instance = CloudTasksAdapter()
    return _instance


# Alias para compatibilidad
get_cloud_tasks = get_cloud_tasks_adapter


# ============================================
# Funciones de conveniencia
# ============================================

def encolar_video(video_id: str, ruta_gcs: str, usuario: str, nombre_archivo: str) -> Dict[str, Any]:
    """Atajo para encolar procesamiento de video"""
    return get_cloud_tasks_adapter().encolar_procesamiento_video(
        video_id=video_id,
        ruta_gcs=ruta_gcs,
        usuario=usuario,
        nombre_archivo=nombre_archivo
    )


def encolar_thumbnail(video_id: str, ruta_gcs: str) -> Dict[str, Any]:
    """Atajo para encolar generación de thumbnail"""
    return get_cloud_tasks_adapter().encolar_generacion_thumbnail(
        video_id=video_id,
        ruta_gcs=ruta_gcs
    )
