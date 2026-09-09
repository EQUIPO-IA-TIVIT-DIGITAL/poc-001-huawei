"""
Generador de Reportes Profesionales para Videos de Seguridad v3.0

Genera reportes con:
- Resumen ejecutivo con análisis cruzado
- Clasificación de riesgo global y por evento
- Imágenes HD de frames clave (descargadas desde GCS)
- Patrones detectados y recomendaciones de seguridad
- Formato TXT completo y PDF profesional con imágenes
"""

import logging
import os
import tempfile
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from domain.entities import SecurityVideo, EventoSeguridad

logger = logging.getLogger(__name__)


# Colores para niveles de riesgo
RISK_COLORS = {
    'BAJO': '#22c55e',      # Verde
    'MEDIO': '#f59e0b',     # Amarillo/Naranja
    'ALTO': '#ef4444',      # Rojo
    'CRITICO': '#7c2d12',   # Rojo oscuro
}

RISK_LABELS = {
    'BAJO': '🟢 BAJO',
    'MEDIO': '🟡 MEDIO',
    'ALTO': '🔴 ALTO',
    'CRITICO': '⚫ CRÍTICO',
}


class ReportGenerator:
    """
    Generador de reportes profesionales v3.0
    
    Genera TXT y PDF con:
    - Análisis cruzado y patrones
    - Clasificación de riesgo
    - Imágenes de frames clave
    - Recomendaciones de seguridad
    """
    
    def __init__(self):
        """Inicializa el generador"""
        self._reportlab_available = self._check_reportlab()
    
    def _check_reportlab(self) -> bool:
        """Verifica si ReportLab está disponible"""
        try:
            from reportlab.lib.pagesizes import letter
            return True
        except ImportError:
            logger.warning("⚠️ ReportLab no disponible. Instala con: pip install reportlab")
            return False
    
    # ═══════════════════════════════════════════════════════════════
    # REPORTE TXT
    # ═══════════════════════════════════════════════════════════════
    
    def generate_text_report(
        self,
        video: SecurityVideo,
        eventos: List[EventoSeguridad],
        cross_analysis: Dict[str, Any] = None
    ) -> str:
        """
        Genera reporte completo en formato TXT
        
        Args:
            video: Video de seguridad
            eventos: Lista de eventos detectados
            cross_analysis: Análisis cruzado (opcional)
        """
        cross_analysis = cross_analysis or {}
        lines = []
        
        # ═══ HEADER ═══
        lines.append("=" * 90)
        lines.append("       REPORTE DE ANÁLISIS DE CÁMARA DE SEGURIDAD")
        lines.append("       Sistema TIVIT-CU002 Security v3.0")
        lines.append("       Pipeline: Clips de Video + Gemini 2.5 Flash")
        lines.append("=" * 90)
        lines.append("")
        
        # ═══ NIVEL DE RIESGO GLOBAL ═══
        nivel_riesgo = cross_analysis.get('nivel_riesgo_global', 'BAJO')
        risk_label = RISK_LABELS.get(nivel_riesgo, nivel_riesgo)
        lines.append(f"  ╔══════════════════════════════════════════════╗")
        lines.append(f"  ║  NIVEL DE RIESGO GLOBAL: {risk_label:<20s}  ║")
        lines.append(f"  ╚══════════════════════════════════════════════╝")
        lines.append("")
        
        # ═══ 1. INFORMACIÓN DEL VIDEO ═══
        lines.append("=" * 90)
        lines.append("1. INFORMACIÓN DEL VIDEO")
        lines.append("=" * 90)
        lines.append("")
        lines.append(f"  ID del Video:            {video.id}")
        lines.append(f"  Nombre de cámara:        {video.nombre_camara}")
        lines.append(f"  Ubicación:               {video.ubicacion}")
        lines.append(f"  Fecha de grabación:      {video.fecha_grabacion}")
        lines.append(f"  Duración total:          {self._format_duration(video.duracion_segundos)}")
        lines.append("")
        
        # Metadata técnico
        if video.metadata_tecnico:
            lines.append("  ESPECIFICACIONES TÉCNICAS:")
            lines.append("  " + "-" * 50)
            mt = video.metadata_tecnico
            if mt.get("width") and mt.get("height"):
                lines.append(f"  Resolución:              {mt['width']}x{mt['height']}")
            if mt.get("fps"):
                lines.append(f"  FPS:                     {mt['fps']:.1f} frames/segundo")
            if mt.get("codec"):
                lines.append(f"  Codec:                   {mt['codec']}")
            if mt.get("size_bytes"):
                size_mb = mt['size_bytes'] / (1024 * 1024)
                lines.append(f"  Tamaño archivo:          {size_mb:.1f} MB")
            lines.append("")
        
        # Procesamiento
        lines.append("  PROCESAMIENTO:")
        lines.append("  " + "-" * 50)
        if video.fecha_procesamiento:
            lines.append(f"  Fecha de análisis:       {video.fecha_procesamiento}")
        if video.tiempo_procesamiento_segundos:
            lines.append(f"  Tiempo procesamiento:    {self._format_duration(video.tiempo_procesamiento_segundos)}")
        lines.append(f"  Pipeline:                v3.0 (Video Clips + Gemini)")
        lines.append("")
        
        # ═══ 2. RESUMEN EJECUTIVO ═══
        lines.append("=" * 90)
        lines.append("2. RESUMEN EJECUTIVO")
        lines.append("=" * 90)
        lines.append("")
        
        resumen = cross_analysis.get('resumen_ejecutivo', '')
        if resumen:
            # Wrap text at 85 chars
            for paragraph in resumen.split('\n'):
                words = paragraph.split()
                current_line = "  "
                for word in words:
                    if len(current_line) + len(word) + 1 > 85:
                        lines.append(current_line)
                        current_line = "  " + word
                    else:
                        current_line += " " + word if len(current_line) > 2 else word
                if current_line.strip():
                    lines.append(current_line)
            lines.append("")
        
        # Distribución de riesgo
        stats = video.estadisticas or {}
        riesgos = stats.get('eventos_por_riesgo', {})
        
        lines.append("  DISTRIBUCIÓN DE EVENTOS POR RIESGO:")
        lines.append("  " + "-" * 50)
        lines.append(f"  ├─ 🟢 BAJO:     {riesgos.get('BAJO', 0)} eventos")
        lines.append(f"  ├─ 🟡 MEDIO:    {riesgos.get('MEDIO', 0)} eventos")
        lines.append(f"  ├─ 🔴 ALTO:     {riesgos.get('ALTO', 0)} eventos")
        lines.append(f"  ├─ ⚫ CRÍTICO:  {riesgos.get('CRITICO', 0)} eventos")
        lines.append(f"  └─ TOTAL:        {len(eventos)} eventos analizados")
        lines.append("")
        
        # Contadores globales
        eventos_con_personas = [e for e in eventos if e.personas_count > 0]
        eventos_con_vehiculos = [e for e in eventos if e.vehiculos_count > 0]
        
        lines.append("  DETECCIONES GLOBALES:")
        lines.append("  " + "-" * 50)
        lines.append(f"  ├─ Eventos con personas:   {len(eventos_con_personas)}")
        lines.append(f"  ├─ Eventos con vehículos:  {len(eventos_con_vehiculos)}")
        total_personas = sum(e.personas_count for e in eventos)
        total_vehiculos = sum(e.vehiculos_count for e in eventos)
        lines.append(f"  ├─ Total personas:         ~{total_personas}")
        lines.append(f"  └─ Total vehículos:        ~{total_vehiculos}")
        lines.append("")
        
        # Objetos detectados
        if stats.get('objetos_unicos'):
            lines.append("  OBJETOS DETECTADOS:")
            lines.append("  " + "-" * 50)
            for obj in stats['objetos_unicos'][:20]:
                lines.append(f"    • {obj}")
            lines.append("")
        
        # ═══ 3. PATRONES Y ANOMALÍAS ═══
        patrones = cross_analysis.get('patrones_detectados', [])
        anomalias = cross_analysis.get('anomalias', [])
        
        if patrones or anomalias:
            lines.append("=" * 90)
            lines.append("3. PATRONES Y ANOMALÍAS DETECTADAS")
            lines.append("=" * 90)
            lines.append("")
            
            if patrones:
                lines.append("  PATRONES:")
                lines.append("  " + "-" * 50)
                for i, patron in enumerate(patrones, 1):
                    if isinstance(patron, dict):
                        lines.append(f"  [{i}] {patron.get('patron', patron)}")
                        if patron.get('relevancia'):
                            lines.append(f"      Relevancia: {patron['relevancia']}")
                    else:
                        lines.append(f"  [{i}] {patron}")
                lines.append("")
            
            if anomalias:
                lines.append("  ⚠️ ANOMALÍAS:")
                lines.append("  " + "-" * 50)
                for anomalia in anomalias:
                    lines.append(f"    ⚠ {anomalia}")
                lines.append("")
        
        # ═══ 4. EVENTOS DETALLADOS ═══
        if eventos:
            lines.append("=" * 90)
            lines.append("4. EVENTOS DETECTADOS (DETALLE)")
            lines.append("=" * 90)
            lines.append("")
            
            for i, evento in enumerate(eventos, 1):
                # Obtener nivel de riesgo del análisis
                nivel = 'BAJO'
                if evento.analisis_detallado:
                    gemini_data = evento.analisis_detallado.get('gemini_video', {})
                    nivel = gemini_data.get('nivel_riesgo', 'BAJO')
                
                risk_indicator = RISK_LABELS.get(nivel, nivel)
                
                lines.append(f"  ┌─────────────────────────────────────────────────────────")
                lines.append(f"  │ EVENTO #{i:03d}  |  {risk_indicator}  |  {self._format_timestamp(evento.timestamp_inicio)} - {self._format_timestamp(evento.timestamp_fin)}")
                lines.append(f"  ├─────────────────────────────────────────────────────────")
                lines.append(f"  │ Duración:    {evento.duracion:.1f}s")
                lines.append(f"  │ Confianza:   {evento.confianza * 100:.0f}%")
                lines.append(f"  │ Personas:    {evento.personas_count}")
                lines.append(f"  │ Vehículos:   {evento.vehiculos_count}")
                
                if evento.objetos_detectados:
                    lines.append(f"  │ Objetos:     {', '.join(evento.objetos_detectados[:10])}")
                
                if evento.acciones_detectadas:
                    lines.append(f"  │ Acciones:    {', '.join(evento.acciones_detectadas[:10])}")
                
                lines.append(f"  │")
                lines.append(f"  │ DESCRIPCIÓN:")
                desc = evento.descripcion or 'Sin descripción'
                # Wrap description
                words = desc.split()
                current_line = "  │   "
                for word in words:
                    if len(current_line) + len(word) + 1 > 85:
                        lines.append(current_line)
                        current_line = "  │   " + word
                    else:
                        current_line += " " + word if len(current_line) > 6 else word
                if current_line.strip('│ '):
                    lines.append(current_line)
                
                # Alertas del evento
                if evento.analisis_detallado:
                    gemini_data = evento.analisis_detallado.get('gemini_video', {})
                    alertas = gemini_data.get('alertas', [])
                    if alertas:
                        lines.append(f"  │")
                        lines.append(f"  │ ⚠️ ALERTAS:")
                        for alerta in alertas:
                            lines.append(f"  │   ⚠ {alerta}")
                    
                    razon = gemini_data.get('razon_riesgo', '')
                    if razon:
                        lines.append(f"  │")
                        lines.append(f"  │ RAZÓN RIESGO: {razon[:100]}")
                
                if evento.frames_urls:
                    lines.append(f"  │")
                    lines.append(f"  │ 📷 Frames guardados: {len(evento.frames_urls)}")
                
                lines.append(f"  └─────────────────────────────────────────────────────────")
                lines.append("")
        
        # ═══ 5. RECOMENDACIONES ═══
        recomendaciones = cross_analysis.get('recomendaciones_seguridad', [])
        if recomendaciones:
            lines.append("=" * 90)
            lines.append("5. RECOMENDACIONES DE SEGURIDAD")
            lines.append("=" * 90)
            lines.append("")
            for i, rec in enumerate(recomendaciones, 1):
                lines.append(f"  {i}. {rec}")
            lines.append("")
        
        # ═══ FOOTER ═══
        lines.append("=" * 90)
        lines.append("  Reporte generado automáticamente por TIVIT-CU002")
        lines.append("  Sistema de Análisis Inteligente de Videos de Seguridad v3.0")
        lines.append("  Pipeline: Motion Detection + Video Clips + Gemini 2.5 Flash")
        lines.append(f"  Fecha de generación: {datetime.utcnow().isoformat()}")
        lines.append("=" * 90)
        
        return "\n".join(lines)
    
    # ═══════════════════════════════════════════════════════════════
    # REPORTE PDF
    # ═══════════════════════════════════════════════════════════════
    
    def generate_pdf_report(
        self,
        video: SecurityVideo,
        eventos: List[EventoSeguridad],
        output_path: str,
        cross_analysis: Dict[str, Any] = None
    ) -> bool:
        """
        Genera reporte PDF profesional con imágenes de frames
        
        Args:
            video: Video de seguridad
            eventos: Lista de eventos
            output_path: Ruta de salida del PDF
            cross_analysis: Análisis cruzado
            
        Returns:
            True si se generó correctamente
        """
        if not self._reportlab_available:
            logger.warning("⚠️ ReportLab no disponible")
            return False
        
        cross_analysis = cross_analysis or {}
        
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch, cm
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                PageBreak, Image as RLImage, KeepTogether, HRFlowable
            )
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
            
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            doc = SimpleDocTemplate(
                output_path,
                pagesize=letter,
                leftMargin=0.75*inch,
                rightMargin=0.75*inch,
                topMargin=0.75*inch,
                bottomMargin=0.75*inch
            )
            story = []
            styles = getSampleStyleSheet()
            
            # ═══ ESTILOS PERSONALIZADOS ═══
            title_style = ParagraphStyle(
                'ReportTitle',
                parent=styles['Heading1'],
                fontSize=22,
                textColor=colors.HexColor('#1f2937'),
                spaceAfter=6,
                alignment=TA_CENTER
            )
            
            subtitle_style = ParagraphStyle(
                'ReportSubtitle',
                parent=styles['Normal'],
                fontSize=11,
                textColor=colors.HexColor('#6b7280'),
                alignment=TA_CENTER,
                spaceAfter=20
            )
            
            section_style = ParagraphStyle(
                'SectionHeader',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=colors.HexColor('#1e3a5f'),
                spaceBefore=20,
                spaceAfter=10,
                borderWidth=1,
                borderColor=colors.HexColor('#3b82f6'),
                borderPadding=5
            )
            
            risk_style = ParagraphStyle(
                'RiskLevel',
                parent=styles['Normal'],
                fontSize=16,
                alignment=TA_CENTER,
                spaceAfter=15,
                spaceBefore=10
            )
            
            body_style = ParagraphStyle(
                'BodyText',
                parent=styles['Normal'],
                fontSize=10,
                leading=14,
                spaceAfter=6
            )
            
            small_style = ParagraphStyle(
                'SmallText',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.HexColor('#6b7280'),
                leading=10
            )
            
            # ═══ PORTADA ═══
            story.append(Spacer(1, 1.5*inch))
            story.append(Paragraph("REPORTE DE ANÁLISIS", title_style))
            story.append(Paragraph("CÁMARA DE SEGURIDAD", title_style))
            story.append(Spacer(1, 0.3*inch))
            story.append(Paragraph("Sistema TIVIT-CU002 Security v3.0", subtitle_style))
            story.append(Paragraph("Pipeline: Video Clips + Gemini 2.5 Flash", subtitle_style))
            story.append(Spacer(1, 0.5*inch))
            
            # Nivel de riesgo global
            nivel_riesgo = cross_analysis.get('nivel_riesgo_global', 'BAJO')
            risk_color = RISK_COLORS.get(nivel_riesgo, '#6b7280')
            
            risk_data = [
                ['NIVEL DE RIESGO GLOBAL'],
                [nivel_riesgo]
            ]
            risk_table = Table(risk_data, colWidths=[4*inch])
            risk_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor(risk_color)),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('FONTSIZE', (0, 1), (-1, 1), 20),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 12),
                ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#1e3a5f')),
            ]))
            story.append(risk_table)
            story.append(Spacer(1, 0.5*inch))
            
            # Info básica en portada
            info_data = [
                ['Cámara:', video.nombre_camara],
                ['Ubicación:', video.ubicacion],
                ['Fecha grabación:', video.fecha_grabacion],
                ['Duración:', self._format_duration(video.duracion_segundos)],
                ['Total eventos:', str(len(eventos))],
                ['Fecha análisis:', datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')],
            ]
            info_table = Table(info_data, colWidths=[2*inch, 4*inch])
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb'))
            ]))
            story.append(info_table)
            
            story.append(PageBreak())
            
            # ═══ RESUMEN EJECUTIVO ═══
            story.append(Paragraph("RESUMEN EJECUTIVO", section_style))
            
            resumen = cross_analysis.get('resumen_ejecutivo', 'Sin resumen disponible.')
            story.append(Paragraph(resumen, body_style))
            story.append(Spacer(1, 0.2*inch))
            
            # Distribución de riesgo
            riesgos = video.estadisticas.get('eventos_por_riesgo', {}) if video.estadisticas else {}
            
            risk_dist_data = [
                ['Nivel', 'Cantidad', 'Proporción'],
                ['BAJO', str(riesgos.get('BAJO', 0)), 
                 f"{(riesgos.get('BAJO', 0) / max(len(eventos), 1)) * 100:.0f}%"],
                ['MEDIO', str(riesgos.get('MEDIO', 0)),
                 f"{(riesgos.get('MEDIO', 0) / max(len(eventos), 1)) * 100:.0f}%"],
                ['ALTO', str(riesgos.get('ALTO', 0)),
                 f"{(riesgos.get('ALTO', 0) / max(len(eventos), 1)) * 100:.0f}%"],
                ['CRÍTICO', str(riesgos.get('CRITICO', 0)),
                 f"{(riesgos.get('CRITICO', 0) / max(len(eventos), 1)) * 100:.0f}%"],
                ['TOTAL', str(len(eventos)), '100%'],
            ]
            
            risk_dist_table = Table(risk_dist_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
            risk_dist_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
                # Color de fondo por riesgo
                ('BACKGROUND', (0, 1), (0, 1), colors.HexColor('#dcfce7')),  # BAJO verde claro
                ('BACKGROUND', (0, 2), (0, 2), colors.HexColor('#fef3c7')),  # MEDIO amarillo
                ('BACKGROUND', (0, 3), (0, 3), colors.HexColor('#fecaca')),  # ALTO rojo claro
                ('BACKGROUND', (0, 4), (0, 4), colors.HexColor('#f87171')),  # CRITICO rojo
                ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#f3f4f6')),  # Total gris
                ('FONTNAME', (0, 5), (-1, 5), 'Helvetica-Bold'),
            ]))
            story.append(risk_dist_table)
            story.append(Spacer(1, 0.3*inch))
            
            # Patrones
            patrones = cross_analysis.get('patrones_detectados', [])
            if patrones:
                story.append(Paragraph("<b>Patrones detectados:</b>", body_style))
                for patron in patrones:
                    if isinstance(patron, dict):
                        text = patron.get('patron', str(patron))
                    else:
                        text = str(patron)
                    story.append(Paragraph(f"• {text}", body_style))
                story.append(Spacer(1, 0.2*inch))
            
            # Anomalías
            anomalias = cross_analysis.get('anomalias', [])
            if anomalias:
                story.append(Paragraph("<b>⚠ Anomalías detectadas:</b>", body_style))
                for anomalia in anomalias:
                    story.append(Paragraph(f"⚠ {anomalia}", body_style))
                story.append(Spacer(1, 0.2*inch))
            
            story.append(PageBreak())
            
            # ═══ EVENTOS DETALLADOS ═══
            story.append(Paragraph("EVENTOS DETECTADOS", section_style))
            
            # Lista para acumular archivos temporales a eliminar después de build
            temp_files_to_cleanup = []
            
            for i, evento in enumerate(eventos, 1):
                # Nivel de riesgo del evento
                nivel_ev = 'BAJO'
                if evento.analisis_detallado:
                    gemini_data = evento.analisis_detallado.get('gemini_video', {})
                    nivel_ev = gemini_data.get('nivel_riesgo', 'BAJO')
                
                ev_risk_color = RISK_COLORS.get(nivel_ev, '#6b7280')
                
                # Header del evento
                ev_header_data = [[
                    f"Evento #{i:03d}",
                    nivel_ev,
                    f"{self._format_timestamp(evento.timestamp_inicio)} - {self._format_timestamp(evento.timestamp_fin)}",
                    f"{evento.duracion:.1f}s"
                ]]
                ev_header = Table(ev_header_data, colWidths=[1.5*inch, 1.2*inch, 2.3*inch, 1*inch])
                ev_header.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#1e3a5f')),
                    ('BACKGROUND', (1, 0), (1, 0), colors.HexColor(ev_risk_color)),
                    ('BACKGROUND', (2, 0), (2, 0), colors.HexColor('#f3f4f6')),
                    ('BACKGROUND', (3, 0), (3, 0), colors.HexColor('#f3f4f6')),
                    ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
                ]))
                story.append(ev_header)
                
                # Descripción
                desc = evento.descripcion or 'Sin descripción'
                story.append(Paragraph(f"<b>Descripción:</b> {desc}", body_style))
                
                # Detalles
                details = []
                if evento.personas_count > 0:
                    details.append(f"Personas: {evento.personas_count}")
                if evento.vehiculos_count > 0:
                    details.append(f"Vehículos: {evento.vehiculos_count}")
                if evento.objetos_detectados:
                    details.append(f"Objetos: {', '.join(evento.objetos_detectados[:8])}")
                if evento.acciones_detectadas:
                    details.append(f"Acciones: {', '.join(evento.acciones_detectadas[:5])}")
                
                if details:
                    story.append(Paragraph(" | ".join(details), small_style))
                
                # Alertas
                if evento.analisis_detallado:
                    gemini_data = evento.analisis_detallado.get('gemini_video', {})
                    alertas = gemini_data.get('alertas', [])
                    if alertas:
                        for alerta in alertas[:3]:
                            story.append(Paragraph(f"⚠ {alerta}", body_style))
                
                # Imagen del frame (si hay URLs)
                if evento.frames_urls:
                    frame_image = self._download_frame_for_pdf(evento.frames_urls[0])
                    if frame_image:
                        try:
                            img = RLImage(frame_image, width=5*inch, height=2.8*inch)
                            story.append(Spacer(1, 0.1*inch))
                            story.append(img)
                            story.append(Paragraph(
                                f"Frame capturado en {self._format_timestamp(evento.timestamp_inicio)}",
                                small_style
                            ))
                            # Guardar para limpiar después de doc.build()
                            temp_files_to_cleanup.append(frame_image)
                        except Exception as img_err:
                            logger.warning(f"No se pudo insertar imagen: {img_err}")
                            # Si falla, eliminar inmediatamente
                            try:
                                os.remove(frame_image)
                            except Exception:
                                pass
                
                story.append(HRFlowable(
                    width="100%", thickness=0.5,
                    color=colors.HexColor('#e5e7eb'),
                    spaceBefore=8, spaceAfter=8
                ))
            
            # ═══ RECOMENDACIONES ═══
            recomendaciones = cross_analysis.get('recomendaciones_seguridad', [])
            if recomendaciones:
                story.append(PageBreak())
                story.append(Paragraph("RECOMENDACIONES DE SEGURIDAD", section_style))
                
                for i, rec in enumerate(recomendaciones, 1):
                    story.append(Paragraph(f"<b>{i}.</b> {rec}", body_style))
                story.append(Spacer(1, 0.3*inch))
            
            # ═══ FOOTER ═══
            story.append(Spacer(1, 0.5*inch))
            story.append(HRFlowable(
                width="100%", thickness=1,
                color=colors.HexColor('#1e3a5f'),
                spaceBefore=10, spaceAfter=10
            ))
            story.append(Paragraph(
                "Reporte generado por TIVIT-CU002 Security v3.0 | "
                "Pipeline: Video Clips + Gemini 2.5 Flash | "
                f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
                small_style
            ))
            
            # Build PDF
            doc.build(story)
            
            # Limpiar archivos temporales DESPUÉS de construir el PDF
            for temp_file in temp_files_to_cleanup:
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
            
            logger.info(f"✅ PDF profesional generado: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error generando PDF: {e}", exc_info=True)
            return False
    
    # ═══════════════════════════════════════════════════════════════
    # UTILIDADES
    # ═══════════════════════════════════════════════════════════════
    
    def _download_frame_for_pdf(self, url: str) -> Optional[str]:
        """Resolve a local or configured storage frame without HTTP downloads."""
        try:
            if url.startswith('/') and os.path.exists(url):
                return url
            parsed = urlparse(url)
            if parsed.scheme in ("http", "https", "gs"):
                logger.warning("Frame remoto no permitido: %.80s", url)
                return None

            if parsed.scheme == "file":
                local_path = parsed.path
                return local_path if os.path.exists(local_path) else None

            if parsed.scheme not in ("", "s3"):
                return None
            from infrastructure.dependencies import get_storage_adapter

            storage = get_storage_adapter()
            if not storage or not storage.is_available():
                return None
            storage_path = parsed.path.lstrip("/") if parsed.scheme == "s3" else url.lstrip("/")
            if url.startswith("/socio/media/"):
                storage_path = url.removeprefix("/socio/media/")
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg", prefix="pdf_frame_")
            temp_path = temp_file.name
            temp_file.close()
            if not storage.descargar_archivo(storage_path, temp_path) or os.path.getsize(temp_path) <= 100:
                os.remove(temp_path)
                return None
            return temp_path
            
        except Exception as e:
            logger.warning(f"No se pudo descargar frame: {e}")
            return None
    
    def _format_duration(self, seconds: float) -> str:
        """Formatea duración en formato legible"""
        if not seconds:
            return "N/A"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}min {secs}s"
        elif minutes > 0:
            return f"{minutes}min {secs}s"
        else:
            return f"{secs}s"
    
    def _format_timestamp(self, seconds: float) -> str:
        """Formatea timestamp en HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
