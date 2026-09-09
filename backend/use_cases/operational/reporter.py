import io
import os
import tempfile
import logging
from datetime import datetime
from typing import List, Dict, Optional

from domain.entities import OperationalAnalysis, OperationalEvent, OPERATIONAL_ANALYSIS_TYPES

logger = logging.getLogger(__name__)

# Brand colours
_RED   = '#C8102E'
_DARK  = '#1A1A2E'
_MID   = '#283593'
_LIGHT = '#E8EAF6'
_GREY  = '#757575'
_WHITE = '#FFFFFF'

def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _download_image(storage_adapter, url: str) -> Optional[bytes]:
    """Descarga bytes de un frame desde el almacenamiento local (s3://, file://, ruta)."""
    try:
        # file:// o ruta local
        if url.startswith("file://") or os.path.exists(url):
            path = url.replace("file://", "", 1)
            if os.path.exists(path):
                with open(path, "rb") as f:
                    return f.read()
            return None

        blob_name = url
        if "://" in url:
            parts = url.split("://", 1)[1]
            blob_name = parts.split("/", 1)[1] if "/" in parts else parts

        if not storage_adapter or not storage_adapter.is_available():
            return None
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            if not storage_adapter.descargar_archivo(blob_name, tmp_path):
                return None
            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception:
        return None


