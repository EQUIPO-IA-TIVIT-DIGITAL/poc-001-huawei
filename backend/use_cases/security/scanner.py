import logging

logger = logging.getLogger(__name__)

class SecurityVideoScanner:
    """Extrae la lógica de cálculo y escáner multinivel"""
    MOTION_THRESHOLD = 0.008
    DENSE_SCAN_INTERVAL = 0.5
    REFERENCE_INTERVAL = 30.0

    def __init__(self):
        self.dense_scanner = None

    def init_dense_scanner(self, scan_interval: float = None):
        effective_interval = scan_interval or self.DENSE_SCAN_INTERVAL
        if self.dense_scanner is not None and self.dense_scanner.sample_interval == effective_interval:
            return
        from infrastructure.services.dense_scanner import DenseVideoScanner
        self.dense_scanner = DenseVideoScanner(
            sample_interval=effective_interval,
            motion_threshold=self.MOTION_THRESHOLD,
            reference_interval=self.REFERENCE_INTERVAL
        )
        logger.info(f"✅ Dense Scanner multinivel inicializado (intervalo={effective_interval}s)")

    def get_adaptive_scan_interval(self, video_duration: float) -> float:
        if video_duration <= 60: return 0.5
        elif video_duration <= 600: return 1.0
        elif video_duration <= 3600: return 1.5
        else: return 2.0

    def calculate_max_segments(self, video_duration: float) -> int:
        if video_duration <= 600: return 30
        elif video_duration <= 1800: return 60
        elif video_duration <= 3600: return 100
        elif video_duration <= 7200: return 150
        elif video_duration <= 14400: return 220
        elif video_duration <= 28800: return 300
        else: return 400
