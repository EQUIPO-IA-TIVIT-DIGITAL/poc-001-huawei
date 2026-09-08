import sys
import os
import cv2
import time
import logging
import argparse

# Añadir la carpeta actual al path para importar directamente sin cargar todo el backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'use_cases', 'realtime')))

from rtsp_stream import VideoStreamer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Prueba de estabilidad RTSP")
    parser.add_argument("--source", type=str, default="0", help="Fuente de video (ej: 0 para webcam, o rtsp://...)")
    args = parser.parse_args()
    
    source = int(args.source) if args.source.isdigit() else args.source

    logger.info("="*60)
    logger.info("🎬 PRUEBA DE INGESTA RTSP CON MULTI-HILO (Sprint 1)")
    logger.info("="*60)
    logger.info(f"Iniciando captura desde: {source}")
    logger.info("Presiona la tecla 'q' en la ventana de video para salir.")
    
    streamer = None
    frames_procesados = 0
    start_time = time.time()
    
    try:
        # Iniciar el Streamer a 8 FPS para prueba (Frame Sampling)
        streamer = VideoStreamer(source=source, target_fps=8).start()
        
        # Simular el Hilo Consumidor (La IA)
        time.sleep(1) # Esperar a que la cámara caliente
        
        # Configurar la ventana para que sea redimensionable (pantalla completa)
        cv2.namedWindow("MIRA - RTSP Stream Test", cv2.WINDOW_NORMAL)
        
        while True:
            # Condición de salida (Apretar Q) y refresco de interfaz (Evita el "No responde")
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break

            # Consumidor extrae el frame (Non-blocking)
            frame = streamer.read()
            
            if frame is None:
                time.sleep(0.01)
                continue
                
            if frame is not None and frame.size > 0:
                frames_procesados += 1
                
                # Calcular FPS del consumidor
                elapsed = time.time() - start_time
                consumer_fps = frames_procesados / elapsed if elapsed > 0 else 0
                
                # Mostrar en pantalla la fluidez (Simulando lo que recibe la IA)
                cv2.putText(frame, "MIRA - Simulador RTSP (Sprint 1)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(frame, f"FPS Reales Captura: {streamer.actual_fps}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(frame, f"FPS Consumidor: {consumer_fps:.1f}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 100, 100), 2)
                
                cv2.imshow("MIRA - RTSP Stream Test", frame)
                
    except KeyboardInterrupt:
        logger.info("Interrumpido por el usuario.")
    except Exception as e:
        logger.exception(f"Error durante la ejecución: {e}")
    finally:
        logger.info("Deteniendo el streamer...")
        if streamer is not None:
            streamer.stop()
        cv2.destroyAllWindows()
        cv2.waitKey(1)
        
        elapsed = time.time() - start_time
        logger.info(f"Tiempo total: {elapsed:.2f}s")
        if elapsed > 0:
            logger.info(f"FPS promedio global: {frames_procesados/elapsed:.2f}")

if __name__ == "__main__":
    main()
