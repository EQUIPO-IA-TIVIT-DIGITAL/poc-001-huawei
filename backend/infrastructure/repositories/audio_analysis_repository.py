"""
Repositorio local (PostgreSQL + SQLAlchemy + pgvector) para Análisis de Audio

Tablas:
- audio_analyses: Análisis principales (id, usuario, estado, s3_uri, language, result JSON)
- audio_segments: Segmentos de transcripción con timestamps y embedding pgvector

Patrón: Singleton con RLock (thread-safe) — mismo patrón que OperationalAnalysisRepository.
"""

import logging
from typing import Optional, List, Tuple, Dict, Any
from threading import RLock
import re
import json

from sqlalchemy import select, delete

from domain.entities import AudioAnalysis, AudioSegment, EstadoAudioAnalysis
from infrastructure.db.session import SessionLocal
from infrastructure.db.models import AudioAnalysisModel, AudioSegmentModel

logger = logging.getLogger(__name__)


def _to_embedding_list(vector) -> Optional[List[float]]:
    """Convierte cualquier objeto vectorial (legacy, lista, tupla) a lista de floats."""
    if vector is None:
        return None
    if isinstance(vector, (list, tuple)):
        return [float(x) for x in vector]
    for attr in ('values', 'list', 'to_list'):
        if hasattr(vector, attr):
            val = getattr(vector, attr)
            if callable(val):
                val = val()
            return [float(x) for x in val]
    try:
        return [float(x) for x in vector]
    except Exception:
        return None


def _analysis_model_to_entity(m: AudioAnalysisModel) -> AudioAnalysis:
    """Reconstruye AudioAnalysis desde el modelo, tolerando campos faltantes."""
    data: Dict[str, Any] = {}
    if m.result:
        data.update(m.result)
    data['id'] = data.get('id') or m.id
    data['usuario'] = data.get('usuario') or (m.usuario or '')
    data['estado'] = data.get('estado') or (m.estado or 'pending')
    data['detected_language'] = data.get('detected_language') or (m.language or 'es')
    return AudioAnalysis.from_dict(data)


def _segment_model_to_entity(m: AudioSegmentModel) -> AudioSegment:
    """Reconstruye AudioSegment desde el modelo."""
    d = {
        'id': m.id,
        'analysis_id': m.analysis_id,
        'text': m.text or '',
        'start_time': m.start_time if m.start_time is not None else 0.0,
        'end_time': m.end_time if m.end_time is not None else 0.0,
        'speaker': m.speaker or '',
    }
    if m.embedding is not None:
        d['embedding'] = list(m.embedding)
    return AudioSegment.from_dict(d)


