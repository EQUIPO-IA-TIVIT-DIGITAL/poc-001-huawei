import logging

logger = logging.getLogger(__name__)

class OperationalScanner:
    """Fase 1: Escaneo denso multinivel de video operativo"""
    
    def __init__(self, dense_scanner):
        self.dense_scanner = dense_scanner
        
    def scan(self, local_video_path: str, video_duration: float, analysis_id: str, vid: str) -> dict:
        """Realiza el escaneo denso y clasifica/segmenta los eventos"""
        logger.info(f"[{vid}] ")
        logger.info(f"[{vid}] 🔬 ══════════════════════════════════════════════════")
        logger.info(f"[{vid}] 🔬 FASE 1: Escaneo denso multinivel (100% cobertura)")
        logger.info(f"[{vid}] 🔬 5 capas: diff + MOG2 + contornos + zonas + temporal")
        logger.info(f"[{vid}] 🔬 ══════════════════════════════════════════════════")

        frame_analyses = self.dense_scanner.scan_video(local_video_path, video_id=analysis_id)
        
        detected_events = self.dense_scanner.classify_events(
            frame_analyses, video_duration, video_id=analysis_id
        )

        max_segs = self._calculate_max_segments(video_duration)
        motion_segments = self.dense_scanner.events_to_segments(
            detected_events, video_duration,
            max_segment_duration=30.0,
            max_segments=max_segs,
            video_id=analysis_id
        )

        stats = {
            'total_samples': len(frame_analyses),
            'detected_events': len(detected_events),
            'segments_for_analysis': len(motion_segments),
            'event_types': {
                et: sum(1 for e in detected_events if e.event_type == et)
                for et in set(e.event_type for e in detected_events)
            } if detected_events else {}
        }
        
        logger.info(f"[{vid}] ✅ {len(motion_segments)} segmentos para análisis Gemini")

        # Crear mapa de eventos para prompts
        detected_events_map = {}
        for ev in detected_events:
            for seg in motion_segments:
                if (ev.start_second <= seg.start_second <= ev.end_second or
                        ev.start_second <= seg.end_second <= ev.end_second):
                    detected_events_map[seg.start_second] = ev

        return {
            'frame_analyses': frame_analyses,
            'detected_events': detected_events,
            'motion_segments': motion_segments,
            'detected_events_map': detected_events_map,
            'stats': stats
        }

    def _calculate_max_segments(self, video_duration: float) -> int:
        if video_duration <= 600:
            return 30
        elif video_duration <= 1800:
            return 60
        elif video_duration <= 3600:
            return 100
        elif video_duration <= 7200:
            return 150
        elif video_duration <= 14400:
            return 220
        elif video_duration <= 28800:
            return 300
        else:
            return 400
