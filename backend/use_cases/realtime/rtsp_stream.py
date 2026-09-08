import cv2
import threading
import queue
import time
import logging

logger = logging.getLogger(__name__)

class VideoStreamer:
    """
    Motor de ingesta de video RTSP (o webcam) usando patrón Productor-Consumidor.
    Lee los cuadros en un hilo separado para evitar cuellos de botella y descarta 
    cuadros antiguos si el consumidor (YOLO) se demora.
    """
    def __init__(self, source=0, target_fps=5, max_queue_size=5):
        self.source = source
        self.target_fps = target_fps
        self.max_queue_size = max_queue_size
        self.frame_queue = queue.Queue(maxsize=max_queue_size)
        self.stopped = False
        self.cap = None
        self.thread = None
        self.actual_fps = 0

    def start(self):
        """Inicia el hilo productor para capturar video."""
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            logger.error(f"Error al abrir la fuente de video: {self.source}")
            raise ValueError(f"No se pudo abrir la fuente: {self.source}")
        
        self.stopped = False
        self.thread = threading.Thread(target=self._update, args=(), daemon=True)
        self.thread.start()
        logger.info(f"Ingesta RTSP iniciada en fuente: {self.source}")
        return self

    def _update(self):
        """Bucle infinito del hilo productor."""
        frame_interval = 1.0 / self.target_fps if self.target_fps > 0 else 0
        last_sampled_time = time.time()
        last_valid_frame_time = time.time()
        frames_read = 0
        fps_start_time = time.time()

        while not self.stopped:
            ret, frame = self.cap.read()
            
            if not ret or frame is None or frame.size == 0:
                if time.time() - last_valid_frame_time > 5.0:
                    logger.warning("No llegan frames desde hace 5s. Deteniendo ingesta.")
                    self.stop()
                    break
                time.sleep(0.01)
                continue
                
            last_valid_frame_time = time.time()
            current_time = time.time()
            
            # Frame Sampling: Solo procesar si ha pasado el intervalo objetivo
            if (current_time - last_sampled_time) >= frame_interval:
                last_sampled_time = current_time
                
                # Si la cola está llena, eliminar el cuadro más antiguo (Drop Frame)
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                
                self.frame_queue.put(frame)

                # Calcular FPS reales de lectura
                frames_read += 1
                if (current_time - fps_start_time) >= 1.0:
                    self.actual_fps = frames_read
                    frames_read = 0
                    fps_start_time = current_time

        self.cap.release()

    def read(self):
        """Extrae el cuadro más reciente de la cola (Consumidor)."""
        try:
            return self.frame_queue.get_nowait() # Non-blocking
        except queue.Empty:
            return None

    def stop(self):
        """Detiene el hilo y libera los recursos."""
        self.stopped = True
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        logger.info("Ingesta RTSP detenida.")

    def more(self):
        """Devuelve True si hay frames en la cola."""
        return not self.frame_queue.empty()
