"""
Repositorio Firestore para Análisis Operativo

Colecciones:
- operational_analyses: Análisis principales
- operational_events: Eventos individuales detectados

Patrón: Singleton con RLock (thread-safe) — mismo patrón que SecurityVideoRepository.
"""

import logging
import json
import base64
from typing import Optional, List
from threading import RLock
from google.cloud import firestore

from domain.entities import OperationalAnalysis, OperationalEvent

logger = logging.getLogger(__name__)


class OperationalAnalysisRepository:
    """Repositorio Firestore para análisis operativos (Singleton thread-safe)"""

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
        from config.gcp_config import GCPConfig
        gcp_config = GCPConfig()
        try:
            self.db = firestore.Client(project=gcp_config.PROJECT_ID)
            logger.info(f"✅ OperationalAnalysisRepository inicializado (Firestore project={gcp_config.PROJECT_ID})")
        except Exception as e:
            logger.error(f"❌ Error inicializando Firestore client: {e}")
            # Fallback sin project_id especificado
            self.db = firestore.Client()
            logger.info("✅ OperationalAnalysisRepository inicializado (Firestore sin project_id)")
        self._initialized = True

    # ═══════════════════════════════════════════════════
    # ANÁLISIS
    # ═══════════════════════════════════════════════════

    def guardar_analisis(self, analysis: OperationalAnalysis) -> OperationalAnalysis:
        """Guarda o actualiza un análisis operativo"""
        with self._lock_repo:
            try:
                doc_ref = self.db.collection('operational_analyses').document(analysis.id)
                data_dict = analysis.to_dict()
                doc_ref.set(data_dict)
                logger.debug(f"✅ Análisis operativo guardado: {analysis.id} (estado={analysis.estado.value if hasattr(analysis.estado, 'value') else analysis.estado})")
                self._publish_progress_update(analysis)
                return analysis
            except Exception as e:
                logger.error(f"❌ Error guardando análisis operativo {analysis.id}: {e}", exc_info=True)
                raise

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
            # No bloquear persistencia por fallas en publicación de progreso.
            pass

    def obtener_analisis(self, analysis_id: str) -> Optional[OperationalAnalysis]:
        """Obtiene un análisis por ID"""
        doc_ref = self.db.collection('operational_analyses').document(analysis_id)
        doc = doc_ref.get()
        if doc.exists:
            return OperationalAnalysis.from_dict(doc.to_dict())
        return None

    def listar_analisis(self, limit: int = 50, analysis_type: str = None) -> List[OperationalAnalysis]:
        """Lista análisis ordenados por fecha de creación, opcionalmente filtrados por tipo"""
        query = self.db.collection('operational_analyses')
        if analysis_type:
            query = query.where(
                filter=firestore.FieldFilter('analysis_type', '==', analysis_type)
            )
        docs = (
            query
            .order_by('created_at', direction=firestore.Query.DESCENDING)
            .limit(limit)
            .get()
        )
        return [OperationalAnalysis.from_dict(doc.to_dict()) for doc in docs]

    def listar_analisis_por_usuario(
        self,
        usuario: str,
        analysis_type: str = None,
        limit: int = 50
    ) -> List[OperationalAnalysis]:
        """Lista análisis de un usuario específico, con filtro de tipo opcional.
        
        Incluye fallback sin order_by si el índice compuesto no existe aún.
        """
        try:
            query = self.db.collection('operational_analyses').where(
                filter=firestore.FieldFilter('usuario', '==', usuario)
            )
            if analysis_type:
                query = query.where(
                    filter=firestore.FieldFilter('analysis_type', '==', analysis_type)
                )
            docs = (
                query
                .order_by('created_at', direction=firestore.Query.DESCENDING)
                .limit(limit)
                .get()
            )
            return [OperationalAnalysis.from_dict(doc.to_dict()) for doc in docs]
        except Exception as e:
            if 'index' in str(e).lower():
                logger.warning(f"⚠️ Índice compuesto no disponible, usando fallback: {e}")
                # Fallback: query sin order_by, ordenar en memoria
                query = self.db.collection('operational_analyses').where(
                    filter=firestore.FieldFilter('usuario', '==', usuario)
                )
                if analysis_type:
                    query = query.where(
                        filter=firestore.FieldFilter('analysis_type', '==', analysis_type)
                    )
                docs = query.limit(limit).get()
                results = [OperationalAnalysis.from_dict(doc.to_dict()) for doc in docs]
                results.sort(key=lambda a: a.created_at or '', reverse=True)
                return results[:limit]
            raise

    def eliminar_analisis(self, analysis_id: str) -> bool:
        """Elimina un análisis y sus eventos asociados en batches para evitar límite de 500 ops."""
        self.eliminar_eventos_by_analysis_id(analysis_id)
        self.db.collection('operational_analyses').document(analysis_id).delete()
        logger.info(f"✅ Análisis eliminado: {analysis_id}")
        return True

    def eliminar_eventos_by_analysis_id(self, analysis_id: str) -> int:
        """Elimina todos los eventos de un análisis en batches (máx 450 por batch).

        Retorna el número total de eventos eliminados.
        """
        BATCH_SIZE = 450
        total = 0
        while True:
            docs = (
                self.db.collection('operational_events')
                .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
                .limit(BATCH_SIZE)
                .get()
            )
            if not docs:
                break
            batch = self.db.batch()
            for doc in docs:
                batch.delete(doc.reference)
            batch.commit()
            total += len(docs)
            if len(docs) < BATCH_SIZE:
                break
        return total

    # ═══════════════════════════════════════════════════
    # EVENTOS (batch writes como SecurityVideoRepository)
    # ═══════════════════════════════════════════════════

    def guardar_eventos_batch(self, eventos: List[OperationalEvent], analysis_id: str) -> int:
        """Guarda eventos en batch (Firestore WriteBatch, max 450 por batch)"""
        with self._lock_repo:
            total_guardados = 0
            BATCH_SIZE = 450

            for i in range(0, len(eventos), BATCH_SIZE):
                chunk = eventos[i:i + BATCH_SIZE]
                batch = self.db.batch()

                for evento in chunk:
                    doc_ref = self.db.collection('operational_events').document(evento.id)
                    batch.set(doc_ref, evento.to_dict())

                batch.commit()
                total_guardados += len(chunk)

            # Actualizar análisis con IDs de eventos
            analysis = self.obtener_analisis(analysis_id)
            if analysis:
                for evento in eventos:
                    analysis.agregar_evento(evento.id)
                self.guardar_analisis(analysis)

            return total_guardados

    def obtener_eventos(self, analysis_id: str) -> List[OperationalEvent]:
        """Obtiene todos los eventos de un análisis, ordenados por timestamp"""
        docs = (
            self.db.collection('operational_events')
            .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
            .get()
        )
        events = [OperationalEvent.from_dict(doc.to_dict()) for doc in docs]
        events.sort(key=lambda e: e.timestamp_start)
        return events

    def obtener_eventos_paginados(
        self,
        analysis_id: str,
        page: int = 1,
        per_page: int = 20
    ) -> tuple:
        """
        Obtiene eventos paginados de un análisis.
        
        Returns:
            tuple: (events: List[OperationalEvent], total: int)
        """
        page = max(1, min(20, int(page)))   # cap to prevent costly deep scans
        per_page = max(1, int(per_page))
        offset = (page - 1) * per_page

        base_query = (
            self.db.collection('operational_events')
            .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
        )

        total = self.contar_eventos(analysis_id)
        if total <= offset:
            return [], total

        try:
            docs = (
                base_query
                .order_by('timestamp_start')
                .offset(offset)
                .limit(per_page)
                .get()
            )
            paginated = [OperationalEvent.from_dict(doc.to_dict()) for doc in docs]
            return paginated, total
        except Exception as e:
            if 'index' in str(e).lower() or 'failed_precondition' in str(e).lower():
                logger.warning(f"⚠️ Índice compuesto faltante en obtener_eventos_paginados, usando fallback en memoria: {e}")
                docs = base_query.get()
                all_events = [OperationalEvent.from_dict(doc.to_dict()) for doc in docs]
                all_events.sort(key=lambda x: x.timestamp_start)
                return all_events[offset:offset + per_page], total
            raise

    def contar_eventos(self, analysis_id: str) -> int:
        """Cuenta eventos de un análisis con fallback seguro si no hay aggregate count."""
        query = (
            self.db.collection('operational_events')
            .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
        )

        try:
            aggregate = query.count().get()
            if aggregate:
                return int(aggregate[0][0].value)
        except Exception:
            pass

        return len(query.get())

    def iter_event_timestamps(self, analysis_id: str, batch_size: int = 1000):
        """Itera timestamps de eventos en lotes para agregaciones sin cargar todo en memoria."""
        batch_size = max(100, min(5000, int(batch_size)))
        last_timestamp = None
        last_doc_id = None

        while True:
            query = (
                self.db.collection('operational_events')
                .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
                .order_by('timestamp_start')
                .order_by('id')
                .limit(batch_size)
            )

            if last_timestamp is not None and last_doc_id is not None:
                query = query.start_after({
                    'timestamp_start': last_timestamp,
                    'id': last_doc_id,
                })

            docs = query.get()
            if not docs:
                break

            for doc in docs:
                data = doc.to_dict() or {}
                ts = data.get('timestamp_start', 0)
                yield float(ts or 0)

            last_data = docs[-1].to_dict() or {}
            last_timestamp = last_data.get('timestamp_start', 0)
            last_doc_id = last_data.get('id', docs[-1].id)

    def obtener_eventos_cursor(
        self,
        analysis_id: str,
        cursor: Optional[str] = None,
        per_page: int = 20,
    ) -> tuple:
        """
        Obtiene eventos con cursor estable (timestamp_start + id).

        Returns:
            tuple: (events: List[OperationalEvent], next_cursor: Optional[str], total: int)
        """
        per_page = max(1, int(per_page))

        query = (
            self.db.collection('operational_events')
            .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
            .order_by('timestamp_start')
            .order_by('id')
        )

        if cursor:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor.encode('utf-8')).decode('utf-8'))
                query = query.start_after({
                    'timestamp_start': decoded.get('timestamp_start', 0),
                    'id': decoded.get('id', ''),
                })
            except Exception:
                raise ValueError('cursor inválido')

        try:
            docs = query.limit(per_page + 1).get()
            has_more = len(docs) > per_page
            page_docs = docs[:per_page]
            events = [OperationalEvent.from_dict(doc.to_dict()) for doc in page_docs]
        except Exception as e:
            if 'index' in str(e).lower() or 'failed_precondition' in str(e).lower():
                logger.warning(f"⚠️ Índice compuesto faltante en obtener_eventos_cursor, usando fallback en memoria: {e}")
                # Fallback en memoria
                base_query = self.db.collection('operational_events').where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
                all_docs = base_query.get()
                all_events = [OperationalEvent.from_dict(doc.to_dict()) for doc in all_docs]
                # sort locally
                all_events.sort(key=lambda x: (x.timestamp_start, x.id))
                
                # Apply cursor logic locally
                start_idx = 0
                if cursor:
                    try:
                        decoded = json.loads(base64.urlsafe_b64decode(cursor.encode('utf-8')).decode('utf-8'))
                        target_ts = decoded.get('timestamp_start', 0)
                        target_id = decoded.get('id', '')
                        for i, ev in enumerate(all_events):
                            if (ev.timestamp_start, ev.id) > (target_ts, target_id):
                                start_idx = i
                                break
                        else:
                            start_idx = len(all_events)
                    except Exception:
                        pass
                
                has_more = len(all_events) - start_idx > per_page
                page_events = all_events[start_idx:start_idx + per_page]
                events = page_events
                page_docs = page_events  # Need to mock page_docs so it has last_data correctly
                
            else:
                raise

        next_cursor = None
        if has_more and page_docs:
            last_data = page_docs[-1].to_dict() or {}
            cursor_payload = {
                'timestamp_start': last_data.get('timestamp_start', 0),
                'id': last_data.get('id', page_docs[-1].id),
            }
            next_cursor = base64.urlsafe_b64encode(
                json.dumps(cursor_payload, separators=(',', ':')).encode('utf-8')
            ).decode('utf-8')

        total = self.contar_eventos(analysis_id)
        return events, next_cursor, total