class AudioAnalysisRepository:
    """Repositorio local (PostgreSQL/SQLAlchemy + pgvector) para análisis de audio (Singleton thread-safe)"""

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
        try:
            conn = SessionLocal()
            conn.execute(select(1))
            conn.close()
            logger.info("✅ AudioAnalysisRepository inicializado (PostgreSQL + SQLAlchemy + pgvector)")
        except Exception as e:
            logger.error(f"❌ Error inicializando sesión SQLAlchemy: {e}")
            logger.info("✅ AudioAnalysisRepository inicializado (session lazy)")
        self._initialized = True

    # ═══════════════════════════════════════════════════
    # HELPERS: REDIS CACHE + PUB/SUB (SCA-01, SCA-04, OPT-03)
    # ═══════════════════════════════════════════════════

    _CACHE_TTL_COMPLETED = 600   # 10 min — análisis completados (inmutables)
    _CACHE_TTL_IN_PROGRESS = 10  # 10 s  — análisis en progreso

    def _get_cache(self, analysis_id: str) -> Optional['AudioAnalysis']:
        """Intenta obtener análisis desde Redis cache (SCA-04)."""
        try:
            from infrastructure.services.job_queue import get_redis_connection
            raw = get_redis_connection().get(f"audio:analysis:{analysis_id}")
            if raw:
                return AudioAnalysis.from_dict(json.loads(raw))
        except Exception:
            pass
        return None

    def _set_cache(self, analysis: 'AudioAnalysis') -> None:
        """Guarda análisis en Redis cache con TTL según estado (SCA-04)."""
        try:
            from infrastructure.services.job_queue import get_redis_connection
            ttl = (
                self._CACHE_TTL_COMPLETED
                if analysis.estado == EstadoAudioAnalysis.COMPLETED
                else self._CACHE_TTL_IN_PROGRESS
            )
            get_redis_connection().setex(
                f"audio:analysis:{analysis.id}",
                ttl,
                json.dumps(analysis.to_dict(), default=str),
            )
        except Exception:
            pass

    def _invalidar_cache(self, analysis_id: str) -> None:
        """Elimina análisis del Redis cache."""
        try:
            from infrastructure.services.job_queue import get_redis_connection
            get_redis_connection().delete(f"audio:analysis:{analysis_id}")
        except Exception:
            pass

    def _publicar_estado_redis(self, analysis_id: str, data: dict) -> None:
        """Publica cambio de estado en canal Redis para notificar al stream SSE (SCA-01)."""
        try:
            from infrastructure.services.job_queue import get_redis_connection
            get_redis_connection().publish(
                f"audio:status:{analysis_id}",
                json.dumps(data, default=str),
            )
        except Exception:
            pass

    def actualizar_progreso_parcial(
        self,
        analysis_id: str,
        estado,
        phase: str,
        progress: float,
        error_msg: str = "",
    ) -> None:
        """Actualiza solo los campos de progreso (estado/current_phase/progress) sin reescritura completa (OPT-03)."""
        data: Dict[str, Any] = {
            'estado': estado.value if hasattr(estado, 'value') else estado,
            'current_phase': phase,
            'progress': progress,
        }
        if error_msg:
            data['error_message'] = error_msg
        with self._lock_repo:
            try:
                db = SessionLocal()
                try:
                    m = db.get(AudioAnalysisModel, analysis_id)
                    if m is not None:
                        result = dict(m.result or {})
                        if 'estado' in data:
                            m.estado = str(data['estado'])
                        if 'current_phase' in data:
                            result['current_phase'] = data['current_phase']
                        if 'progress' in data:
                            result['progress'] = data['progress']
                        if 'error_message' in data:
                            result['error_message'] = data['error_message']
                        m.result = result
                        db.commit()
                    else:
                        logger.warning(f"⚠️ update parcial falló para {analysis_id}: no existe fila")
                finally:
                    db.close()
            except Exception as e:
                logger.warning(f"⚠️ update parcial falló para {analysis_id}: {e}")
            self._invalidar_cache(analysis_id)
            self._publicar_estado_redis(analysis_id, data)

    # ═══════════════════════════════════════════════════
    # ANÁLISIS
    # ═══════════════════════════════════════════════════

    def guardar_analisis(self, analysis: AudioAnalysis) -> AudioAnalysis:
        """Guarda o actualiza un análisis de audio"""
        with self._lock_repo:
            try:
                data_dict = analysis.to_dict()
                new_estado = str(data_dict.get('estado', 'pending'))
                db = SessionLocal()
                try:
                    m = db.get(AudioAnalysisModel, analysis.id)
                    if m is None:
                        m = AudioAnalysisModel(id=analysis.id)
                        db.add(m)
                    m.usuario = data_dict.get('usuario', '')
                    m.estado = new_estado
                    m.language = str(data_dict.get('detected_language', 'es') or 'es')[:16]
                    m.result = data_dict
                    db.commit()
                finally:
                    db.close()
                logger.debug(f"✅ Análisis de audio guardado: {analysis.id} (estado={new_estado})")
                self._invalidar_cache(analysis.id)
                self._publicar_estado_redis(analysis.id, {
                    'estado': new_estado,
                    'current_phase': data_dict.get('current_phase'),
                    'progress': data_dict.get('progress'),
                    'error_message': data_dict.get('error_message'),
                })
                return analysis
            except Exception as e:
                logger.error(f"❌ Error guardando análisis de audio {analysis.id}: {e}", exc_info=True)
                raise

    def obtener_analisis(self, analysis_id: str) -> Optional[AudioAnalysis]:
        """Obtiene un análisis por ID (con Redis cache — SCA-04)"""
        cached = self._get_cache(analysis_id)
        if cached is not None:
            return cached
        with self._lock_repo:
            db = SessionLocal()
            try:
                m = db.get(AudioAnalysisModel, analysis_id)
                if m is not None:
                    analysis = _analysis_model_to_entity(m)
                    self._set_cache(analysis)
                    return analysis
                return None
            finally:
                db.close()

    def listar_analisis_por_usuario(
        self,
        usuario: str,
        limit: int = 50
    ) -> List[AudioAnalysis]:
        """Lista análisis de un usuario específico, ordenados por fecha (created_at DESC)."""
        with self._lock_repo:
            db = SessionLocal()
            try:
                rows = (
                    db.query(AudioAnalysisModel)
                    .filter(AudioAnalysisModel.usuario == usuario)
                    .order_by(AudioAnalysisModel.created_at.desc())
                    .limit(limit)
                    .all()
                )
                return [_analysis_model_to_entity(r) for r in rows]
            finally:
                db.close()

    def eliminar_analisis(self, analysis_id: str) -> bool:
        """Elimina un análisis y sus segmentos (OPT-06)."""
        with self._lock_repo:
            db = SessionLocal()
            try:
                total_segs = (
                    db.query(AudioSegmentModel)
                    .filter(AudioSegmentModel.analysis_id == analysis_id)
                    .count()
                )
                db.execute(
                    delete(AudioSegmentModel).where(AudioSegmentModel.analysis_id == analysis_id)
                )
                m = db.get(AudioAnalysisModel, analysis_id)
                if m is not None:
                    db.delete(m)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"❌ Error eliminando análisis {analysis_id}: {e}")
                return False
            finally:
                db.close()
            self._invalidar_cache(analysis_id)
            logger.info(f"✅ Análisis de audio eliminado: {analysis_id} ({total_segs} segmentos)")
            return True

    # ═══════════════════════════════════════════════════
    # SEGMENTOS DE TRANSCRIPCIÓN
    # ═══════════════════════════════════════════════════

    def guardar_segmentos_batch(self, segmentos: List[AudioSegment], analysis_id: str) -> int:
        """Guarda segmentos de transcripción en batch (upsert por PK)."""
        with self._lock_repo:
            total_guardados = 0
            db = SessionLocal()
            try:
                for segmento in segmentos:
                    m = db.get(AudioSegmentModel, segmento.id)
                    if m is None:
                        m = AudioSegmentModel(id=segmento.id)
                        db.add(m)
                    m.analysis_id = analysis_id
                    m.start_time = float(segmento.start_time or 0.0)
                    m.end_time = float(segmento.end_time or 0.0)
                    m.text = segmento.text or ''
                    m.speaker = (segmento.speaker or 'SPEAKER_1')[:64]
                    embedding = getattr(segmento, 'embedding', None)
                    m.embedding = _to_embedding_list(embedding)
                    total_guardados += 1
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
            return total_guardados

    def obtener_segmentos(self, analysis_id: str) -> List[AudioSegment]:
        """Obtiene todos los segmentos de un análisis, ordenados por timestamp."""
        with self._lock_repo:
            rows = self._query_segmentos_ordenados(analysis_id)
            segments = [_segment_model_to_entity(r) for r in rows]
            segments.sort(key=lambda s: (s.start_time, s.id))
            return segments

    def obtener_segmentos_paginados(
        self,
        analysis_id: str,
        page: int = 1,
        per_page: int = 50,
        cursor: Optional[str] = None,
    ) -> Tuple[List[AudioSegment], int, Optional[str]]:
        """
        Obtiene segmentos paginados de un análisis.

        Returns:
            tuple: (segments: List[AudioSegment], total: int, next_cursor: Optional[str])
        """
        with self._lock_repo:
            per_page = max(1, min(per_page, 200))
            db = SessionLocal()
            try:
                q = (
                    db.query(AudioSegmentModel)
                    .filter(AudioSegmentModel.analysis_id == analysis_id)
                    .order_by(AudioSegmentModel.start_time.asc(), AudioSegmentModel.id.asc())
                )

                if cursor:
                    try:
                        start_time_raw, last_id = cursor.split('|', 1)
                        start_time = float(start_time_raw)
                        q = q.filter(
                            (AudioSegmentModel.start_time > start_time)
                            | (
                                (AudioSegmentModel.start_time == start_time)
                                & (AudioSegmentModel.id > last_id)
                            )
                        )
                    except Exception:
                        logger.warning(f"⚠️ Cursor inválido para análisis {analysis_id}: {cursor}")
                elif page and page > 1:
                    q = q.offset((page - 1) * per_page)

                rows = q.limit(per_page).all()
                segments = [_segment_model_to_entity(r) for r in rows]
            finally:
                db.close()

            total = self._obtener_total_segmentos(analysis_id)

            next_cursor = None
            if len(segments) == per_page:
                last = segments[-1]
                next_cursor = f"{last.start_time}|{last.id}"

            return segments, total, next_cursor

    def buscar_en_segmentos(
        self,
        segmentos: List[AudioSegment],
        query: str,
        limit: int = 200,
    ) -> List[AudioSegment]:
        """Busca texto en una lista de segmentos ya cargados (sin roundtrip a DB)."""
        query_lower = query.lower()
        limit = max(1, min(limit, 1000))

        matching = []
        for seg in segmentos:
            if query_lower in seg.text.lower():
                matching.append(seg)
                if len(matching) >= limit:
                    break
        matching.sort(key=lambda s: s.start_time)
        return matching

    def buscar_en_transcripcion(self, analysis_id: str, query: str, limit: int = 200) -> List[AudioSegment]:
        """
        Busca texto en los segmentos de transcripción de un análisis.
        Búsqueda case-insensitive (no hay full-text search nativo; similar a Firestore).

        Args:
            analysis_id: ID del análisis
            query: Texto a buscar

        Args:
            limit: Máximo de coincidencias a retornar

        Returns:
            Lista de segmentos que contienen el texto buscado
        """
        with self._lock_repo:
            query_lower = query.lower()
            limit = max(1, min(limit, 1000))
            db = SessionLocal()
            try:
                rows = (
                    db.query(AudioSegmentModel)
                    .filter(
                        AudioSegmentModel.analysis_id == analysis_id,
                        AudioSegmentModel.text.ilike(f"%{query_lower}%"),
                    )
                    .order_by(AudioSegmentModel.start_time.asc())
                    .limit(limit)
                    .all()
                )
                return [_segment_model_to_entity(r) for r in rows]
            except Exception as e:
                logger.warning(f"⚠️ Búsqueda SQL falló para {analysis_id}, fallback en memoria: {e}")
                all_segments = self.obtener_segmentos(analysis_id)
                matching: List[AudioSegment] = []
                for segment in all_segments:
                    if query_lower in segment.text.lower():
                        matching.append(segment)
                        if len(matching) >= limit:
                            break
                return matching
            finally:
                db.close()

    def _query_segmentos_ordenados(self, analysis_id: str):
        db = SessionLocal()
        try:
            return (
                db.query(AudioSegmentModel)
                .filter(AudioSegmentModel.analysis_id == analysis_id)
                .order_by(AudioSegmentModel.start_time.asc(), AudioSegmentModel.id.asc())
                .all()
            )
        finally:
            db.close()

    @staticmethod
    def _extract_search_terms(query: str) -> List[str]:
        terms = re.findall(r"[a-zA-Z0-9áéíóúÁÉÍÓÚñÑüÜ]{3,}", query.lower())
        unique = []
        seen = set()
        for t in terms:
            if t in seen:
                continue
            seen.add(t)
            unique.append(t)
            if len(unique) >= 10:
                break
        return unique

    def _obtener_total_segmentos(self, analysis_id: str) -> int:
        """Obtiene total de segmentos usando el documento principal como fuente rápida, con fallback a count."""
        try:
            m = self._get_analysis_model(analysis_id)
            if m is not None:
                result = m.result or {}
                total = result.get('total_segments', 0) or 0
                if total > 0:
                    return int(total)
        except Exception:
            pass

        try:
            db = SessionLocal()
            try:
                return (
                    db.query(AudioSegmentModel)
                    .filter(AudioSegmentModel.analysis_id == analysis_id)
                    .count()
                )
            finally:
                db.close()
        except Exception:
            return 0

    def _get_analysis_model(self, analysis_id: str) -> Optional[AudioAnalysisModel]:
        try:
            db = SessionLocal()
            try:
                return db.get(AudioAnalysisModel, analysis_id)
            finally:
                db.close()
        except Exception:
            return None

    # ═══════════════════════════════════════════════════
    # VECTOR SEARCH (OPT-07)
    # ═══════════════════════════════════════════════════

    def actualizar_embedding_segmento(
        self, analysis_id: str, segment_id: str, vector
    ) -> None:
        """Guarda el embedding vectorial en la columna pgvector 'embedding' del segmento."""
        with self._lock_repo:
            db = SessionLocal()
            try:
                m = db.get(AudioSegmentModel, segment_id)
                if m is None:
                    m = AudioSegmentModel(
                        id=segment_id,
                        analysis_id=analysis_id,
                        start_time=0.0,
                        end_time=0.0,
                    )
                    db.add(m)
                else:
                    m.analysis_id = analysis_id
                m.embedding = _to_embedding_list(vector)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.warning(f"⚠️ Error actualizando embedding de segmento {segment_id}: {e}")
            finally:
                db.close()

    def buscar_por_vector(
        self,
        analysis_id: str,
        vector,
        distance_measure,
        limit: int = 20,
    ) -> List[AudioSegment]:
        """
        Búsqueda semántica por similaridad vectorial con cosine distance (pgvector `<=>`).
        Filtra por analysis_id para limitar el espacio de búsqueda.
        Retorna lista vacía si no hay embeddings o el query no se puede ejecutar.
        """
        query_embedding = _to_embedding_list(vector)
        if not query_embedding:
            return []
        with self._lock_repo:
            try:
                db = SessionLocal()
                try:
                    distance = self._build_distance_expr(
                        AudioSegmentModel.embedding, query_embedding, distance_measure
                    )
                    stmt = (
                        select(AudioSegmentModel)
                        .where(
                            AudioSegmentModel.analysis_id == analysis_id,
                            AudioSegmentModel.embedding.isnot(None),
                            distance < 1.0,
                        )
                        .order_by(distance.asc())
                        .limit(limit)
                    )
                    rows = db.execute(stmt).scalars().all()
                    return [_segment_model_to_entity(r) for r in rows]
                finally:
                    db.close()
            except Exception as e:
                logger.warning(f"⚠️ buscar_por_vector error ({str(analysis_id)[:8]}): {e}")
                return []

    @staticmethod
    def _build_distance_expr(embedding_col, query_embedding: List[float], distance_measure):
        """Mapea DistanceMeasure legacy (COSINE/EUCLIDEAN/DOT_PRODUCT) al operador pgvector."""
        measure = None
        if isinstance(distance_measure, str):
            measure = distance_measure.upper()
        elif hasattr(distance_measure, 'name'):
            measure = str(distance_measure.name).upper()
        elif hasattr(distance_measure, 'value'):
            measure = str(distance_measure.value).upper()
        if measure in ('EUCLIDIAN', 'EUCLIDEAN', 'L2'):
            return embedding_col.l2_distance(query_embedding)
        if measure in ('DOT_PRODUCT', 'INNER_PRODUCT', 'DOT'):
            return embedding_col.inner_product(query_embedding)
        return embedding_col.cosine_distance(query_embedding)