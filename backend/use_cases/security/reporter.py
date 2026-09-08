import logging
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any

from domain.entities import SecurityVideo

logger = logging.getLogger(__name__)

class SecurityVideoReportGenerator:
    """Extrae la lógica de generación de reportes y notificaciones"""

    def __init__(self, storage_adapter, repository):
        self.storage_adapter = storage_adapter
        self.repository = repository

    def generate_complete_report(self, video: SecurityVideo, events: List[Dict], cross_analysis: Dict):
        try:
            from infrastructure.services.report_generator import ReportGenerator
            from domain.entities import EventoSeguridad
            
            generator = ReportGenerator()
            
            eventos_obj = []
            for idx, ev in enumerate(events):
                try:
                    event_id = ev.get('id') or f"ev_{video.id}_{idx}_{uuid.uuid4().hex[:6]}"
                    evento = EventoSeguridad(
                        id=event_id,
                        security_video_id=ev.get('security_video_id') or video.id,
                        timestamp_inicio=ev.get('timestamp_inicio', 0.0),
                        timestamp_fin=ev.get('timestamp_fin', 0.0),
                        duracion=max(ev.get('duracion', 0.1), 0.1),
                        objetos_detectados=ev.get('objetos_detectados', []),
                        acciones_detectadas=ev.get('acciones_detectadas', []),
                        personas_count=ev.get('personas_count', 0),
                        vehiculos_count=ev.get('vehiculos_count', 0),
                        descripcion=ev.get('descripcion', ''),
                        confianza=min(max(ev.get('confianza', 0.0), 0.0), 1.0),
                        analisis_detallado=ev.get('analisis_detallado', {}),
                        frames_urls=ev.get('frames_urls', []),
                        metadata=ev.get('metadata', {})
                    )
                    eventos_obj.append(evento)
                except Exception as conv_err:
                    logger.warning(f"⚠️ Error convirtiendo evento: {conv_err}")

            # Generar TXT
            txt_content = generator.generate_text_report(video, eventos_obj, cross_analysis=cross_analysis)
            txt_path = f"/tmp/report_{video.id}.txt"
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(txt_content)
                
            txt_blob = f"reports/{video.id}/report.txt"
            txt_url = self.storage_adapter.upload_file(txt_path, txt_blob, return_signed_url=True)
            if txt_url: video.reporte_txt_url = txt_url
            
            # Generar PDF
            pdf_path = f"/tmp/report_{video.id}.pdf"
            if generator.generate_pdf_report(video, eventos_obj, pdf_path, cross_analysis=cross_analysis):
                pdf_blob = f"reports/{video.id}/report.pdf"
                pdf_url = self.storage_adapter.upload_file(pdf_path, pdf_blob, return_signed_url=True)
                if pdf_url: video.reporte_pdf_url = pdf_url
                if os.path.exists(pdf_path): os.remove(pdf_path)
            
            self.repository.guardar_video(video)
            if os.path.exists(txt_path): os.remove(txt_path)
            
        except Exception as e:
            logger.error(f"Error generando reportes: {e}", exc_info=True)

    def notify_analysis_complete(self, video: SecurityVideo, events: List[Dict], cross_analysis: Dict):
        try:
            notify_email = video.metadata_tecnico.get('notify_email')
            if not notify_email: return
            
            from infrastructure.services.notification_service import NotificationService
            notifier = NotificationService()
            
            total_eventos = len(events)
            nivel_riesgo = cross_analysis.get('nivel_riesgo_global', 'N/A')
            duracion = video.duracion_segundos or 0
            duracion_str = f"{duracion/3600:.1f}h" if duracion > 3600 else f"{duracion/60:.1f}min"
            
            notifier.send_email(
                to=notify_email,
                subject=f"✅ Análisis completado: {video.nombre_camara}",
                body=f"Resultados de {video.nombre_camara} duración {duracion_str}. Riesgo: {nivel_riesgo}."
            )
        except Exception as e:
            logger.error(f"Error notificaciones: {e}")
