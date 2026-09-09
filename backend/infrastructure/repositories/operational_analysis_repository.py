"""
Repositorio PostgreSQL/SQLAlchemy para Análisis Operativo

Tablas:
- operational_analyses: Análisis principales
- operational_events: Eventos individuales detectados

Patrón: Singleton con RLock (thread-safe) — mismo patrón que SecurityVideoRepository.
"""

import logging
import json
import base64
from typing import Optional, List
from threading import RLock
from sqlalchemy import text

from infrastructure.db.session import SessionLocal
from infrastructure.db.models import OperationalAnalysisModel, OperationalEventModel
from domain.entities import (
    OperationalAnalysis,
    OperationalEvent,
    EstadoOperationalAnalysis,
)

logger = logging.getLogger(__name__)


class OperationalAnalysisRepository:
    """Repositorio SQLAlchemy/PostgreSQL para análisis operativos (Singleton thread-safe)"""

    _instance = None
    _lock_cls = RLock()

    def __new__(cls, *args, **kwargs):
        with cls._lock_cls:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._lock_repo = RLock()
        self._initialized = True
        logger.info("✅ OperationalAnalysisRepository inicializado (PostgreSQL/SQLAlchemy)")

    # ═══════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════

    def _analysis_to_row(self, analysis: OperationalAnalysis) -> dict:
        estado_val = analysis.estado.value if isinstance(analysis.estado, EstadoOperationalAnalysis) else str(analysis.estado)
        return {
            'id': analysis.id,
            'usuario': analysis.usuario or '',
            'analysis_type': analysis.analysis_type or '',
            'estado': estado_val,
            's3_uri': analysis.video_url or '',
            'custom_context': analysis.custom_context or '',
            'result': analysis.to_dict(),
        }

    def _row_to_analysis(self, row: OperationalAnalysisModel) -> OperationalAnalysis:
        data = row.result if row.result else {}
        if not data:
            data = {
                'id': row.id,
                'usuario': row.usuario,
                'analysis_type': row.analysis_type,
                'estado': row.estado,
                'video_url': row.s3_uri,
                'custom_context': row.custom_context,
            }
        else:
            data = dict(data)
            data.setdefault('id', row.id)
            data.setdefault('usuario', row.usuario)
            data.setdefault('analysis_type', row.analysis_type)
            data.setdefault('estado', row.estado)
            data.setdefault('video_url', row.s3_uri or '')
            data.setdefault('custom_context', row.custom_context or '')
        return OperationalAnalysis.from_dict(data)

    def _event_to_row(self, evento: OperationalEvent, analysis_id: str) -> dict:
        return {
            'id': evento.id,
            'analysis_id': analysis_id,
            'timestamp_start': evento.timestamp_start,
            'timestamp_end': evento.timestamp_end,
            'event_type': evento.event_type or '',
            'description': getattr(evento, 'person_description', '') or '',
            'metadata_json': evento.to_dict(),
        }

    def _row_to_event(self, row: OperationalEventModel) -> OperationalEvent:
        data = row.metadata_json if row.metadata_json else {}
        if not data:
            data = {
                'id': row.id,
                'analysis_id': row.analysis_id,
                'timestamp_start': row.timestamp_start,
                'timestamp_end': row.timestamp_end,
                'event_type': row.event_type,
            }
        else:
            data = dict(data)
            data.setdefault('id', row.id)
            data.setdefault('analysis_id', row.analysis_id)
            data.setdefault('timestamp_start', row.timestamp_start)
            data.setdefault('timestamp_end', row.timestamp_end)
            data.setdefault('event_type', row.event_type)
        return OperationalEvent.from_dict(data)

    # ═══════════════════════════════════════════════════
    # PROGRESS / PUB-SUB
    # ═══════════════════════════════════════════════════

    def _build_progress_state(self, analysis: OperationalAnalysis) -> dict:
        status = analysis.estado.value if hasattr(analysis.estado, 'value') else str(analysis.estado)
        is_final = status in ('completed', 'error', 'cancelled')
        return {
            'status': status,
            'progress': round(float(analysis.progress or 0), 1),
            'current_phase': analysis.current_phase or '',
            'summary': analysis.summary if status == 'completed' else {},
            'error_message': (
                analysis.error_message
                if status in ('error', 'cancelled') and analysis.error_message
                else ('Se produjo un error durante el análisis' if status in ('error', 'cancelled') else '')
            ),
            'scan_stats': analysis.scan_stats or {},
            'eta_seconds': None,
            'final': is_final,
        }

    def _publish_progress_update(self, analysis: OperationalAnalysis) -> None:
        """Publica estado de progreso en Redis Pub/Sub y guarda snapshot reciente."""
        try:
            from infrastructure.services.job_queue import get_redis_connection

            redis_conn = get_redis_connection()
            state = self._build_progress_state(analysis)
            payload = json.dumps(state, default=str)
            channel = f"op_progress:{analysis.id}"
            latest_key = f"op_progress_latest:{analysis.id}"

            redis_conn.publish(channel, payload)
            redis_conn.setex(latest_key, 7200, payload)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════
    # ANÁLISIS
    # ═══════════════════════════════════════════════════

    def guardar_analisis(self, analysis: OperationalAnalysis) -> OperationalAnalysis:
        """Guarda o actualiza un análisis operativo"""
        with self._lock_repo:
            try:
                db = SessionLocal()
                try:
                    row = db.get(OperationalAnalysisModel, analysis.id)
                    row_data = self._analysis_to_row(analysis)
                    if row is None:
                        row = OperationalAnalysisModel(**row_data)
                        db.add(row)
                    else:
                        for k, v in row_data.items():
                            setattr(row, k, v)
                    db.commit()
                    logger.debug(f"✅ Análisis operativo guardado: {analysis.id}")
                    self._publish_progress_update(analysis)
                    return analysis
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"❌ Error guardando análisis operativo {analysis.id}: {e}", exc_info=True)
                raise

    def obtener_analisis(self, analysis_id: str) -> Optional[OperationalAnalysis]:
        """Obtiene un análisis por ID"""
        db = SessionLocal()
        try:
            row = db.get(OperationalAnalysisModel, analysis_id)
            if row is None:
                return None
            return self._row_to_analysis(row)
        finally:
            db.close()

    def listar_analisis(self, limit: int = 50, analysis_type: str = None) -> List[OperationalAnalysis]:
        """Lista análisis ordenados por fecha de creación, opcionalmente filtrados por tipo"""
        db = SessionLocal()
        try:
            query = db.query(OperationalAnalysisModel)
            if analysis_type:
                query = query.filter(OperationalAnalysisModel.analysis_type == analysis_type)
            rows = (
                query.order_by(OperationalAnalysisModel.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._row_to_analysis(r) for r in rows]
        finally:
            db.close()

    def listar_analisis_por_usuario(
        self,
        usuario: str,
        analysis_type: str = None,
        limit: int = 50,
    ) -> List[OperationalAnalysis]:
        """Lista análisis de un usuario específico, con filtro de tipo opcional."""
        db = SessionLocal()
        try:
            query = db.query(OperationalAnalysisModel).filter(
                OperationalAnalysisModel.usuario == usuario
            )
            if analysis_type:
                query = query.filter(OperationalAnalysisModel.analysis_type == analysis_type)
            rows = (
                query.order_by(OperationalAnalysisModel.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._row_to_analysis(r) for r in rows]
        finally:
            db.close()

    def eliminar_analisis(self, analysis_id: str) -> bool:
        """Elimina un análisis y sus eventos asociados."""
        self.eliminar_eventos_by_analysis_id(analysis_id)
        db = SessionLocal()
        try:
            row = db.get(OperationalAnalysisModel, analysis_id)
            if row:
                db.delete(row)
                db.commit()
            logger.info(f"✅ Análisis eliminado: {analysis_id}")
            return True
        finally:
            db.close()

    def eliminar_eventos_by_analysis_id(self, analysis_id: str) -> int:
        """Elimina todos los eventos de un análisis. Retorna el número total eliminados."""
        db = SessionLocal()
        try:
            count = (
                db.query(OperationalEventModel)
                .filter(OperationalEventModel.analysis_id == analysis_id)
                .delete(synchronize_session=False)
            )
            db.commit()
            return count
        finally:
            db.close()

    # ═══════════════════════════════════════════════════
    # EVENTOS
    # ═══════════════════════════════════════════════════

    def guardar_eventos_batch(self, eventos: List[OperationalEvent], analysis_id: str) -> int:
        """Elimina eventos viejos, inserta nuevos en batch, y actualiza el análisis."""
        with self._lock_repo:
            try:
                db = SessionLocal()
                try:
                    self.eliminar_eventos_by_analysis_id(analysis_id)

                    BATCH_SIZE = 450
                    total_guardados = 0

                    for i in range(0, len(eventos), BATCH_SIZE):
                        chunk = eventos[i:i + BATCH_SIZE]
                        mappings = [self._event_to_row(ev, analysis_id) for ev in chunk]
                        db.bulk_insert_mappings(OperationalEventModel, mappings)
                        db.commit()
                        total_guardados += len(chunk)

                    analysis = self.obtener_analisis(analysis_id)
                    if analysis:
                        for evento in eventos:
                            analysis.agregar_evento(evento.id)
                        self.guardar_analisis(analysis)

                    return total_guardados
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"❌ Error en guardar_eventos_batch para {analysis_id}: {e}", exc_info=True)
                raise

    def obtener_eventos(self, analysis_id: str) -> List[OperationalEvent]:
        """Obtiene todos los eventos de un análisis, ordenados por timestamp_start."""
        db = SessionLocal()
        try:
            rows = (
                db.query(OperationalEventModel)
                .filter(OperationalEventModel.analysis_id == analysis_id)
                .order_by(OperationalEventModel.timestamp_start.asc())
                .all()
            )
            return [self._row_to_event(r) for r in rows]
        finally:
            db.close()

    def obtener_eventos_paginados(
        self,
        analysis_id: str,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple:
        """
        Obtiene eventos paginados de un análisis.
        Returns: tuple(events, total)
        """
        page = max(1, min(20, int(page)))
        per_page = max(1, int(per_page))
        offset = (page - 1) * per_page

        db = SessionLocal()
        try:
            total = (
                db.query(OperationalEventModel)
                .filter(OperationalEventModel.analysis_id == analysis_id)
                .count()
            )
            if total <= offset:
                return [], total

            rows = (
                db.query(OperationalEventModel)
                .filter(OperationalEventModel.analysis_id == analysis_id)
                .order_by(OperationalEventModel.timestamp_start.asc())
                .offset(offset)
                .limit(per_page)
                .all()
            )
            return [self._row_to_event(r) for r in rows], total
        finally:
            db.close()

    def contar_eventos(self, analysis_id: str) -> int:
        """Cuenta eventos de un análisis."""
        db = SessionLocal()
        try:
            return (
                db.query(OperationalEventModel)
                .filter(OperationalEventModel.analysis_id == analysis_id)
                .count()
            )
        finally:
            db.close()

    def iter_event_timestamps(self, analysis_id: str, batch_size: int = 1000):
        """Itera timestamps de eventos en lotes para agregaciones sin cargar todo en memoria."""
        batch_size = max(100, min(5000, int(batch_size)))
        db = SessionLocal()
        try:
            offset = 0
            while True:
                rows = (
                    db.query(OperationalEventModel.timestamp_start)
                    .filter(OperationalEventModel.analysis_id == analysis_id)
                    .order_by(OperationalEventModel.timestamp_start.asc(), OperationalEventModel.id.asc())
                    .offset(offset)
                    .limit(batch_size)
                    .all()
                )
                if not rows:
                    break
                for row in rows:
                    yield float(row.timestamp_start or 0)
                if len(rows) < batch_size:
                    break
                offset += batch_size
        finally:
            db.close()

    def obtener_eventos_cursor(
        self,
        analysis_id: str,
        cursor: Optional[str] = None,
        per_page: int = 20,
    ) -> tuple:
        """
        Obtiene eventos con cursor estable (timestamp_start + id).
        Returns: tuple(events, next_cursor, total)
        """
        per_page = max(1, int(per_page))

        db = SessionLocal()
        try:
            query = (
                db.query(OperationalEventModel)
                .filter(OperationalEventModel.analysis_id == analysis_id)
                .order_by(OperationalEventModel.timestamp_start.asc(), OperationalEventModel.id.asc())
            )

            if cursor:
                try:
                    decoded = json.loads(
                        base64.urlsafe_b64decode(cursor.encode('utf-8')).decode('utf-8')
                    )
                    target_ts = decoded.get('timestamp_start', 0)
                    target_id = decoded.get('id', '')
                    query = query.filter(
                        (
                            (OperationalEventModel.timestamp_start > target_ts)
                            | (
                                (OperationalEventModel.timestamp_start == target_ts)
                                & (OperationalEventModel.id > target_id)
                            )
                        )
                    )
                except Exception:
                    raise ValueError('cursor inválido')

            rows = query.limit(per_page + 1).all()
            has_more = len(rows) > per_page
            page_rows = rows[:per_page]

            events = [self._row_to_event(r) for r in page_rows]

            next_cursor = None
            if has_more and page_rows:
                last = page_rows[-1]
                cursor_payload = {
                    'timestamp_start': last.timestamp_start or 0,
                    'id': last.id,
                }
                next_cursor = base64.urlsafe_b64encode(
                    json.dumps(cursor_payload, separators=(',', ':')).encode('utf-8')
                ).decode('utf-8')

            total = (
                db.query(OperationalEventModel)
                .filter(OperationalEventModel.analysis_id == analysis_id)
                .count()
            )
            return events, next_cursor, total
        finally:
            db.close()
