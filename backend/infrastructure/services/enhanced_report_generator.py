"""
Generador de Reportes Mejorado para Videos de Seguridad
Incluye: Imágenes con bounding boxes, thumbnails, detecciones de Video Intelligence
"""

import logging
import os
import tempfile
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class EnhancedReportGenerator:
    """
    Generador de reportes profesionales con soporte de imágenes
    
    Funcionalidades:
    - Incluir frames con bounding boxes
    - Thumbnails de eventos
    - Detecciones de Video Intelligence (caras, personas, objetos)
    - Estadísticas visuales
    """
    
    def __init__(self):
        """Inicializa el generador"""
        self._reportlab_available = self._check_reportlab()
        self._cv2_available = self._check_opencv()
        self._pil_available = self._check_pillow()
    
    def _check_reportlab(self) -> bool:
        try:
            from reportlab.lib.pagesizes import letter
            return True
        except ImportError:
            logger.warning("⚠️ ReportLab no disponible")
            return False
    
    def _check_opencv(self) -> bool:
        try:
            import cv2
            return True
        except ImportError:
            logger.warning("⚠️ OpenCV no disponible para anotaciones")
            return False
    
    def _check_pillow(self) -> bool:
        try:
            from PIL import Image
            return True
        except ImportError:
            logger.warning("⚠️ Pillow no disponible")
            return False
    
    def save_text_report(self, video, eventos, output_path: str) -> bool:
        """
        Genera reporte en formato TXT (compatibilidad con ReportGenerator básico)
        
        Args:
            video: Objeto SecurityVideo o dict con datos del video
            eventos: Lista de eventos (objetos EventoSeguridad o dicts)
            output_path: Ruta donde guardar el archivo TXT
        
        Returns:
            True si se guardó correctamente
        """
        try:
            lines = []
            
            # Header
            lines.append("=" * 80)
            lines.append("       REPORTE DE ANÁLISIS DE CÁMARA DE SEGURIDAD")
            lines.append("                Sistema TIVIT-CU002 Security v2.0")
            lines.append("=" * 80)
            lines.append("")
            
            # Obtener datos del video (puede ser objeto o dict)
            if hasattr(video, 'id'):
                video_id = video.id
                nombre_camara = video.nombre_camara
                ubicacion = video.ubicacion
                fecha_grabacion = video.fecha_grabacion
                duracion_segundos = video.duracion_segundos
            else:
                video_id = video.get('id', 'N/A')
                nombre_camara = video.get('nombre_camara', 'N/A')
                ubicacion = video.get('ubicacion', 'N/A')
                fecha_grabacion = video.get('fecha_grabacion', 'N/A')
                duracion_segundos = video.get('duracion_segundos', 0)
            
            # Información General
            lines.append("=" * 80)
            lines.append("1. INFORMACIÓN DEL VIDEO")
            lines.append("=" * 80)
            lines.append("")
            lines.append(f"ID del Video:            {video_id}")
            lines.append(f"Nombre de cámara:        {nombre_camara}")
            lines.append(f"Ubicación:               {ubicacion}")
            lines.append(f"Fecha de grabación:      {fecha_grabacion}")
            lines.append(f"Duración total:          {self._format_duration(duracion_segundos)}")
            lines.append("")
            
            # Resumen de eventos
            lines.append("=" * 80)
            lines.append("2. RESUMEN DE EVENTOS")
            lines.append("=" * 80)
            lines.append("")
            
            # Clasificar eventos
            importantes = []
            sospechosos = []
            normales = []
            
            for evt in eventos:
                if hasattr(evt, 'clasificacion'):
                    clasificacion = evt.clasificacion.value if hasattr(evt.clasificacion, 'value') else str(evt.clasificacion)
                else:
                    clasificacion = evt.get('clasificacion', 'normal')
                
                clasificacion = str(clasificacion).upper()
                
                if 'IMPORTANTE' in clasificacion:
                    importantes.append(evt)
                elif 'SOSPECHOSO' in clasificacion:
                    sospechosos.append(evt)
                else:
                    normales.append(evt)
            
            lines.append(f"├─ EVENTOS IMPORTANTES:      {len(importantes)} eventos   {'⚠️  REQUIERE ATENCIÓN' if importantes else ''}")
            lines.append(f"├─ EVENTOS SOSPECHOSOS:      {len(sospechosos)} eventos   {'⚡ REVISAR' if sospechosos else ''}")
            lines.append(f"└─ ACTIVIDAD NORMAL:         {len(normales)} eventos   ✅ Sin riesgo")
            lines.append("")
            
            # Timeline de eventos
            lines.append("=" * 80)
            lines.append("3. TIMELINE DE DETECCIONES")
            lines.append("=" * 80)
            lines.append("")
            
            for i, evt in enumerate(eventos, 1):
                if hasattr(evt, 'timestamp_inicio'):
                    ts_inicio = evt.timestamp_inicio
                    ts_fin = evt.timestamp_fin
                    descripcion = evt.descripcion_gemini or 'Sin descripción'
                else:
                    ts_inicio = evt.get('timestamp_inicio', 0)
                    ts_fin = evt.get('timestamp_fin', 0)
                    descripcion = evt.get('descripcion_gemini', 'Sin descripción')
                
                tiempo = self._format_timestamp(ts_inicio)
                lines.append(f"[{i:03d}] {tiempo} - {descripcion[:60]}")
            
            lines.append("")
            
            # Footer
            lines.append("=" * 80)
            lines.append("Reporte generado automáticamente por TIVIT-CU002")
            lines.append("Sistema de Análisis Inteligente de Videos v2.0")
            lines.append(f"Fecha de generación: {datetime.utcnow().isoformat()}")
            lines.append("=" * 80)
            
            # Guardar archivo
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines))
            
            logger.info(f"✅ Reporte TXT guardado: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando reporte TXT: {e}")
            return False
    
    def draw_bounding_boxes(
        self,
        image_path: str,
        detections: List[Dict[str, Any]],
        output_path: str = None
    ) -> Optional[str]:
        """
        Dibuja bounding boxes sobre una imagen
        
        Args:
            image_path: Ruta a la imagen original
            detections: Lista de detecciones con formato:
                {
                    "type": "person" | "face" | "object",
                    "box": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
                    "confidence": 0.95,
                    "label": "Persona #1"
                }
            output_path: Ruta de salida (opcional)
        
        Returns:
            Ruta a la imagen con anotaciones
        """
        if not self._cv2_available:
            return None
        
        import cv2
        import numpy as np
        
        try:
            # Leer imagen
            img = cv2.imread(image_path)
            if img is None:
                logger.error(f"No se pudo leer imagen: {image_path}")
                return None
            
            h, w = img.shape[:2]
            
            # Colores por tipo de detección
            colors = {
                "person": (0, 255, 0),      # Verde
                "face": (255, 0, 0),         # Azul
                "object": (0, 165, 255),     # Naranja
                "vehicle": (255, 255, 0),    # Cyan
                "suspicious": (0, 0, 255),   # Rojo
            }
            
            for det in detections:
                det_type = det.get("type", "object")
                box = det.get("box", {})
                confidence = det.get("confidence", 0)
                label = det.get("label", det_type)
                
                # Convertir coordenadas normalizadas a píxeles
                x1 = int(box.get("x", 0) * w)
                y1 = int(box.get("y", 0) * h)
                x2 = int((box.get("x", 0) + box.get("width", 0)) * w)
                y2 = int((box.get("y", 0) + box.get("height", 0)) * h)
                
                color = colors.get(det_type, (0, 255, 0))
                
                # Dibujar rectángulo
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
                
                # Etiqueta con fondo
                label_text = f"{label} ({confidence*100:.0f}%)"
                (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(img, (x1, y1 - th - 10), (x1 + tw + 10, y1), color, -1)
                cv2.putText(img, label_text, (x1 + 5, y1 - 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Guardar imagen
            if output_path is None:
                output_path = tempfile.NamedTemporaryFile(
                    suffix=".jpg", delete=False
                ).name
            
            cv2.imwrite(output_path, img)
            return output_path
        
        except Exception as e:
            logger.error(f"Error dibujando bounding boxes: {e}")
            return None
    
    def generate_enhanced_pdf(
        self,
        video_data: Dict[str, Any],
        eventos: List[Dict[str, Any]],
        output_path: str,
        frame_images: List[str] = None
    ) -> bool:
        """
        Genera reporte PDF mejorado con imágenes
        
        Args:
            video_data: Datos del video
            eventos: Lista de eventos con detecciones
            output_path: Ruta de salida del PDF
            frame_images: Lista de rutas a imágenes de frames
        """
        if not self._reportlab_available:
            logger.error("ReportLab no disponible")
            return False
        
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch, cm
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, PageBreak, 
                Table, TableStyle, Image as RLImage, KeepTogether
            )
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
            from reportlab.graphics.shapes import Drawing, Rect
            from reportlab.graphics.charts.piecharts import Pie
            
            # Crear documento
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            doc = SimpleDocTemplate(
                output_path, 
                pagesize=A4,
                rightMargin=1.5*cm,
                leftMargin=1.5*cm,
                topMargin=2*cm,
                bottomMargin=2*cm
            )
            
            story = []
            styles = getSampleStyleSheet()
            
            # Estilos personalizados
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=22,
                textColor=colors.HexColor('#1a365d'),
                spaceAfter=20,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            
            subtitle_style = ParagraphStyle(
                'Subtitle',
                parent=styles['Normal'],
                fontSize=12,
                textColor=colors.HexColor('#4a5568'),
                alignment=TA_CENTER,
                spaceAfter=30
            )
            
            section_style = ParagraphStyle(
                'Section',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=colors.HexColor('#2d3748'),
                spaceBefore=20,
                spaceAfter=10,
                fontName='Helvetica-Bold'
            )
            
            alert_style = ParagraphStyle(
                'Alert',
                parent=styles['Normal'],
                fontSize=11,
                textColor=colors.HexColor('#c53030'),
                backColor=colors.HexColor('#fed7d7'),
                borderPadding=10,
                spaceBefore=10,
                spaceAfter=10
            )
            
            # ==================== HEADER ====================
            story.append(Paragraph("🔒 REPORTE DE ANÁLISIS DE SEGURIDAD", title_style))
            story.append(Paragraph("Sistema TIVIT-CU002 Security Intelligence v2.0", subtitle_style))
            story.append(Spacer(1, 0.3 * inch))
            
            # ==================== INFO DEL VIDEO ====================
            story.append(Paragraph("📹 INFORMACIÓN DEL VIDEO", section_style))
            
            video_info = [
                ['Campo', 'Valor'],
                ['ID del Video', video_data.get('id', 'N/A')],
                ['Cámara', video_data.get('nombre_camara', 'N/A')],
                ['Ubicación', video_data.get('ubicacion', 'N/A')],
                ['Fecha de Grabación', video_data.get('fecha_grabacion', 'N/A')],
                ['Duración', self._format_duration(video_data.get('duracion_segundos', 0))],
                ['Resolución', f"{video_data.get('width', 'N/A')}x{video_data.get('height', 'N/A')}"],
                ['Tiempo de Análisis', self._format_duration(video_data.get('tiempo_procesamiento', 0))],
            ]
            
            video_table = Table(video_info, colWidths=[5*cm, 10*cm])
            video_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#edf2f7')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0'))
            ]))
            story.append(video_table)
            story.append(Spacer(1, 0.3 * inch))
            
            # ==================== RESUMEN EJECUTIVO ====================
            story.append(Paragraph("📊 RESUMEN EJECUTIVO", section_style))
            
            # Contar eventos por tipo
            eventos_importantes = [e for e in eventos if e.get('clasificacion') == 'IMPORTANTE']
            eventos_sospechosos = [e for e in eventos if e.get('clasificacion') == 'SOSPECHOSO']
            eventos_normales = [e for e in eventos if e.get('clasificacion') == 'NORMAL']
            
            # Alerta si hay eventos importantes
            if eventos_importantes:
                story.append(Paragraph(
                    f"⚠️ ALERTA: Se detectaron {len(eventos_importantes)} eventos IMPORTANTES que requieren atención inmediata.",
                    alert_style
                ))
            
            # Tabla de resumen
            summary_data = [
                ['Clasificación', 'Cantidad', 'Porcentaje', 'Estado'],
                ['🔴 IMPORTANTES', str(len(eventos_importantes)), 
                 f"{len(eventos_importantes)/max(len(eventos),1)*100:.1f}%", 'REQUIERE ACCIÓN'],
                ['🟡 SOSPECHOSOS', str(len(eventos_sospechosos)), 
                 f"{len(eventos_sospechosos)/max(len(eventos),1)*100:.1f}%", 'REVISAR'],
                ['🟢 NORMALES', str(len(eventos_normales)), 
                 f"{len(eventos_normales)/max(len(eventos),1)*100:.1f}%", 'OK'],
                ['TOTAL', str(len(eventos)), '100%', '-'],
            ]
            
            summary_table = Table(summary_data, colWidths=[4*cm, 3*cm, 3*cm, 5*cm])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3182ce')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#fed7d7')),
                ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#fefcbf')),
                ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#c6f6d5')),
                ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#e2e8f0')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#a0aec0'))
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 0.3 * inch))
            
            # ==================== TIMELINE VISUAL DE DETECCIONES ====================
            story.append(Paragraph("⏱️ TIMELINE DE DETECCIONES", section_style))
            story.append(Paragraph(
                "Momentos exactos donde se detectó actividad en el video:",
                styles['Normal']
            ))
            story.append(Spacer(1, 0.1 * inch))
            
            # Ordenar eventos por timestamp
            eventos_ordenados = sorted(eventos, key=lambda x: x.get('timestamp_inicio', 0))
            
            # Crear tabla de timeline
            timeline_data = [['Tiempo', 'Duración', 'Tipo', 'Descripción']]
            for evt in eventos_ordenados:
                tiempo = self._format_timestamp(evt.get('timestamp_inicio', 0))
                duracion = f"{evt.get('duracion', 0):.1f}s"
                clasificacion = evt.get('clasificacion', 'NORMAL')
                
                # Emoji según clasificación
                emoji_map = {'IMPORTANTE': '🔴', 'SOSPECHOSO': '🟡', 'NORMAL': '🟢'}
                emoji = emoji_map.get(clasificacion, '⚪')
                
                # Descripción truncada
                desc = evt.get('descripcion_gemini', 'Sin descripción')[:60]
                if len(evt.get('descripcion_gemini', '')) > 60:
                    desc += '...'
                
                timeline_data.append([tiempo, duracion, f"{emoji} {clasificacion}", desc])
            
            # Solo mostrar hasta 20 eventos en el timeline para no saturar
            if len(timeline_data) > 21:
                timeline_data = timeline_data[:21]
                timeline_data.append(['...', '...', '...', f'(+{len(eventos) - 20} eventos más)'])
            
            timeline_table = Table(timeline_data, colWidths=[2.5*cm, 2*cm, 3.5*cm, 7*cm])
            timeline_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (2, -1), 'CENTER'),
                ('ALIGN', (3, 0), (3, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0'))
            ]))
            story.append(timeline_table)
            story.append(Spacer(1, 0.3 * inch))
            
            # ==================== ESTADÍSTICAS DE ACTIVIDAD ====================
            story.append(Paragraph("📈 ANÁLISIS Y ESTADÍSTICAS", section_style))
            
            # Calcular estadísticas
            duracion_total_video = video_data.get('duracion_segundos', 0)
            duracion_movimiento = sum(e.get('duracion', 0) for e in eventos)
            porcentaje_actividad = (duracion_movimiento / max(duracion_total_video, 1)) * 100
            
            # Hora pico (buscar el minuto con más actividad)
            if eventos:
                minutos_actividad = {}
                for e in eventos:
                    minuto = int(e.get('timestamp_inicio', 0) // 60)
                    minutos_actividad[minuto] = minutos_actividad.get(minuto, 0) + 1
                
                minuto_pico = max(minutos_actividad, key=minutos_actividad.get) if minutos_actividad else 0
                eventos_en_pico = minutos_actividad.get(minuto_pico, 0)
                hora_pico_str = f"Minuto {minuto_pico:02d} ({eventos_en_pico} eventos)"
            else:
                hora_pico_str = "N/A"
            
            # Confianza promedio
            confianzas = [e.get('confianza', 0) for e in eventos if e.get('confianza')]
            confianza_promedio = sum(confianzas) / len(confianzas) * 100 if confianzas else 0
            
            stats_data = [
                ['Métrica', 'Valor', 'Interpretación'],
                ['Total de Detecciones', str(len(eventos)), 'Segmentos con movimiento detectado'],
                ['Duración con Movimiento', self._format_duration(duracion_movimiento), f'{porcentaje_actividad:.1f}% del video total'],
                ['Momento de Mayor Actividad', hora_pico_str, 'Concentración de eventos'],
                ['Confianza Promedio IA', f'{confianza_promedio:.1f}%', 'Certeza del análisis'],
                ['Eventos por Revisar', str(len(eventos_importantes) + len(eventos_sospechosos)), 'IMPORTANTES + SOSPECHOSOS'],
            ]
            
            stats_table = Table(stats_data, colWidths=[5*cm, 4*cm, 6*cm])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2b6cb0')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#ebf8ff')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 1), (1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bee3f8'))
            ]))
            story.append(stats_table)
            story.append(Spacer(1, 0.4 * inch))
            
            # ==================== GALERÍA DE CAPTURAS ====================
            # Recopilar frames disponibles
            frames_disponibles = [e.get('frame_path') for e in eventos if e.get('frame_path') and os.path.exists(e.get('frame_path', ''))]
            
            if frames_disponibles:
                story.append(PageBreak())
                story.append(Paragraph("🖼️ GALERÍA DE CAPTURAS DETECTADAS", section_style))
                story.append(Paragraph(
                    f"Se capturaron {len(frames_disponibles)} imágenes de los momentos de detección:",
                    styles['Normal']
                ))
                story.append(Spacer(1, 0.2 * inch))
                
                # Mostrar hasta 6 imágenes (2 columnas x 3 filas)
                max_images = min(6, len(frames_disponibles))
                for i in range(0, max_images, 2):
                    row_images = []
                    for j in range(2):
                        if i + j < max_images:
                            frame_path = frames_disponibles[i + j]
                            try:
                                img = RLImage(frame_path, width=7.5*cm, height=4.5*cm)
                                # Encontrar el evento correspondiente
                                evento_img = next((e for e in eventos if e.get('frame_path') == frame_path), None)
                                if evento_img:
                                    timestamp = self._format_timestamp(evento_img.get('timestamp_inicio', 0))
                                    clasificacion = evento_img.get('clasificacion', 'N/A')
                                    caption = Paragraph(f"<b>{timestamp}</b> - {clasificacion}", 
                                                      ParagraphStyle('Caption', fontSize=8, alignment=TA_CENTER))
                                    row_images.append([img, caption])
                                else:
                                    row_images.append([img, Paragraph("", styles['Normal'])])
                            except Exception as e:
                                logger.warning(f"No se pudo cargar imagen {frame_path}: {e}")
                    
                    if row_images:
                        # Crear tabla para las imágenes en fila
                        img_row = []
                        for item in row_images:
                            img_row.append(item[0])
                        
                        img_table = Table([img_row], colWidths=[8*cm] * len(img_row))
                        img_table.setStyle(TableStyle([
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ]))
                        story.append(img_table)
                        
                        # Captions
                        caption_row = [item[1] for item in row_images]
                        caption_table = Table([caption_row], colWidths=[8*cm] * len(caption_row))
                        story.append(caption_table)
                        story.append(Spacer(1, 0.2 * inch))
                
                if len(frames_disponibles) > 6:
                    story.append(Paragraph(
                        f"<i>(+{len(frames_disponibles) - 6} imágenes adicionales disponibles en el sistema)</i>",
                        ParagraphStyle('Note', fontSize=9, textColor=colors.gray, alignment=TA_CENTER)
                    ))
            
            # ==================== EVENTOS IMPORTANTES CON IMÁGENES ====================
            if eventos_importantes:
                story.append(PageBreak())
                story.append(Paragraph("🚨 EVENTOS IMPORTANTES - DETALLE", section_style))
                
                for i, evento in enumerate(eventos_importantes, 1):
                    elements = []
                    
                    # Título del evento
                    elements.append(Paragraph(
                        f"<b>EVENTO #{i:03d}</b> - {self._format_timestamp(evento.get('timestamp_inicio', 0))}",
                        styles['Heading3']
                    ))
                    
                    # Imagen del frame (si existe)
                    frame_path = evento.get('frame_path')
                    if frame_path and os.path.exists(frame_path):
                        try:
                            # Procesar imagen con bounding boxes si hay detecciones
                            detections = evento.get('detections', [])
                            if detections and self._cv2_available:
                                annotated_path = self.draw_bounding_boxes(
                                    frame_path, detections
                                )
                                if annotated_path:
                                    frame_path = annotated_path
                            
                            img = RLImage(frame_path, width=14*cm, height=8*cm)
                            elements.append(img)
                            elements.append(Spacer(1, 0.1 * inch))
                        except Exception as e:
                            logger.warning(f"No se pudo incluir imagen: {e}")
                    
                    # Información del evento
                    evento_info = [
                        ['Timestamp', f"{self._format_timestamp(evento.get('timestamp_inicio', 0))} - {self._format_timestamp(evento.get('timestamp_fin', 0))}"],
                        ['Duración', f"{evento.get('duracion', 0):.1f} segundos"],
                        ['Confianza IA', f"{evento.get('confianza', 0)*100:.1f}%"],
                    ]
                    
                    info_table = Table(evento_info, colWidths=[4*cm, 11*cm])
                    info_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#edf2f7')),
                        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0'))
                    ]))
                    elements.append(info_table)
                    elements.append(Spacer(1, 0.1 * inch))
                    
                    # Descripción de la IA
                    elements.append(Paragraph(
                        f"<b>Descripción:</b> {evento.get('descripcion_gemini', 'Sin descripción')}",
                        styles['Normal']
                    ))
                    
                    # Detecciones de Video Intelligence
                    deep_analysis = evento.get('analisis_profundo', {})
                    if deep_analysis:
                        elements.append(Spacer(1, 0.1 * inch))
                        elements.append(Paragraph("<b>Análisis Profundo (Video Intelligence):</b>", styles['Normal']))
                        
                        if 'persons_detected' in deep_analysis:
                            elements.append(Paragraph(
                                f"• Personas detectadas: {deep_analysis['persons_detected']}",
                                styles['Normal']
                            ))
                        if 'faces_detected' in deep_analysis:
                            elements.append(Paragraph(
                                f"• Rostros detectados: {deep_analysis['faces_detected']}",
                                styles['Normal']
                            ))
                        if 'objects' in deep_analysis:
                            objects_str = ", ".join(deep_analysis['objects'][:5])
                            elements.append(Paragraph(
                                f"• Objetos: {objects_str}",
                                styles['Normal']
                            ))
                        if 'labels' in deep_analysis:
                            labels_str = ", ".join(deep_analysis['labels'][:5])
                            elements.append(Paragraph(
                                f"• Etiquetas: {labels_str}",
                                styles['Normal']
                            ))
                    
                    elements.append(Spacer(1, 0.2 * inch))
                    
                    # Mantener elementos juntos
                    story.append(KeepTogether(elements))
            
            # ==================== EVENTOS SOSPECHOSOS ====================
            if eventos_sospechosos:
                story.append(PageBreak())
                story.append(Paragraph("⚡ EVENTOS SOSPECHOSOS", section_style))
                
                sosp_data = [['#', 'Timestamp', 'Duración', 'Descripción']]
                for i, evento in enumerate(eventos_sospechosos, 1):
                    sosp_data.append([
                        f"{i:03d}",
                        self._format_timestamp(evento.get('timestamp_inicio', 0)),
                        f"{evento.get('duracion', 0):.1f}s",
                        evento.get('descripcion_gemini', '')[:50] + "..."
                    ])
                
                sosp_table = Table(sosp_data, colWidths=[1.5*cm, 3*cm, 2.5*cm, 8*cm])
                sosp_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecc94b')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fffff0')]),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d69e2e'))
                ]))
                story.append(sosp_table)
            
            # ==================== FOOTER ====================
            story.append(Spacer(1, 0.5 * inch))
            story.append(Paragraph(
                f"Reporte generado: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.gray)
            ))
            story.append(Paragraph(
                "Sistema TIVIT-CU002 Security Intelligence • Powered by Google Cloud AI",
                ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.gray)
            ))
            
            # Generar PDF
            doc.build(story)
            logger.info(f"✅ Reporte PDF mejorado generado: {output_path}")
            return True
        
        except Exception as e:
            logger.error(f"❌ Error generando PDF mejorado: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _format_duration(self, seconds: float) -> str:
        """Formatea duración"""
        if not seconds:
            return "N/A"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours}h {minutes}min {secs}s"
        elif minutes > 0:
            return f"{minutes}min {secs}s"
        return f"{secs}s"
    
    def _format_timestamp(self, seconds: float) -> str:
        """Formatea timestamp"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def generate_contextual_report(
        self,
        analysis_data: Dict[str, Any],
        formato: str = "pdf"
    ) -> str:
        """
        Genera reporte para análisis contextual
        
        Args:
            analysis_data: Datos del análisis contextual
            formato: "pdf", "json", "txt"
            
        Returns:
            Ruta al archivo generado
        """
        import json
        output_dir = os.path.join(tempfile.gettempdir(), "security_reports")
        os.makedirs(output_dir, exist_ok=True)
        
        analysis_id = analysis_data.get("id", "unknown")
        resultado = analysis_data.get("resultado", {})
        
        if formato == "json":
            # JSON simple
            output_path = os.path.join(output_dir, f"reporte_{analysis_id[:8]}.json")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(analysis_data, f, ensure_ascii=False, indent=2)
            return output_path
        
        elif formato == "txt":
            # Reporte TXT
            output_path = os.path.join(output_dir, f"reporte_{analysis_id[:8]}.txt")
            
            lines = [
                "=" * 70,
                "     REPORTE DE ANÁLISIS CONTEXTUAL DE SEGURIDAD",
                "=" * 70,
                "",
                f"🎯 CONSULTA: {analysis_data.get('contexto', 'N/A')}",
                "",
                "─" * 70,
                "📋 RESPUESTA",
                "─" * 70,
                resultado.get("respuesta_consulta", "Sin respuesta"),
                "",
                "─" * 70,
                "📊 ESTADÍSTICAS",
                "─" * 70,
            ]
            
            stats = resultado.get("estadisticas", {})
            lines.extend([
                f"• Movimientos detectados: {stats.get('total_movimientos', 0)}",
                f"• Relevantes para consulta: {stats.get('relevantes_contexto', 0)}",
                f"• Porcentaje de relevancia: {stats.get('porcentaje_relevancia', 0)}%",
                f"• Modo de análisis: {stats.get('modo_analisis', 'ESTANDAR')}",
                "",
            ])
            
            # Timeline
            timeline = resultado.get("timeline", [])
            if timeline:
                lines.extend([
                    "─" * 70,
                    "⏱️ TIMELINE DE EVENTOS",
                    "─" * 70,
                ])
                for i, evento in enumerate(timeline, 1):
                    ts = evento.get("timestamp_formatted", "??:??:??")
                    analisis = evento.get("analisis", {})
                    desc = analisis.get("descripcion_escena", "Sin descripción")[:100]
                    lines.append(f"{i}. [{ts}] {desc}")
                lines.append("")
            
            # Análisis profundo
            profundo = resultado.get("analisis_profundo", {})
            if profundo and not profundo.get("error"):
                lines.extend([
                    "─" * 70,
                    "🔬 ANÁLISIS PROFUNDO (Video Intelligence)",
                    "─" * 70,
                    f"• Personas detectadas: {profundo.get('personas', {}).get('total', 0)}",
                    f"• Rostros detectados: {profundo.get('rostros', {}).get('total', 0)}",
                    f"• Etiquetas: {', '.join(profundo.get('etiquetas', [])[:10])}",
                    "",
                ])
            
            lines.extend([
                "=" * 70,
                f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 70,
            ])
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            
            return output_path
        
        else:
            # PDF
            output_path = os.path.join(output_dir, f"reporte_{analysis_id[:8]}.pdf")
            
            # Construir datos para el PDF mejorado
            video_data = resultado.get("video_info", {})
            video_data["estadisticas"] = resultado.get("estadisticas", {})
            video_data["contexto_usuario"] = analysis_data.get("contexto", "")
            video_data["respuesta_consulta"] = resultado.get("respuesta_consulta", "")
            video_data["analisis_profundo"] = resultado.get("analisis_profundo")
            
            # Convertir timeline a eventos
            eventos = []
            for ev in resultado.get("timeline", []):
                eventos.append({
                    "timestamp_inicio": ev.get("timestamp_inicio", 0),
                    "timestamp_fin": ev.get("timestamp_fin", 0),
                    "clasificacion": ev.get("analisis", {}).get("clasificacion", "NORMAL"),
                    "descripcion_gemini": ev.get("analisis", {}).get("descripcion_escena", ""),
                    "frame_path": ev.get("frame_path")
                })
            
            # Recopilar imágenes
            frame_images = [e.get("frame_path") for e in eventos if e.get("frame_path")]
            
            self.generate_enhanced_pdf(video_data, eventos, output_path, frame_images)
            return output_path