class OperationalReporter:
    """Fase 4: Generación de reportes PDF para análisis operativos"""

    def __init__(self, storage_adapter, temp_dir: str):
        self.storage_adapter = storage_adapter
        self.temp_dir = temp_dir

    # ─────────────────────────────────────────────────────────────
    # PUBLIC
    # ─────────────────────────────────────────────────────────────

    def generate_reports(self, analysis: OperationalAnalysis, events: List[OperationalEvent], summary: dict, vid: str) -> Dict[str, str]:
        urls = {}
        try:
            pdf_path = self._generate_pdf_report(analysis, events, summary, vid)
            if pdf_path and os.path.exists(pdf_path):
                if self.storage_adapter and self.storage_adapter.is_available():
                    storage_destination = f"operational/{analysis.id}/report.pdf"
                    url = self.storage_adapter.upload_file(
                        pdf_path, storage_destination,
                        content_type='application/pdf',
                        return_signed_url=True,
                    )
                    if url:
                        urls['pdf'] = url
                        logger.info(f"[{vid}]    📄 Reporte PDF subido al almacenamiento")
                try:
                    os.remove(pdf_path)
                except OSError:
                    pass
        except Exception as e:
            logger.error(f"[{vid}]    ⚠️ Error generando reporte PDF: {e}", exc_info=True)
        return urls

    # ─────────────────────────────────────────────────────────────
    # PDF GENERATION
    # ─────────────────────────────────────────────────────────────

    def _generate_pdf_report(self, analysis: OperationalAnalysis, events: List[OperationalEvent], summary: dict, vid: str) -> Optional[str]:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.lib.colors import HexColor, white, black
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                HRFlowable, KeepTogether, Image as RLImage,
            )
            from reportlab.lib import colors as rl_colors
        except ImportError:
            logger.warning(f"[{vid}]    ⚠️ ReportLab no instalado")
            return None

        pdf_path = os.path.join(self.temp_dir, f"op_report_{vid}.pdf")
        type_info = OPERATIONAL_ANALYSIS_TYPES.get(analysis.analysis_type, {})
        type_name = type_info.get('name', analysis.analysis_type)
        type_icon = type_info.get('icon', '📊')

        W, H = A4
        LEFT = RIGHT = 1.8 * cm
        TOP = BOT = 1.8 * cm
        CONTENT_W = W - LEFT - RIGHT

        doc = SimpleDocTemplate(
            pdf_path, pagesize=A4,
            topMargin=TOP, bottomMargin=BOT,
            leftMargin=LEFT, rightMargin=RIGHT,
        )

        SS = getSampleStyleSheet()
        def _ps(name, **kw):
            base = kw.pop('parent', SS['Normal'])
            return ParagraphStyle(name, parent=base, **kw)

        title_s  = _ps('OPTitle',  parent=SS['Title'],   fontSize=20, textColor=HexColor(_WHITE),  spaceAfter=0, leading=24)
        sub_s    = _ps('OPSub',    parent=SS['Normal'],  fontSize=11, textColor=HexColor(_WHITE),  spaceAfter=0)
        h2_s     = _ps('OPH2',     parent=SS['Heading2'],fontSize=12, textColor=HexColor(_MID),    spaceBefore=14, spaceAfter=6, fontName='Helvetica-Bold')
        body_s   = _ps('OPBody',   fontSize=9,  leading=13)
        small_s  = _ps('OPSmall',  fontSize=7.5,leading=10, textColor=HexColor(_GREY))
        label_s  = _ps('OPLabel',  fontSize=8,  textColor=HexColor(_GREY), spaceAfter=1)
        value_s  = _ps('OPValue',  fontSize=9,  fontName='Helvetica-Bold', spaceAfter=0)
        ev_num_s = _ps('OPEvNum',  fontSize=18, fontName='Helvetica-Bold', textColor=HexColor(_RED), leading=22)
        ev_hd_s  = _ps('OPEvHd',   fontSize=10, fontName='Helvetica-Bold', textColor=HexColor(_DARK), spaceAfter=2)
        ev_bd_s  = _ps('OPEvBd',   fontSize=8.5,leading=12, textColor=HexColor('#333333'))

        RED  = HexColor(_RED)
        DARK = HexColor(_DARK)
        MID  = HexColor(_MID)
        LITE = HexColor(_LIGHT)

        elems = []

        # ── HEADER BANNER ──────────────────────────────────────────
        dur_str = (
            f"{analysis.video_duration/3600:.1f}h"
            if analysis.video_duration > 3600
            else f"{analysis.video_duration/60:.1f}min"
        )
        banner_inner = [
            [
                Paragraph("TIVIT CU002", _ps('BrandLbl', fontSize=8, textColor=HexColor('#FFCDD2'), fontName='Helvetica-Bold', spaceAfter=0)),
                Paragraph(f"{type_icon} Reporte de Análisis Operativo", title_s),
                Paragraph(type_name, sub_s),
            ]
        ]
        banner_table = Table(banner_inner, colWidths=[CONTENT_W])
        banner_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), DARK),
            ('TOPPADDING',    (0, 0), (-1, -1), 14),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
            ('LEFTPADDING',   (0, 0), (-1, -1), 16),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 16),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [DARK]),
        ]))
        elems.append(banner_table)
        elems.append(Spacer(1, 10))

        # ── METADATA CARDS ─────────────────────────────────────────
        created_str = analysis.created_at[:16].replace('T', '  ') if analysis.created_at else '-'
        meta_pairs = [
            ("ID del análisis", analysis.id[:24]),
            ("Fecha",           created_str),
            ("Video",           (analysis.video_filename or '-')[:50]),
            ("Duración",        dur_str),
            ("Cámara",          analysis.nombre_camara or 'Sin cámara'),
            ("Ubicación",       analysis.ubicacion or 'Sin ubicación'),
        ]
        if analysis.custom_context:
            meta_pairs.append(("Contexto", analysis.custom_context[:80]))

        def _card(label, value):
            return [Paragraph(label, label_s), Paragraph(str(value), value_s)]

        # 2-column card grid
        card_rows = []
        for i in range(0, len(meta_pairs), 2):
            left  = _card(*meta_pairs[i])
            right = _card(*meta_pairs[i+1]) if i+1 < len(meta_pairs) else [Paragraph('', label_s), Paragraph('', value_s)]
            card_rows.append([left, right])

        CW = CONTENT_W / 2 - 4
        for row in card_rows:
            t = Table([row], colWidths=[CW, CW])
            t.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (-1, -1), LITE),
                ('BOX',           (0, 0), (0, 0), 0.5, HexColor(_RED)),
                ('BOX',           (1, 0), (1, 0), 0.5, HexColor(_RED)),
                ('LEFTPADDING',   (0, 0), (-1, -1), 8),
                ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
                ('TOPPADDING',    (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ]))
            elems.append(t)
            elems.append(Spacer(1, 4))

        elems.append(Spacer(1, 8))

        # ── SUMMARY SECTION ────────────────────────────────────────
        elems.append(HRFlowable(width=CONTENT_W, thickness=2, color=RED, spaceAfter=6))
        elems.append(Paragraph("Resumen Consolidado", h2_s))

        if isinstance(summary, dict) and summary:
            skip_keys = {'raw_response', 'raw', 'hourly_breakdown'}
            readable = {k: v for k, v in summary.items()
                        if k not in skip_keys and not isinstance(v, (list, dict))}
            if readable:
                sum_data = [[Paragraph(f"<b>{k.replace('_',' ').title()}</b>", body_s),
                             Paragraph(str(v)[:200], body_s)]
                            for k, v in list(readable.items())[:10]]
                sum_table = Table(sum_data, colWidths=[5*cm, CONTENT_W - 5*cm])
                sum_table.setStyle(TableStyle([
                    ('FONTSIZE',      (0, 0), (-1, -1), 9),
                    ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
                    ('ROWBACKGROUNDS',(0, 0), (-1, -1), [HexColor(_WHITE), LITE]),
                    ('LEFTPADDING',   (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
                    ('TOPPADDING',    (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('BOX',           (0, 0), (-1, -1), 0.5, HexColor('#CCCCCC')),
                    ('INNERGRID',     (0, 0), (-1, -1), 0.3, HexColor('#DDDDDD')),
                ]))
                elems.append(sum_table)

            assessment = summary.get('overall_assessment') or summary.get('resumen_ejecutivo') or summary.get('resumen', '')
            if assessment:
                elems.append(Spacer(1, 6))
                elems.append(Paragraph("<b>Evaluación general:</b>", body_s))
                elems.append(Paragraph(str(assessment)[:600], body_s))

            recs = summary.get('recommendations') or summary.get('recomendaciones', [])
            if isinstance(recs, list) and recs:
                elems.append(Spacer(1, 6))
                elems.append(Paragraph("<b>Recomendaciones:</b>", body_s))
                for i, rec in enumerate(recs[:8], 1):
                    elems.append(Paragraph(f"{i}. {str(rec)[:200]}", body_s))
        else:
            elems.append(Paragraph("Resumen no disponible.", body_s))

        elems.append(Spacer(1, 10))

        # ── EVENTS SECTION ─────────────────────────────────────────
        elems.append(HRFlowable(width=CONTENT_W, thickness=2, color=RED, spaceAfter=6))
        elems.append(Paragraph(f"Eventos Detectados ({len(events)})", h2_s))
        elems.append(Spacer(1, 4))

        MAX_EVENTS_WITH_IMAGES = 30  # embed images only for first N events
        MAX_EVENTS_TOTAL = 100

        for idx, ev in enumerate(events[:MAX_EVENTS_TOTAL], 1):
            with_images = idx <= MAX_EVENTS_WITH_IMAGES and bool(ev.frame_urls)

            # — Number + type badge row
            time_str = f"{_fmt_time(ev.timestamp_start)} — {_fmt_time(ev.timestamp_end)}"
            badge_data = [[
                Paragraph(f"{idx}", ev_num_s),
                Table(
                    [[Paragraph(f"<b>{ev.event_type}</b>", ev_hd_s)],
                     [Paragraph(time_str, small_s)]],
                    colWidths=[CONTENT_W - 2*cm]
                ),
            ]]
            badge_t = Table(badge_data, colWidths=[2*cm, CONTENT_W - 2*cm])
            badge_t.setStyle(TableStyle([
                ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING',   (0, 0), (-1, -1), 6),
                ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
                ('TOPPADDING',    (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('BACKGROUND',    (0, 0), (-1, -1), LITE),
                ('LINEBELOW',     (0, 0), (-1, 0), 1, RED),
            ]))

            # — Detail row
            detail_lines = []
            if ev.person_description:
                detail_lines.append(f"<b>Persona:</b> {ev.person_description[:200]}")
            if ev.direction:
                detail_lines.append(f"<b>Dirección:</b> {ev.direction}")
            if ev.carried_objects:
                detail_lines.append(f"<b>Objetos:</b> {ev.carried_objects[:120]}")
            if ev.confidence:
                detail_lines.append(f"<b>Confianza:</b> {ev.confidence}")
            if ev.zone:
                detail_lines.append(f"<b>Zona:</b> {ev.zone}")

            detail_paras = [Paragraph(line, ev_bd_s) for line in detail_lines] or [Paragraph("—", ev_bd_s)]

            if with_images:
                # Download up to 3 frames
                img_elems = []
                for url in ev.frame_urls[:3]:
                    raw = _download_image(self.storage_adapter, url)
                    if raw:
                        try:
                            img_buf = io.BytesIO(raw)
                            img = RLImage(img_buf, width=5.2*cm, height=3.5*cm)
                            img.hAlign = 'LEFT'
                            img_elems.append(img)
                        except Exception:
                            pass

                if img_elems:
                    # Place text on left, images on right
                    img_col = []
                    for im in img_elems:
                        img_col.append([im])
                    img_inner = Table(img_col, colWidths=[5.4*cm])
                    img_inner.setStyle(TableStyle([
                        ('TOPPADDING',    (0, 0), (-1, -1), 2),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                        ('LEFTPADDING',   (0, 0), (-1, -1), 2),
                    ]))

                    txt_w = CONTENT_W - 5.8*cm
                    det_row_data = [[
                        Table([[p] for p in detail_paras], colWidths=[txt_w]),
                        img_inner,
                    ]]
                    det_t = Table(det_row_data, colWidths=[txt_w, 5.8*cm])
                    det_t.setStyle(TableStyle([
                        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
                        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
                        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
                        ('TOPPADDING',    (0, 0), (-1, -1), 6),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('BACKGROUND',    (0, 0), (-1, -1), HexColor(_WHITE)),
                    ]))
                else:
                    # No images loaded — plain text row
                    det_t = Table([[Table([[p] for p in detail_paras], colWidths=[CONTENT_W - 0.4*cm])]],
                                  colWidths=[CONTENT_W])
                    det_t.setStyle(TableStyle([
                        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
                        ('TOPPADDING',    (0, 0), (-1, -1), 6),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('BACKGROUND',    (0, 0), (-1, -1), HexColor(_WHITE)),
                    ]))
            else:
                det_t = Table([[Table([[p] for p in detail_paras], colWidths=[CONTENT_W - 0.4*cm])]],
                              colWidths=[CONTENT_W])
                det_t.setStyle(TableStyle([
                    ('LEFTPADDING',   (0, 0), (-1, -1), 8),
                    ('TOPPADDING',    (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('BACKGROUND',    (0, 0), (-1, -1), HexColor(_WHITE)),
                ]))

            outer = Table([[badge_t], [det_t]], colWidths=[CONTENT_W])
            outer.setStyle(TableStyle([
                ('BOX',           (0, 0), (-1, -1), 0.8, HexColor('#DDDDDD')),
                ('TOPPADDING',    (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ('LEFTPADDING',   (0, 0), (-1, -1), 0),
                ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
            ]))

            elems.append(KeepTogether([outer, Spacer(1, 6)]))

        if len(events) > MAX_EVENTS_TOTAL:
            elems.append(Paragraph(f"… y {len(events) - MAX_EVENTS_TOTAL} eventos adicionales no mostrados.", small_s))

        # ── FOOTER ─────────────────────────────────────────────────
        elems.append(Spacer(1, 16))
        elems.append(HRFlowable(width=CONTENT_W, thickness=0.5, color=HexColor(_GREY)))
        elems.append(Spacer(1, 4))
        elems.append(Paragraph(
            f"Generado por TIVIT CU002 — Pipeline Operativo v3.0 — "
            f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
            small_s,
        ))

        doc.build(elems)
        logger.info(f"PDF generado: {pdf_path}")
        return pdf_path
