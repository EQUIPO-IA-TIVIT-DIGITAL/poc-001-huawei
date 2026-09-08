import os
import time
import uuid
import logging
import random
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore

from domain.entities import OperationalAnalysis, OperationalEvent
from infrastructure.adapters.gemini_operational_prompts import build_segment_prompt

logger = logging.getLogger(__name__)

class OperationalSegmentAnalyzer:
    """Fase 2: Análisis por segmento usando Gemini 2.5 con paralelismo y retry"""
    
    GEMINI_MAX_RETRIES = 3
    GEMINI_RETRY_DELAYS = [5, 15, 30]
    PARALLEL_WORKERS = 3
    CHECKPOINT_INTERVAL = 10
    MAX_CLIP_DURATION = 120
    CLIP_BUFFER_SECONDS = 3.0
    HD_RESOLUTION = (1280, 720)
    MAX_FRAMES_PER_SEGMENT = 5
    
    def __init__(self, gemini_adapter, storage_adapter, temp_dir: str):
        self.gemini_adapter = gemini_adapter
        self.storage_adapter = storage_adapter
        self.temp_dir = temp_dir
        
    def analyze_segments(
        self,
        analysis: OperationalAnalysis,
        vid: str,
        video_path: str,
        segments: list,
        detected_events_map: dict,
        progress_callback=None,
        check_cancelled=None
    ) -> tuple:
        total = len(segments)
        operational_events: List[OperationalEvent] = []
        segment_results: List[Dict] = []
        phase_start = time.time()
        gemini_semaphore = Semaphore(self.PARALLEL_WORKERS)
        failed_segments = 0

        logger.info(f"[{vid}] 🔬 Iniciando análisis de {total} segmentos "
                     f"(semi-paralelo, {self.PARALLEL_WORKERS} workers, retry={self.GEMINI_MAX_RETRIES})")

        def process_single_segment(idx: int, segment) -> dict:
            seg_num = idx + 1
            seg_start = time.time()

            detected_ev = detected_events_map.get(segment.start_second)
            ev_type = detected_ev.event_type if detected_ev else 'UNKNOWN'
            ev_priority = detected_ev.priority if detected_ev else '-'

            logger.info(f"[{vid}] 📊 ─── Segmento {seg_num}/{total} [{ev_type}/{ev_priority}] ───")

            result = {
                'idx': idx, 'seg_num': seg_num, 'success': False,
                'events': [], 'segment_result': None, 'ev_type': ev_type,
            }

            try:
                # 1. Extraer clip local con FFmpeg
                clip_path = self._extract_clip(
                    video_path, segment.start_second, segment.end_second,
                    os.path.join(self.temp_dir, f"op_clip_{idx}.mp4"), vid
                )

                if not clip_path:
                    logger.warning(f"[{vid}]    ⚠️ No se pudo extraer clip, saltando segmento")
                    return result

                # 1.5. Intentar subir el clip a GCS para pasarlo como gs:// URI a Gemini.
                # Vertex AI consume el video directamente desde GCS sin serializar frames
                # como base64 (~33% overhead), lo que reduce el payload y el uso de tokens.
                # Si GCS no está disponible se usa frames base64 como fallback.
                gcs_clip_uri = None
                if self.storage_adapter and self.storage_adapter.is_available():
                    tmp_blob = f"operational/tmp_clips/{analysis.id}/clip_{idx:04d}.mp4"
                    gcs_clip_uri = self.storage_adapter.upload_file(
                        clip_path, tmp_blob, content_type="video/mp4"
                    )
                    if gcs_clip_uri:
                        logger.info(f"[{vid}]    ☁️ Clip subido a GCS: {tmp_blob}")
                    else:
                        logger.warning(f"[{vid}]    ⚠️ No se pudo subir clip a GCS, usando frames base64")

                # Extraer frames base64 solo si no se pudo subir a GCS (fallback)
                frames_b64 = None if gcs_clip_uri else self._extract_frames_base64(clip_path, vid)


                # 2. Construir prompt
                time_range = f"{segment.start_second:.0f}s - {segment.end_second:.0f}s"
                prompt = build_segment_prompt(
                    analysis_type=analysis.analysis_type,
                    custom_context=analysis.custom_context,
                    segment_number=seg_num,
                    total_segments=total,
                    event_type=ev_type,
                    event_priority=ev_priority,
                    time_range=time_range,
                    is_frames_only=(gcs_clip_uri is None)
                )

                # 3. Analizar con Gemini — RETRY CON BACKOFF
                # clip_to_pass: gs:// URI si está disponible, ruta local como fallback
                clip_to_pass = gcs_clip_uri or clip_path
                gemini_result = None
                last_error = None

                for attempt in range(self.GEMINI_MAX_RETRIES):
                    try:
                        with gemini_semaphore:
                            logger.info(f"[{vid}]    🧠 Gemini intento {attempt+1}/{self.GEMINI_MAX_RETRIES}...")
                            gemini_result = self.gemini_adapter.analyze_video_clip(
                                clip_path=clip_to_pass, prompt=prompt, frames_base64=frames_b64 or None
                            )
                        if gemini_result and gemini_result.get('success', False):
                            break
                        last_error = gemini_result.get('error', 'Unknown error') if gemini_result else 'No response'
                    except Exception as e:
                        last_error = str(e)

                    if attempt < self.GEMINI_MAX_RETRIES - 1:
                        delay = self.GEMINI_RETRY_DELAYS[min(attempt, len(self.GEMINI_RETRY_DELAYS) - 1)]
                        jitter = random.uniform(-0.25, 0.25) * delay
                        wait_seconds = max(1.0, delay + jitter)
                        logger.warning(
                            f"[{vid}]    ⚠️ Intento {attempt+1} falló: {last_error}. "
                            f"Reintentando en {wait_seconds:.1f}s..."
                        )
                        time.sleep(wait_seconds)

                seg_elapsed = time.time() - seg_start

                if gemini_result and gemini_result.get('success', False):
                    analysis_data = gemini_result.get('analisis', {})
                    result['segment_result'] = {
                        'segment_number': seg_num, 'time_range': time_range,
                        'event_type': ev_type, 'result': analysis_data
                    }
                    frame_urls = self._extract_and_upload_frames(
                        video_path, segment, analysis.id, idx, vid, clip_path=clip_path
                    )
                    new_events = self._create_events_from_gemini(analysis_data, analysis.id, segment, ev_type, frame_urls)
                    result['events'] = new_events
                    result['success'] = True
                else:
                    logger.warning(f"[{vid}]    ❌ Gemini falló tras {self.GEMINI_MAX_RETRIES} intentos para segmento {seg_num} ({seg_elapsed:.1f}s): {last_error}")

                # Limpiar clip temporal local y GCS
                if clip_path and os.path.exists(clip_path):
                    os.remove(clip_path)
                if gcs_clip_uri and self.storage_adapter and self.storage_adapter.is_available():
                    try:
                        blob_name = gcs_clip_uri.split("/", 3)[-1] if gcs_clip_uri.startswith("gs://") else None
                        if blob_name:
                            self.storage_adapter.delete_file(blob_name)
                    except Exception:
                        pass  # La limpieza GCS es best-effort

            except Exception as e:
                logger.error(f"[{vid}]    ❌ Error en segmento {seg_num} [{ev_type}]: {e}")

            return result

        BATCH_SIZE = self.PARALLEL_WORKERS
        completed = 0

        for batch_start in range(0, total, BATCH_SIZE):
            if check_cancelled and check_cancelled(analysis.id):
                logger.info(f"[{vid}]    🛑 Pipeline cancelado — deteniendo en batch {batch_start}")
                break

            batch_end = min(batch_start + BATCH_SIZE, total)
            batch_segments = [(i, segments[i]) for i in range(batch_start, batch_end)]

            with ThreadPoolExecutor(max_workers=self.PARALLEL_WORKERS) as executor:
                futures = {executor.submit(process_single_segment, idx, seg): (idx, seg) for idx, seg in batch_segments}
                for future in as_completed(futures):
                    result = future.result()
                    if result['success']:
                        operational_events.extend(result['events'])
                        if result['segment_result']:
                            segment_results.append(result['segment_result'])
                    else:
                        failed_segments += 1
                    completed += 1

            if progress_callback:
                progress_callback(completed, total)

            if completed > 0 and completed % self.CHECKPOINT_INTERVAL == 0:
                logger.info(f"[{vid}]    💾 CHECKPOINT: {completed}/{total} segmentos procesados "
                            f"({len(operational_events)} eventos, {failed_segments} fallos)")

            if batch_end < total:
                time.sleep(1)

        phase_elapsed = time.time() - phase_start
        return operational_events, segment_results

    def _extract_frames_base64(self, clip_path: str, vid: str, n_frames: int = 4) -> List[str]:
        """Extrae N frames del clip como base64 JPEG para fallback cuando File API falla."""
        frames_b64 = []
        try:
            import cv2
            import base64
            cap = cv2.VideoCapture(clip_path)
            if not cap.isOpened():
                return frames_b64
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 1
            if total_frames <= 0:
                cap.release()
                return frames_b64
            # Distribuir n_frames equitativamente a lo largo del clip
            indices = [int(total_frames * (i + 1) / (n_frames + 1)) for i in range(n_frames)]
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if not ret:
                    continue
                # Redimensionar a resolución razonable para Gemini (~720p)
                h, w = frame.shape[:2]
                if w > 1280:
                    scale = 1280 / w
                    frame = cv2.resize(frame, (1280, int(h * scale)), interpolation=cv2.INTER_AREA)
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frames_b64.append(base64.b64encode(buf.tobytes()).decode('utf-8'))
            cap.release()
        except Exception as e:
            logger.debug(f"[{vid}]    ⚠️ Error extrayendo frames base64: {e}")
        return frames_b64

    def _extract_clip(self, video_path: str, start: float, end: float, output_path: str, vid: str) -> Optional[str]:
        try:
            import subprocess
            duration = end - start
            if duration > self.MAX_CLIP_DURATION:
                end = start + self.MAX_CLIP_DURATION
                duration = self.MAX_CLIP_DURATION

            clip_start = max(0, start - self.CLIP_BUFFER_SECONDS)
            clip_end = end + self.CLIP_BUFFER_SECONDS
            clip_duration = clip_end - clip_start

            target_bitrate = int((18 * 8 * 1024) / max(clip_duration, 1))
            target_bitrate = min(max(target_bitrate, 200), 2000)

            cmd = [
                "ffmpeg", "-y", "-ss", str(clip_start),
                "-i", video_path, "-t", str(clip_duration),
                "-c:v", "libx264", "-preset", "fast",
                "-b:v", f"{target_bitrate}k",
                "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
                "-c:a", "aac", "-b:a", "64k",
                "-movflags", "+faststart", output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result.returncode == 0 and os.path.exists(output_path):
                return output_path
            return None
        except Exception as e:
            logger.error(f"[{vid}]    ❌ Error extrayendo clip: {e}")
            return None

    @staticmethod
    def _truncate_details(data: dict, max_keys: int = 15, max_str: int = 300) -> dict:
        """Limita el tamaño del dict almacenado en 'details' para evitar documentos Firestore grandes."""
        if not isinstance(data, dict):
            return {}
        return {
            str(k)[:80]: (
                str(v)[:max_str]
                if not isinstance(v, dict)
                else {str(kk)[:80]: str(vv)[:100] for kk, vv in list(v.items())[:5]}
            )
            for k, v in list(data.items())[:max_keys]
        }

    def _extract_and_upload_frames(
        self, video_path: str, segment, analysis_id: str, seg_idx: int, vid: str,
        clip_path: Optional[str] = None
    ) -> List[str]:
        frame_urls = []
        try:
            import cv2
            # Preferir clip (más corto) sobre video original cuando esté disponible
            source_path = clip_path if clip_path and os.path.exists(clip_path) else video_path
            clip_offset = (
                max(0.0, segment.start_second - self.CLIP_BUFFER_SECONDS)
                if source_path == clip_path
                else 0.0
            )
            cap = cv2.VideoCapture(source_path)
            if not cap.isOpened():
                return []
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = segment.end_second - segment.start_second
            if fps <= 0 or duration <= 0:
                cap.release()
                return []

            n_frames = min(self.MAX_FRAMES_PER_SEGMENT, max(1, int(duration / 3)))
            interval = duration / (n_frames + 1)
            # Timestamps relativos al source (0 si es el video original, ajustado si es clip)
            timestamps = [
                (segment.start_second + interval * (i + 1)) - clip_offset
                for i in range(n_frames)
            ]

            for i, ts in enumerate(timestamps):
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(ts * fps))
                ret, frame = cap.read()
                if ret:
                    resized = cv2.resize(frame, self.HD_RESOLUTION, interpolation=cv2.INTER_LANCZOS4)
                    frame_path = os.path.join(self.temp_dir, f"op_frame_{seg_idx}_{i}.jpg")
                    cv2.imwrite(frame_path, resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    
                    if self.storage_adapter and self.storage_adapter.is_available():
                        gcs_dest = f"operational/{analysis_id}/seg_{seg_idx:03d}/frame_{i:02d}.jpg"
                        # Guardar gs:// URI (no signed URL) — las ADC user credentials no
                        # tienen private key para firmar. El endpoint proxy del backend
                        # sirve la imagen con auth propia usando download_as_bytes().
                        url = self.storage_adapter.upload_file(frame_path, gcs_dest, return_signed_url=False)
                        if url:
                            frame_urls.append(url)
                    os.remove(frame_path)
            cap.release()
        except Exception as e:
            logger.debug(f"[{vid}]    ⚠️ Error extrayendo/subiendo frames del segmento {seg_idx}: {e}")
        return frame_urls

    def _create_events_from_gemini(self, analysis_data: dict, analysis_id: str, segment, scanner_event_type: str, frame_urls: list) -> List[OperationalEvent]:
        events = []

        # ACCESS_CONTROL / PEOPLE_FLOW / OCCUPANCY — persons_detected list
        persons = analysis_data.get('persons_detected', [])
        if persons:
            for p in persons:
                if not isinstance(p, dict):
                    continue
                ev = OperationalEvent(
                    id=f"op_ev_{uuid.uuid4().hex[:10]}",
                    analysis_id=analysis_id,
                    timestamp_start=segment.start_second,
                    timestamp_end=segment.end_second,
                    event_type=p.get('fotcheck_status', p.get('direction', scanner_event_type)),
                    scanner_event_type=scanner_event_type,
                    person_description=p.get('description', ''),
                    carried_objects=p.get('carried_objects', ''),
                    direction=p.get('direction', ''),
                    confidence=p.get('confidence', 'MEDIUM'),
                    details=self._truncate_details(p),
                    frame_urls=frame_urls
                )
                events.append(ev)
            return events

        # WORK_SUPERVISION — workers list
        workers = analysis_data.get('workers', [])
        if workers:
            for w in workers:
                if not isinstance(w, dict):
                    continue
                ev = OperationalEvent(
                    id=f"op_ev_{uuid.uuid4().hex[:10]}",
                    analysis_id=analysis_id,
                    timestamp_start=segment.start_second,
                    timestamp_end=segment.end_second,
                    event_type='PPE_VIOLATION' if not w.get('ppe_compliant', True) else 'WORKER_ACTIVE',
                    scanner_event_type=scanner_event_type,
                    person_description=w.get('description', ''),
                    confidence='HIGH' if w.get('violation') else 'MEDIUM',
                    details=self._truncate_details(w),
                    frame_urls=frame_urls
                )
                events.append(ev)
            return events

        # PARKING — vehicles_entering / vehicles_exiting lists
        vehicles_in = analysis_data.get('vehicles_entering', [])
        vehicles_out = analysis_data.get('vehicles_exiting', [])
        if vehicles_in or vehicles_out:
            for v in vehicles_in:
                if not isinstance(v, dict):
                    continue
                ev = OperationalEvent(
                    id=f"op_ev_{uuid.uuid4().hex[:10]}",
                    analysis_id=analysis_id,
                    timestamp_start=segment.start_second,
                    timestamp_end=segment.end_second,
                    event_type='VEHICLE_ENTRY',
                    scanner_event_type=scanner_event_type,
                    direction='ENTRY',
                    confidence='MEDIUM',
                    details=self._truncate_details(v),
                    frame_urls=frame_urls
                )
                events.append(ev)
            for v in vehicles_out:
                if not isinstance(v, dict):
                    continue
                ev = OperationalEvent(
                    id=f"op_ev_{uuid.uuid4().hex[:10]}",
                    analysis_id=analysis_id,
                    timestamp_start=segment.start_second,
                    timestamp_end=segment.end_second,
                    event_type='VEHICLE_EXIT',
                    scanner_event_type=scanner_event_type,
                    direction='EXIT',
                    confidence='MEDIUM',
                    details=self._truncate_details(v),
                    frame_urls=frame_urls
                )
                events.append(ev)
            return events

        # MERCHANDISE_CONTROL — objects_in / objects_out lists
        objects_in = analysis_data.get('objects_in', [])
        objects_out = analysis_data.get('objects_out', [])
        if objects_in or objects_out:
            for o in objects_in:
                if not isinstance(o, dict):
                    continue
                ev = OperationalEvent(
                    id=f"op_ev_{uuid.uuid4().hex[:10]}",
                    analysis_id=analysis_id,
                    timestamp_start=segment.start_second,
                    timestamp_end=segment.end_second,
                    event_type='OBJECT_IN',
                    scanner_event_type=scanner_event_type,
                    direction='ENTRY',
                    carried_objects=o.get('description', ''),
                    confidence='MEDIUM',
                    details=self._truncate_details(o),
                    frame_urls=frame_urls
                )
                events.append(ev)
            for o in objects_out:
                if not isinstance(o, dict):
                    continue
                ev = OperationalEvent(
                    id=f"op_ev_{uuid.uuid4().hex[:10]}",
                    analysis_id=analysis_id,
                    timestamp_start=segment.start_second,
                    timestamp_end=segment.end_second,
                    event_type='OBJECT_OUT',
                    scanner_event_type=scanner_event_type,
                    direction='EXIT',
                    carried_objects=o.get('description', ''),
                    confidence='MEDIUM',
                    details=self._truncate_details(o),
                    frame_urls=frame_urls
                )
                events.append(ev)
            return events

        # Fallback genérico — un evento por segmento con el JSON completo en details
        ev = OperationalEvent(
            id=f"op_ev_{uuid.uuid4().hex[:10]}",
            analysis_id=analysis_id,
            timestamp_start=segment.start_second,
            timestamp_end=segment.end_second,
            event_type=scanner_event_type,
            scanner_event_type=scanner_event_type,
            details=self._truncate_details(analysis_data),
            frame_urls=frame_urls
        )
        events.append(ev)
        return events
