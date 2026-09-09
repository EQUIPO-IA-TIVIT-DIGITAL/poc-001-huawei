import { useEffect, useState } from 'react';
import { getApiBaseUrl } from '../lib/backendUrl';
import { Loader2, CheckCircle, AlertCircle, Clock } from 'lucide-react';

interface ProgressData {
  success: boolean;
  video_id: string;
  estado: string;
  progreso: number;
  fase_actual: string;
  timestamp: string;
  estadisticas?: any;
  error?: string;
}

interface VideoProcessingProgressProps {
  videoId: string;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

function getFaseDescripcion(fase: string): string {
  const fases: Record<string, string> = {
    'INICIO': 'Iniciando procesamiento...',
    'MOTION_DONE': 'Detección de movimiento completada',
    'CLIPS_EXTRACTED': 'Clips extraídos',
    'CLASSIFICATION_DONE': 'Clasificación con IA completada',
    'DEEP_ANALYSIS_DONE': 'Análisis profundo completado',
    'EVENTS_SAVED': 'Eventos guardados',
    'REPORT_DONE': 'Reporte generado'
  };
  return fases[fase] || fase;
}

/**
 * Componente para mostrar progreso en tiempo real usando Server-Sent Events (SSE)
 * 
 * Uso:
 * <VideoProcessingProgress 
 *   videoId="sec_video_xxx" 
 *   onComplete={() => console.log('Completado')} 
 * />
 */
export default function VideoProcessingProgress({
  videoId,
  onComplete,
  onError
}: VideoProcessingProgressProps) {
  const [progress, setProgress] = useState<number>(0);
  const [currentPhase, setCurrentPhase] = useState<string>('Iniciando...');
  const [status, setStatus] = useState<string>('processing');
  const [connected, setConnected] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Crear conexión SSE
    const eventSource = new EventSource(
      `${import.meta.env.VITE_API_BASE_URL || getApiBaseUrl()}/api/security/videos/${videoId}/progress`
    );

    eventSource.onopen = () => {
      console.log('✅ SSE conectado');
      setConnected(true);
    };

    eventSource.onmessage = (event) => {
      try {
        const data: ProgressData = JSON.parse(event.data);
        
        if (data.error) {
          setError(data.error);
          setConnected(false);
          onError?.(data.error);
          return;
        }

        setProgress(data.progreso);
        setStatus(data.estado);
        setCurrentPhase(getFaseDescripcion(data.fase_actual));

        // Si completado o error, cerrar conexión
        if (data.estado === 'completed') {
          eventSource.close();
          setConnected(false);
          onComplete?.();
        } else if (data.estado === 'error') {
          eventSource.close();
          setConnected(false);
          setError('Error en el procesamiento');
          onError?.('Error en el procesamiento');
        }
      } catch (err) {
        console.error('Error parsing SSE data:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('❌ SSE error:', err);
      eventSource.close();
      setConnected(false);
      setError('Conexión perdida');
    };

    // Cleanup al desmontar
    return () => {
      eventSource.close();
      setConnected(false);
    };
  }, [videoId, onComplete, onError]);

  const getStatusIcon = () => {
    if (error) {
      return <AlertCircle className="w-6 h-6 text-red-500" />;
    }
    if (status === 'completed') {
      return <CheckCircle className="w-6 h-6 text-green-500" />;
    }
    return <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />;
  };

  const getStatusColor = () => {
    if (error) return 'bg-red-100 border-red-300';
    if (status === 'completed') return 'bg-green-100 border-green-300';
    return 'bg-blue-100 border-blue-300';
  };

  return (
    <div className={`border-2 rounded-lg p-6 ${getStatusColor()}`}>
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        {getStatusIcon()}
        <div className="flex-1">
          <h3 className="font-semibold text-gray-900">
            {error ? 'Error en Procesamiento' : 
             status === 'completed' ? 'Procesamiento Completado' : 
             'Procesando Video'}
          </h3>
          <p className="text-sm text-gray-600">{currentPhase}</p>
        </div>
        {connected && !error && status !== 'completed' && (
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <Clock className="w-4 h-4" />
            <span>En vivo</span>
          </div>
        )}
      </div>

      {/* Progress Bar */}
      {!error && (
        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700">Progreso</span>
            <span className="text-sm font-bold text-gray-900">{progress}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
            <div
              className="bg-blue-600 h-full transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      {/* Info adicional */}
      {!error && status !== 'completed' && (
        <p className="text-xs text-gray-500 mt-4">
          ⏱️ Este proceso puede tardar 35-45 minutos para videos de 12 horas.
          Puedes cerrar esta ventana, el procesamiento continuará.
        </p>
      )}

      {/* Success Message */}
      {status === 'completed' && !error && (
        <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm text-green-800">
            ✅ Video procesado exitosamente. Los resultados están disponibles.
          </p>
        </div>
      )}
    </div>
  );
}