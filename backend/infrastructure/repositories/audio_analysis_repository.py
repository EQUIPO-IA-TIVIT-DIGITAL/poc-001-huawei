"""
Repositorio Firestore para Análisis de Audio

Colecciones:
- audio_analyses: Análisis principales
- audio_segments: Segmentos de transcripción con timestamps

Patrón: Singleton con RLock (thread-safe) — mismo patrón que OperationalAnalysisRepository.
"""

import logging
from typing import Optional, List, Tuple, Dict, Any
from threading import RLock
from google.cloud import firestore
import re

from domain.entities import AudioAnalysis, AudioSegment

logger = logging.getLogger(__name__)


def _query_requires_index(error: Exception) -> bool:
    """Detecta errores de Firestore por índice compuesto faltante."""
    text = str(error).lower()
    return 'requires an index' in text or 'create_composite' in text or 'index' in text


class AudioAnalysisRepository:
    """Repositorio Firestore para análisis de audio (Singleton thread-safe)"""

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
            logger.info(f"✅ AudioAnalysisRepository inicializado (Firestore project={gcp_config.PROJECT_ID})")
        except Exception as e:
            logger.error(f"❌ Error inicializando Firestore client: {e}")
            # Fallback sin project_id especificado
            self.db = firestore.Client()
            logger.info("✅ AudioAnalysisRepository inicializado (Firestore sin project_id)")
        self._initialized = True

    # ═══════════════════════════════════════════════════
    # HELPERS: REDIS CACHE + PUB/SUB (SCA-01, SCA-04, OPT-03)
    # ═══════════════════════════════════════════════════

    _CACHE_TTL_COMPLETED = 600   # 10 min — análisis completados (inmutables)
    _CACHE_TTL_IN_PROGRESS = 10  # 10 s  — análisis en progreso

    def _get_cache(self, analysis_id: str) -> Optional['AudioAnalysis']:
        """Intenta obtener análisis desde Redis cache (SCA-04)."""
        try:
            import json
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
            import json
            from domain.entities import EstadoAudioAnalysis
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
            import json
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
        """Actualiza solo los campos de progreso en Firestore sin read-then-write (OPT-03)."""
        data: Dict[str, Any] = {
            'estado': estado.value if hasattr(estado, 'value') else estado,
            'current_phase': phase,
            'progress': progress,
        }
        if error_msg:
            data['error_message'] = error_msg
        with self._lock_repo:
            try:
                self.db.collection('audio_analyses').document(analysis_id).update(data)
            except Exception as e:
                logger.warning(f"⚠️ update parcial falló para {analysis_id}, usando set merge: {e}")
                self.db.collection('audio_analyses').document(analysis_id).set(data, merge=True)
            self._invalidar_cache(analysis_id)
            self._publicar_estado_redis(analysis_id, data)

    # ═══════════════════════════════════════════════════
    # ANÁLISIS
    # ═══════════════════════════════════════════════════

    def guardar_analisis(self, analysis: AudioAnalysis) -> AudioAnalysis:
        """Guarda o actualiza un análisis de audio"""
        with self._lock_repo:
            try:
                doc_ref = self.db.collection('audio_analyses').document(analysis.id)
                data_dict = analysis.to_dict()
                doc_ref.set(data_dict)
                logger.debug(f"✅ Análisis de audio guardado: {analysis.id} (estado={analysis.estado.value if hasattr(analysis.estado, 'value') else analysis.estado})")
                self._invalidar_cache(analysis.id)
                self._publicar_estado_redis(analysis.id, {
                    'estado': analysis.estado.value if hasattr(analysis.estado, 'value') else analysis.estado,
                    'current_phase': analysis.current_phase,
                    'progress': analysis.progress,
                    'error_message': analysis.error_message,
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
            doc_ref = self.db.collection('audio_analyses').document(analysis_id)
            doc = doc_ref.get()
            if doc.exists:
                analysis = AudioAnalysis.from_dict(doc.to_dict())
                self._set_cache(analysis)
                return analysis
            return None

    def listar_analisis_por_usuario(
        self,
        usuario: str,
        limit: int = 50
    ) -> List[AudioAnalysis]:
        """Lista análisis de un usuario específico, ordenados por fecha."""
        with self._lock_repo:
            try:
                query = self.db.collection('audio_analyses').where(
                    filter=firestore.FieldFilter('usuario', '==', usuario)
                )
                docs = (
                    query
                    .order_by('created_at', direction=firestore.Query.DESCENDING)
                    .limit(limit)
                    .get()
                )
                return [AudioAnalysis.from_dict(doc.to_dict()) for doc in docs]
            except Exception as e:
                if 'index' in str(e).lower():
                    from infrastructure.services.job_queue import is_queue_required
                    if is_queue_required():
                        logger.error(
                            f"❌ Índice Firestore compuesto faltante en audio_analyses "
                            f"(usuario, created_at DESC). Crear en Firebase Console. Error: {e}"
                        )
                    else:
                        logger.warning(f"⚠️ Índice compuesto no disponible, usando fallback: {e}")
                    query = self.db.collection('audio_analyses').where(
                        filter=firestore.FieldFilter('usuario', '==', usuario)
                    )
                    docs = query.limit(limit).get()
                    results = [AudioAnalysis.from_dict(doc.to_dict()) for doc in docs]
                    results.sort(key=lambda a: a.created_at or '', reverse=True)
                    return results[:limit]
                raise

    def eliminar_analisis(self, analysis_id: str) -> bool:
        """Elimina un análisis y sus segmentos usando batches seguros de 450 (OPT-06)"""
        with self._lock_repo:
            BATCH_SIZE = 450
            total_segs = 0

            # stream() evita cargar todos los docs en memoria; batches de 450 cumplen límite Firestore
            seg_iter = (
                self.db.collection('audio_segments')
                .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
                .stream()
            )
            chunk: list = []
            for seg_doc in seg_iter:
                chunk.append(seg_doc.reference)
                if len(chunk) >= BATCH_SIZE:
                    b = self.db.batch()
                    for ref in chunk:
                        b.delete(ref)
                    b.commit()
                    total_segs += len(chunk)
                    chunk = []

            # Último batch — incluir también el documento principal del análisis
            b = self.db.batch()
            for ref in chunk:
                b.delete(ref)
            total_segs += len(chunk)
            b.delete(self.db.collection('audio_analyses').document(analysis_id))
            b.commit()

            self._invalidar_cache(analysis_id)
            logger.info(f"✅ Análisis de audio eliminado: {analysis_id} ({total_segs} segmentos)")
            return True

    # ═══════════════════════════════════════════════════
    # SEGMENTOS DE TRANSCRIPCIÓN
    # ═══════════════════════════════════════════════════

    def guardar_segmentos_batch(self, segmentos: List[AudioSegment], analysis_id: str) -> int:
        """Guarda segmentos de transcripción en batch (max 450 por batch de Firestore)"""
        with self._lock_repo:
            total_guardados = 0
            BATCH_SIZE = 450

            for i in range(0, len(segmentos), BATCH_SIZE):
                chunk = segmentos[i:i + BATCH_SIZE]
                batch = self.db.batch()

                for segmento in chunk:
                    doc_ref = self.db.collection('audio_segments').document(segmento.id)
                    batch.set(doc_ref, segmento.to_dict())

                batch.commit()
                total_guardados += len(chunk)

            return total_guardados

    def obtener_segmentos(self, analysis_id: str) -> List[AudioSegment]:
        """Obtiene todos los segmentos de un análisis, ordenados por timestamp"""
        with self._lock_repo:
            docs = (
                self.db.collection('audio_segments')
                .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
                .get()
            )
            segments = [AudioSegment.from_dict(doc.to_dict()) for doc in docs]
            segments.sort(key=lambda s: s.start_time)
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

            try:
                query = (
                    self.db.collection('audio_segments')
                    .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
                    .order_by('start_time', direction=firestore.Query.ASCENDING)
                    .order_by('id', direction=firestore.Query.ASCENDING)
                )

                # Soporta dos modos:
                # 1) cursor-based (recomendado): cursor="<start_time>|<id>"
                # 2) page-based legacy: aplica offset para compatibilidad
                if cursor:
                    try:
                        start_time_raw, last_id = cursor.split('|', 1)
                        start_time = float(start_time_raw)
                        query = query.start_after({'start_time': start_time, 'id': last_id})
                    except Exception:
                        logger.warning(f"⚠️ Cursor inválido para análisis {analysis_id}: {cursor}")
                elif page and page > 1:
                    query = query.offset((page - 1) * per_page)

                docs = query.limit(per_page).get()
                segments = [AudioSegment.from_dict(doc.to_dict()) for doc in docs]
            except Exception as e:
                if not _query_requires_index(e):
                    raise

                from infrastructure.services.job_queue import is_queue_required
                if is_queue_required():
                    logger.error(
                        f"❌ Índice Firestore compuesto faltante en audio_segments "
                        f"(analysis_id, start_time ASC, id ASC). Crear en Firebase Console. "
                        f"Análisis: {analysis_id[:8]}. Error: {e}"
                    )
                else:
                    logger.warning(
                        f"⚠️ Índice compuesto no disponible para segmentos de {analysis_id}, "
                        f"usando fallback en memoria: {e}"
                    )
                docs = (
                    self.db.collection('audio_segments')
                    .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
                    .get()
                )
                all_segments = [AudioSegment.from_dict(doc.to_dict()) for doc in docs]
                all_segments.sort(key=lambda s: (s.start_time, s.id))

                start_idx = 0
                if cursor:
                    try:
                        start_time_raw, last_id = cursor.split('|', 1)
                        start_time = float(start_time_raw)
                        for i, seg in enumerate(all_segments):
                            if (seg.start_time, seg.id) > (start_time, last_id):
                                start_idx = i
                                break
                        else:
                            start_idx = len(all_segments)
                    except Exception:
                        logger.warning(f"⚠️ Cursor inválido para análisis {analysis_id}: {cursor}")
                elif page and page > 1:
                    start_idx = max(0, (page - 1) * per_page)

                segments = all_segments[start_idx:start_idx + per_page]

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
        """Busca texto en una lista de segmentos ya cargados (sin roundtrip a Firestore)."""
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
        Búsqueda case-insensitive en memoria (Firestore no soporta full-text search nativo).

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
            search_terms = self._extract_search_terms(query_lower)

            if search_terms:
                try:
                    docs = (
                        self.db.collection('audio_segments')
                        .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
                        .where(filter=firestore.FieldFilter('search_terms', 'array_contains_any', search_terms[:10]))
                        .order_by('start_time', direction=firestore.Query.ASCENDING)
                        .limit(min(limit * 20, 2000))
                        .stream()
                    )

                    matching: List[AudioSegment] = []
                    for doc in docs:
                        segment = AudioSegment.from_dict(doc.to_dict())
                        if query_lower in segment.text.lower():
                            matching.append(segment)
                            if len(matching) >= limit:
                                break

                    if matching:
                        return matching
                except Exception as e:
                    logger.warning(f"⚠️ Búsqueda indexada no disponible, fallback lineal: {e}")

            try:
                docs = (
                    self.db.collection('audio_segments')
                    .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
                    .order_by('start_time', direction=firestore.Query.ASCENDING)
                    .limit(min(limit * 20, 5000))
                    .stream()
                )

                matching: List[AudioSegment] = []
                for doc in docs:
                    segment = AudioSegment.from_dict(doc.to_dict())
                    if query_lower in segment.text.lower():
                        matching.append(segment)
                        if len(matching) >= limit:
                            break

                return matching
            except Exception as e:
                if not _query_requires_index(e):
                    raise

                logger.warning(
                    f"⚠️ Índice compuesto no disponible para búsqueda en {analysis_id}, "
                    f"usando fallback en memoria: {e}"
                )
                docs = (
                    self.db.collection('audio_segments')
                    .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
                    .get()
                )
                all_segments = [AudioSegment.from_dict(doc.to_dict()) for doc in docs]
                all_segments.sort(key=lambda s: (s.start_time, s.id))

                matching: List[AudioSegment] = []
                for segment in all_segments:
                    if query_lower in segment.text.lower():
                        matching.append(segment)
                        if len(matching) >= limit:
                            break
                return matching

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
        """Obtiene total de segmentos usando el documento principal como fuente rápida."""
        try:
            analysis_doc = self.db.collection('audio_analyses').document(analysis_id).get()
            if analysis_doc.exists:
                total = int((analysis_doc.to_dict() or {}).get('total_segments', 0) or 0)
                if total > 0:
                    return total
        except Exception:
            pass

        # Fallback para análisis antiguos sin total_segments — usa stream con select([])
        # para no cargar todos los campos en memoria, solo iterar document references.
        count = sum(
            1 for _ in (
                self.db.collection('audio_segments')
                .where(filter=firestore.FieldFilter('analysis_id', '==', analysis_id))
                .select([])
                .stream()
            )
        )
        return count

    # ═══════════════════════════════════════════════════
    # VECTOR SEARCH (OPT-07)
    # ═══════════════════════════════════════════════════

    def actualizar_embedding_segmento(
        self, analysis_id: str, segment_id: str, vector
    ) -> None:
        """Guarda el embedding vectorial en el campo 'embedding' del segmento."""
        with self._lock_repo:
            doc_ref = (
                self.db.collection('audio_segments')
                .document(f"{analysis_id}_{segment_id}")
            )
            doc_ref.set({"embedding": vector}, merge=True)

    def buscar_por_vector(
        self,
        analysis_id: str,
        vector,
        distance_measure,
        limit: int = 20,
    ) -> List[AudioSegment]:
        """
        Búsqueda semántica por similaridad vectorial en Firestore (find_nearest).
        Filtra por analysis_id para limitar el espacio de búsqueda.
        Retorna lista vacía si el índice no está disponible.
        """
        from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
        with self._lock_repo:
            try:
                collection = self.db.collection('audio_segments')
                vector_query = collection.where(
                    filter=firestore.FieldFilter('analysis_id', '==', analysis_id)
                ).find_nearest(
                    vector_field='embedding',
                    query_vector=vector,
                    distance_measure=distance_measure,
                    limit=limit,
                )
                results = [AudioSegment.from_dict(doc.to_dict()) for doc in vector_query.stream()]
                return results
            except Exception as e:
                logger.warning(f"⚠️ buscar_por_vector error ({analysis_id[:8]}): {e}")
                return []
