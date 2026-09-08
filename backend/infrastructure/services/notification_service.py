"""
Servicio de Notificaciones - AccessFan
Maneja el envío de emails y notificaciones a usuarios
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from datetime import datetime


import logging
logger = logging.getLogger(__name__)

class NotificationService:
    """
    Servicio para enviar notificaciones por email
    
    Soporta:
    - Notificación de video aprobado
    - Notificación de video rechazado
    - Notificación de video en revisión
    - Notificación a admin de videos pendientes
    """
    
    def __init__(self):
        """Inicializa el servicio de notificaciones"""
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.from_email = os.getenv('SMTP_FROM', 'noreply@accessfan.com')
        self.from_name = os.getenv('SMTP_FROM_NAME', 'AccessFan - TIVIT')
        self.app_base_url = os.getenv('APP_BASE_URL', '').rstrip('/')
        
        # Verificar configuración
        self.is_configured = bool(self.smtp_user and self.smtp_password)
        
        if not self.is_configured:
            logger.warning(" Notificaciones por email deshabilitadas (SMTP no configurado)")
        else:
            logger.info(f"Servicio de notificaciones configurado: {self.smtp_host}")
    
    def is_available(self) -> bool:
        """Verifica si el servicio está disponible"""
        return self.is_configured
    
    def send_video_approved(self, user_email: str, user_name: str, video_data: Dict[str, Any]) -> bool:
        """
        Envía notificación de video aprobado
        
        Args:
            user_email: Email del usuario
            user_name: Nombre del usuario
            video_data: Datos del video (id, descripcion, fecha, etc.)
        """
        subject = "✅ ¡Tu video ha sido aprobado! - AccessFan"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #E30613 0%, #C70000 100%); color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 30px; }}
                .success-badge {{ background: #00cc66; color: white; padding: 10px 20px; border-radius: 20px; display: inline-block; font-weight: bold; }}
                .video-info {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .footer {{ background: #1e293b; color: #94a3b8; padding: 20px; text-align: center; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎬 AccessFan</h1>
                    <p>Plataforma de contenido UGC - TIVIT Latam</p>
                </div>
                <div class="content">
                    <h2>¡Hola {user_name}!</h2>
                    <p>Nos complace informarte que tu video ha sido <span class="success-badge">APROBADO</span></p>
                    
                    <div class="video-info">
                        <h3>📹 Detalles del video:</h3>
                        <p><strong>ID:</strong> {video_data.get('id', 'N/A')}</p>
                        <p><strong>Descripción:</strong> {video_data.get('descripcion', 'Sin descripción')}</p>
                        <p><strong>Duración:</strong> {video_data.get('duracion_segundos', 'N/A')} segundos</p>
                        <p><strong>Fecha de procesamiento:</strong> {video_data.get('fecha_procesamiento', datetime.now().isoformat())}</p>
                    </div>
                    
                    <p>Tu video ya está disponible en nuestra plataforma.</p>
                    <p>¡Gracias por compartir contenido de calidad!</p>
                </div>
                <div class="footer">
                    <p>© 2025 AccessFan - Powered by TIVIT Latam</p>
                    <p>Este es un mensaje automático, por favor no respondas a este correo.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self._send_email(user_email, subject, html_content)
    
    def send_video_rejected(self, user_email: str, user_name: str, video_data: Dict[str, Any], reason: str) -> bool:
        """
        Envía notificación de video rechazado
        
        Args:
            user_email: Email del usuario
            user_name: Nombre del usuario
            video_data: Datos del video
            reason: Razón del rechazo
        """
        subject = "❌ Tu video no ha sido aprobado - AccessFan"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #E30613 0%, #C70000 100%); color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 30px; }}
                .rejected-badge {{ background: #E30613; color: white; padding: 10px 20px; border-radius: 20px; display: inline-block; font-weight: bold; }}
                .reason-box {{ background: #fff3f3; border-left: 4px solid #E30613; padding: 15px; margin: 20px 0; }}
                .video-info {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .footer {{ background: #1e293b; color: #94a3b8; padding: 20px; text-align: center; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎬 AccessFan</h1>
                    <p>Plataforma de contenido UGC - TIVIT Latam</p>
                </div>
                <div class="content">
                    <h2>Hola {user_name},</h2>
                    <p>Lamentamos informarte que tu video ha sido <span class="rejected-badge">RECHAZADO</span></p>
                    
                    <div class="reason-box">
                        <h3>📋 Razón del rechazo:</h3>
                        <p>{reason}</p>
                    </div>
                    
                    <div class="video-info">
                        <h3>📹 Detalles del video:</h3>
                        <p><strong>ID:</strong> {video_data.get('id', 'N/A')}</p>
                        <p><strong>Descripción:</strong> {video_data.get('descripcion', 'Sin descripción')}</p>
                    </div>
                    
                    <p>Puedes intentar subir un nuevo video que cumpla con nuestras políticas de contenido.</p>
                    <p>Si crees que esto es un error, contacta a nuestro equipo de soporte.</p>
                </div>
                <div class="footer">
                    <p>© 2025 AccessFan - Powered by TIVIT Latam</p>
                    <p>Este es un mensaje automático, por favor no respondas a este correo.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self._send_email(user_email, subject, html_content)
    
    def send_video_in_review(self, user_email: str, user_name: str, video_data: Dict[str, Any]) -> bool:
        """
        Envía notificación de video en revisión manual
        
        Args:
            user_email: Email del usuario
            user_name: Nombre del usuario
            video_data: Datos del video
        """
        subject = "🔍 Tu video está siendo revisado - AccessFan"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #E30613 0%, #C70000 100%); color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 30px; }}
                .review-badge {{ background: #ffaa00; color: white; padding: 10px 20px; border-radius: 20px; display: inline-block; font-weight: bold; }}
                .video-info {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .footer {{ background: #1e293b; color: #94a3b8; padding: 20px; text-align: center; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎬 AccessFan</h1>
                    <p>Plataforma de contenido UGC - TIVIT Latam</p>
                </div>
                <div class="content">
                    <h2>Hola {user_name},</h2>
                    <p>Tu video está actualmente <span class="review-badge">EN REVISIÓN</span></p>
                    
                    <p>Nuestro equipo de moderación está revisando tu contenido manualmente. 
                    Este proceso puede tomar entre 24 y 48 horas.</p>
                    
                    <div class="video-info">
                        <h3>📹 Detalles del video:</h3>
                        <p><strong>ID:</strong> {video_data.get('id', 'N/A')}</p>
                        <p><strong>Descripción:</strong> {video_data.get('descripcion', 'Sin descripción')}</p>
                    </div>
                    
                    <p>Te notificaremos por email cuando tengamos una decisión.</p>
                </div>
                <div class="footer">
                    <p>© 2025 AccessFan - Powered by TIVIT Latam</p>
                    <p>Este es un mensaje automático, por favor no respondas a este correo.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self._send_email(user_email, subject, html_content)
    
    def send_admin_pending_review(self, admin_email: str, pending_count: int) -> bool:
        """
        Envía notificación al admin sobre videos pendientes de revisión
        
        Args:
            admin_email: Email del administrador
            pending_count: Cantidad de videos pendientes
        """
        subject = f"🔔 {pending_count} videos pendientes de revisión - AccessFan"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 30px; }}
                .count-badge {{ background: #E30613; color: white; padding: 20px 40px; border-radius: 10px; display: inline-block; font-size: 32px; font-weight: bold; }}
                .btn {{ display: inline-block; background: #E30613; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; margin-top: 20px; }}
                .footer {{ background: #1e293b; color: #94a3b8; padding: 20px; text-align: center; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🛡️ Panel de Administración</h1>
                    <p>AccessFan - TIVIT Latam</p>
                </div>
                <div class="content" style="text-align: center;">
                    <h2>Videos pendientes de revisión:</h2>
                    <div class="count-badge">{pending_count}</div>
                    <p style="margin-top: 20px;">Hay videos esperando tu revisión manual.</p>
                    <a href="{self.app_base_url}/admin" class="btn">Ir al Dashboard</a>
                </div>
                <div class="footer">
                    <p>© 2025 AccessFan - Powered by TIVIT Latam</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self._send_email(admin_email, subject, html_content)
    
    def _send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        """
        Envía un email usando SMTP
        
        Args:
            to_email: Destinatario
            subject: Asunto
            html_content: Contenido HTML
            
        Returns:
            bool: True si se envió correctamente
        """
        if not self.is_configured:
            logger.info(f"📧 [SIMULADO] Email a {to_email}: {subject}")
            return True  # Simular envío exitoso si no está configurado
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            
            # Adjuntar contenido HTML
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Conectar y enviar
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_email, msg.as_string())
            
            logger.info(f"Email enviado a {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Error enviando email a {to_email}: {e}")
            return False

    # ===============================================
    # NOTIFICACIONES DE SEGURIDAD (CCTV)
    # ===============================================

    def send_security_alert(
        self, 
        to_email: str, 
        video_data: Dict[str, Any],
        eventos_importantes: list,
        eventos_sospechosos: list = None
    ) -> bool:
        """
        Envía alerta de seguridad cuando se detectan eventos importantes
        
        Args:
            to_email: Email del destinatario (seguridad, admin)
            video_data: Datos del video de seguridad
            eventos_importantes: Lista de eventos clasificados como IMPORTANTES
            eventos_sospechosos: Lista de eventos SOSPECHOSOS (opcional)
        """
        eventos_sospechosos = eventos_sospechosos or []
        total_alertas = len(eventos_importantes) + len(eventos_sospechosos)
        
        # Determinar nivel de urgencia
        if len(eventos_importantes) >= 3:
            urgencia = "🔴 CRÍTICO"
            urgencia_color = "#dc2626"
        elif len(eventos_importantes) >= 1:
            urgencia = "🟠 ALTO"
            urgencia_color = "#ea580c"
        elif len(eventos_sospechosos) >= 3:
            urgencia = "🟡 MEDIO"
            urgencia_color = "#ca8a04"
        else:
            urgencia = "🟢 BAJO"
            urgencia_color = "#16a34a"
        
        subject = f"🚨 ALERTA SEGURIDAD: {len(eventos_importantes)} eventos importantes - {video_data.get('ubicacion', 'Desconocido')}"
        
        # Construir lista de eventos
        eventos_html = ""
        for i, evt in enumerate(eventos_importantes[:5], 1):
            timestamp = evt.get('timestamp_inicio', 0)
            mins, secs = divmod(int(timestamp), 60)
            hours, mins = divmod(mins, 60)
            tiempo_str = f"{hours:02d}:{mins:02d}:{secs:02d}"
            eventos_html += f"""
            <tr style="background: #fef2f2;">
                <td style="padding: 10px; border-bottom: 1px solid #fecaca;">🔴 IMPORTANTE</td>
                <td style="padding: 10px; border-bottom: 1px solid #fecaca;">{tiempo_str}</td>
                <td style="padding: 10px; border-bottom: 1px solid #fecaca;">{evt.get('descripcion_gemini', 'Sin descripción')[:100]}</td>
            </tr>
            """
        
        for i, evt in enumerate(eventos_sospechosos[:3], 1):
            timestamp = evt.get('timestamp_inicio', 0)
            mins, secs = divmod(int(timestamp), 60)
            hours, mins = divmod(mins, 60)
            tiempo_str = f"{hours:02d}:{mins:02d}:{secs:02d}"
            eventos_html += f"""
            <tr style="background: #fefce8;">
                <td style="padding: 10px; border-bottom: 1px solid #fef08a;">🟡 SOSPECHOSO</td>
                <td style="padding: 10px; border-bottom: 1px solid #fef08a;">{tiempo_str}</td>
                <td style="padding: 10px; border-bottom: 1px solid #fef08a;">{evt.get('descripcion_gemini', 'Sin descripción')[:100]}</td>
            </tr>
            """
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #1a1a2e; margin: 0; padding: 20px; }}
                .container {{ max-width: 700px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
                .header {{ background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); color: white; padding: 30px; text-align: center; }}
                .urgencia {{ background: {urgencia_color}; color: white; padding: 15px 30px; border-radius: 25px; display: inline-block; font-weight: bold; font-size: 18px; }}
                .content {{ padding: 30px; }}
                .video-info {{ background: #f1f5f9; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #3b82f6; }}
                .stats {{ display: flex; justify-content: space-around; margin: 20px 0; text-align: center; }}
                .stat-box {{ background: #f8fafc; padding: 15px 25px; border-radius: 8px; }}
                .stat-number {{ font-size: 32px; font-weight: bold; color: #1e293b; }}
                .stat-label {{ color: #64748b; font-size: 12px; }}
                .eventos-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                .eventos-table th {{ background: #1e293b; color: white; padding: 12px; text-align: left; }}
                .btn {{ display: inline-block; background: #E30613; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; margin: 10px 5px; font-weight: bold; }}
                .btn-secondary {{ background: #475569; }}
                .footer {{ background: #1e293b; color: #94a3b8; padding: 20px; text-align: center; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🛡️ TIVIT-CU002 Security</h1>
                    <p>Sistema de Análisis de Video de Seguridad</p>
                    <div class="urgencia">{urgencia}</div>
                </div>
                <div class="content">
                    <h2>⚠️ Se han detectado eventos de seguridad</h2>
                    
                    <div class="video-info">
                        <h3>📹 Información del Video</h3>
                        <p><strong>ID:</strong> {video_data.get('id', 'N/A')}</p>
                        <p><strong>Cámara:</strong> {video_data.get('nombre_camara', 'Sin nombre')}</p>
                        <p><strong>Ubicación:</strong> {video_data.get('ubicacion', 'Desconocida')}</p>
                        <p><strong>Fecha de grabación:</strong> {video_data.get('fecha_grabacion', 'N/A')}</p>
                        <p><strong>Duración:</strong> {self._format_duration_email(video_data.get('duracion_segundos', 0))}</p>
                    </div>
                    
                    <div class="stats">
                        <div class="stat-box">
                            <div class="stat-number" style="color: #dc2626;">{len(eventos_importantes)}</div>
                            <div class="stat-label">IMPORTANTES</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number" style="color: #ca8a04;">{len(eventos_sospechosos)}</div>
                            <div class="stat-label">SOSPECHOSOS</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number" style="color: #3b82f6;">{total_alertas}</div>
                            <div class="stat-label">TOTAL</div>
                        </div>
                    </div>
                    
                    <h3>📋 Detalle de Eventos</h3>
                    <table class="eventos-table">
                        <thead>
                            <tr>
                                <th>Clasificación</th>
                                <th>Timestamp</th>
                                <th>Descripción</th>
                            </tr>
                        </thead>
                        <tbody>
                            {eventos_html if eventos_html else '<tr><td colspan="3" style="padding: 20px; text-align: center;">Sin eventos detectados</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="text-align: center; margin-top: 30px;">
                        <a href="{video_data.get('reporte_url', '#')}" class="btn">📄 Ver Reporte Completo</a>
                        <a href="{video_data.get('video_url', '#')}" class="btn btn-secondary">🎬 Ver Video</a>
                    </div>
                    
                    <p style="margin-top: 30px; color: #64748b; font-size: 12px;">
                        Este análisis fue realizado automáticamente por el sistema TIVIT-CU002 usando 
                        detección de movimiento con OpenCV y clasificación con Gemini Vision AI.
                    </p>
                </div>
                <div class="footer">
                    <p>© {datetime.now().year} TIVIT-CU002 Security - Powered by TIVIT Latam</p>
                    <p>Análisis generado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self._send_email(to_email, subject, html_content)

    def send_security_processing_complete(
        self, 
        to_email: str, 
        video_data: Dict[str, Any],
        estadisticas: Dict[str, Any]
    ) -> bool:
        """
        Envía notificación cuando el procesamiento de video de seguridad finaliza
        
        Args:
            to_email: Email del destinatario
            video_data: Datos del video procesado
            estadisticas: Estadísticas del análisis
        """
        total_eventos = estadisticas.get('eventos_totales', 0)
        importantes = estadisticas.get('eventos_importantes', 0)
        sospechosos = estadisticas.get('eventos_sospechosos', 0)
        normales = estadisticas.get('eventos_normales', 0)
        
        # Determinar resultado
        if importantes > 0:
            resultado = "⚠️ REQUIERE ATENCIÓN"
            resultado_color = "#dc2626"
        elif sospechosos > 0:
            resultado = "🔍 REVISAR"
            resultado_color = "#ca8a04"
        else:
            resultado = "✅ SIN INCIDENTES"
            resultado_color = "#16a34a"
        
        subject = f"📊 Análisis completado: {video_data.get('nombre_camara', 'Video')} - {video_data.get('ubicacion', '')}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 650px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #1e293b 0%, #334155 100%); color: white; padding: 30px; text-align: center; }}
                .resultado {{ background: {resultado_color}; color: white; padding: 12px 24px; border-radius: 20px; display: inline-block; font-weight: bold; }}
                .content {{ padding: 30px; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0; }}
                .stat-card {{ background: #f8fafc; padding: 20px; border-radius: 8px; text-align: center; }}
                .stat-value {{ font-size: 28px; font-weight: bold; }}
                .stat-label {{ color: #64748b; font-size: 13px; margin-top: 5px; }}
                .tiempo {{ background: #e0f2fe; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0; }}
                .footer {{ background: #1e293b; color: #94a3b8; padding: 20px; text-align: center; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🛡️ TIVIT-CU002 Security</h1>
                    <p>Análisis de Video Completado</p>
                    <div class="resultado">{resultado}</div>
                </div>
                <div class="content">
                    <h2>📹 {video_data.get('nombre_camara', 'Video de Seguridad')}</h2>
                    <p><strong>Ubicación:</strong> {video_data.get('ubicacion', 'N/A')}</p>
                    <p><strong>Fecha grabación:</strong> {video_data.get('fecha_grabacion', 'N/A')}</p>
                    
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value" style="color: #3b82f6;">{total_eventos}</div>
                            <div class="stat-label">Eventos Totales</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value" style="color: #dc2626;">{importantes}</div>
                            <div class="stat-label">Importantes</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value" style="color: #ca8a04;">{sospechosos}</div>
                            <div class="stat-label">Sospechosos</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value" style="color: #16a34a;">{normales}</div>
                            <div class="stat-label">Normales</div>
                        </div>
                    </div>
                    
                    <div class="tiempo">
                        <p style="margin: 0;"><strong>⏱️ Tiempo de procesamiento:</strong> {self._format_duration_email(video_data.get('tiempo_procesamiento_segundos', 0))}</p>
                    </div>
                    
                    <p style="text-align: center;">
                        El reporte detallado está disponible en el sistema.
                    </p>
                </div>
                <div class="footer">
                    <p>© {datetime.now().year} TIVIT-CU002 Security</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self._send_email(to_email, subject, html_content)

    def send_security_error(
        self, 
        to_email: str, 
        video_data: Dict[str, Any],
        error_message: str
    ) -> bool:
        """
        Envía notificación cuando hay un error en el procesamiento
        
        Args:
            to_email: Email del destinatario
            video_data: Datos del video
            error_message: Mensaje de error
        """
        subject = f"❌ Error en procesamiento: {video_data.get('id', 'Video')}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; }}
                .header {{ background: #dc2626; color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 30px; }}
                .error-box {{ background: #fef2f2; border: 1px solid #fecaca; border-left: 4px solid #dc2626; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .video-info {{ background: #f8fafc; padding: 15px; border-radius: 8px; margin: 15px 0; }}
                .footer {{ background: #1e293b; color: #94a3b8; padding: 20px; text-align: center; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>❌ Error de Procesamiento</h1>
                    <p>TIVIT-CU002 Security</p>
                </div>
                <div class="content">
                    <h2>Ha ocurrido un error</h2>
                    
                    <div class="video-info">
                        <p><strong>Video ID:</strong> {video_data.get('id', 'N/A')}</p>
                        <p><strong>Cámara:</strong> {video_data.get('nombre_camara', 'N/A')}</p>
                        <p><strong>Ubicación:</strong> {video_data.get('ubicacion', 'N/A')}</p>
                    </div>
                    
                    <div class="error-box">
                        <h3>🔴 Detalle del error:</h3>
                        <code style="word-break: break-all;">{error_message}</code>
                    </div>
                    
                    <p>Por favor, revise los logs del sistema para más información.</p>
                </div>
                <div class="footer">
                    <p>© {datetime.now().year} TIVIT-CU002 Security</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self._send_email(to_email, subject, html_content)

    def _format_duration_email(self, seconds: float) -> str:
        """Formatea duración para emails"""
        if not seconds:
            return "N/A"
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"


# Instancia singleton del servicio
_notification_service = None

def get_notification_service() -> NotificationService:
    """Obtiene la instancia singleton del servicio de notificaciones"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
