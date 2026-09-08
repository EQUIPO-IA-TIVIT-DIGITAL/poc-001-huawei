import { useEffect, useState, useRef, useCallback } from 'react';
import {
    Check,
    Loader2,
    AlertCircle,
    X,
    RefreshCw,
    CheckCircle2,
    XCircle,
    Clock,
    FileVideo,
    Upload,
    Timer,
    Eye,
    Video,
    Mic,
    Brain,
    FileText,
    Sparkles,
    MessageCircle,
    Send,
} from 'lucide-react';
import { Button } from './ui/button';
import { videoService } from '../services/video';
import { useNavigate } from '@tanstack/react-router';
import { useQueryClient } from '@tanstack/react-query';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';

// Fallback video for demo purposes
const MOCK_VIDEO_URL =
    'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4';

// Definición de pasos con iconos y tiempos estimados
interface ProcessingStep {
    id: number;
    label: string;
    icon: any;
    estimatedTime: string;
    description: string;
}

const PROCESSING_STEPS: ProcessingStep[] = [
    {
        id: 1,
        label: 'Preparación',
        icon: Upload,
        estimatedTime: '~5s',
        description: 'Compresión + Upload a GCS + Thumbnail',
    },
    {
        id: 2,
        label: 'Verificación',
        icon: Timer,
        estimatedTime: '~2s',
        description: 'Validando duración (60s máx)',
    },
    {
        id: 3,
        label: 'Escaneo Rápido',
        icon: Eye,
        estimatedTime: '~5s',
        description: 'Detección de violaciones obvias',
    },
    {
        id: 4,
        label: 'Análisis Profundo',
        icon: Brain,
        estimatedTime: '~15s',
        description: 'Gemini Vision + Audio en paralelo',
    },
    {
        id: 5,
        label: 'Decisión IA',
        icon: Sparkles,
        estimatedTime: '~5s',
        description: 'Decisión final + Título automático',
    },
];

interface VideoResult {
    id: string;
    titulo: string;
    resultado: string;
    confianza: number;
    confianzaPorcentaje?: number;
    analisis?: string;
    razon?: string;
    duracion?: number;
    estado?: string;
}

interface ProcessingError {
    errorCode: string;
    message: string;
    canRetry: boolean;
}

interface ProcessingState {
    currentStep: number;
    stepStatus: 'running' | 'success' | 'warning' | 'error' | 'skipped' | 'pending';
    status: 'pending' | 'processing' | 'completed' | 'error' | 'cancelled' | 'clarification';
    message: string;
    details?: any;
    videoResult?: VideoResult;
    error?: ProcessingError;
    finalStatus?: 'approved' | 'rejected' | 'review' | 'unknown';
    clarificationQuestions?: Array<{ id: string; question: string }>;
}

interface VideoProcessingModalProps {
    videoId: string | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    videoFile?: File | null;
    onRetry?: () => void;
    workspaceId?: string;
}

export function VideoProcessingModal({
    videoId,
    open,
    onOpenChange,
    videoFile,
    onRetry,
    workspaceId,
}: VideoProcessingModalProps) {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const videoRef = useRef<HTMLVideoElement>(null);
    const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const eventSourceRef = useRef<EventSource | null>(null);
    const sseFailedRef = useRef(false);

    const [state, setState] = useState<ProcessingState>({
        currentStep: 0,
        stepStatus: 'pending',
        status: 'pending',
        message: 'Iniciando...',
    });

    const [videoUrl, setVideoUrl] = useState<string | null>(null);
    const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
    const [submittingClarification, setSubmittingClarification] = useState(false);

    const stopPolling = useCallback(() => {
        if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
        }
    }, []);

    const stopStream = useCallback(() => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
        }
    }, []);

    const invalidateVideoQueries = useCallback(() => {
        queryClient.invalidateQueries({ queryKey: ['my-videos'] });
        queryClient.invalidateQueries({ queryKey: ['dashboard-videos'] });
        queryClient.invalidateQueries({ queryKey: ['workspaces'] });
    }, [queryClient]);

    const applyStatusUpdate = useCallback(
        (response: any) => {
            if (!response) return;

            if (response.status === 'completed' && response.final_result) {
                setState((s) => ({
                    ...s,
                    currentStep: 6,
                    status: 'completed',
                    stepStatus: 'success',
                    message: response.message || 'Completado',
                    videoResult: response.final_result?.video,
                    finalStatus: response.final_result?.finalStatus,
                }));

                if (response.final_result?.video?.video_url) {
                    setVideoUrl(response.final_result.video.video_url);
                }

                stopPolling();
                stopStream();
                invalidateVideoQueries();
                return;
            }

            if (response.status === 'error') {
                setState((s) => ({
                    ...s,
                    status: 'error',
                    stepStatus: 'error',
                    message: response.message || 'Error desconocido',
                    currentStep: response.step || s.currentStep,
                    error: response.error || {
                        errorCode: response.details?.errorCode || 'UNKNOWN_ERROR',
                        message: response.message || 'Error desconocido',
                        canRetry: response.details?.canRetry ?? true,
                    },
                }));
                stopPolling();
                stopStream();
                invalidateVideoQueries();
                return;
            }

            if (response.status === 'cancelled') {
                setState((s) => ({
                    ...s,
                    status: 'cancelled',
                    stepStatus: 'error',
                    message: response.message || 'Cancelado',
                }));
                stopPolling();
                stopStream();
                invalidateVideoQueries();
                return;
            }

            if (response.status === 'processing' || response.status === 'pending') {
                setState((s) => ({
                    ...s,
                    currentStep: response.step || 0,
                    stepStatus: 'running',
                    message: response.message || 'Procesando...',
                    status: 'processing',
                    details: response.details,
                }));
            }
        },
        [invalidateVideoQueries, stopPolling, stopStream],
    );

    // Create object URL for the file to preview
    useEffect(() => {
        if (videoFile) {
            const url = URL.createObjectURL(videoFile);
            setVideoUrl(url);
            return () => URL.revokeObjectURL(url);
        } else {
            setVideoUrl(null);
        }
    }, [videoFile]);

    // Función para consultar el estado (POLLING)
    const pollStatus = useCallback(async () => {
        if (!videoId) return;

        try {
            const response = await videoService.getVideoStatus(videoId);

            // Si es undefined, probablemente autenticación falló y apiRequest manejó el redirect
            if (!response) return;

            console.log('📊 Estado recibido (polling):', response);
            applyStatusUpdate(response);
        } catch (error) {
            console.error('Error polling status:', error);
            // No detenemos el polling por errores de red temporales
        }
    }, [videoId, applyStatusUpdate]);

    const startPolling = useCallback(() => {
        if (pollingIntervalRef.current) return;
        pollStatus();
        pollingIntervalRef.current = setInterval(pollStatus, 1500);
    }, [pollStatus]);

    const startStatusStream = useCallback(() => {
        if (!videoId) return;
        stopStream();
        try {
            const stream = videoService.getVideoStatusStream(videoId);
            eventSourceRef.current = stream;

            stream.onmessage = (event) => {
                try {
                    const payload = JSON.parse(event.data);
                    applyStatusUpdate(payload);
                } catch (err) {
                    console.error('Error parsing SSE payload:', err);
                }
            };

            stream.onerror = () => {
                if (!sseFailedRef.current) {
                    sseFailedRef.current = true;
                    stopStream();
                    startPolling();
                }
            };
        } catch (error) {
            console.error('SSE no disponible, usando polling:', error);
            startPolling();
        }
    }, [videoId, applyStatusUpdate, startPolling, stopStream]);

    // Iniciar polling cuando se abre el modal
    useEffect(() => {
        if (!videoId || !open) {
            stopPolling();
            stopStream();
            setState({
                currentStep: 0,
                stepStatus: 'pending',
                status: 'pending',
                message: 'Esperando video...',
            });
            return;
        }

        console.log('🔄 Iniciando stream/polling para video:', videoId);
        sseFailedRef.current = false;

        // Disparar inicio de procesamiento (Idempotente en backend)
        const startProcessing = async () => {
            try {
                // Usar endpoint correcto sin prefijo /socio si no está configurado en backend
                await videoService.startProcessing(videoId);
                console.log('🚀 Procesamiento iniciado exitosamente');
            } catch (error) {
                console.error(
                    '⚠️ Error al iniciar procesamiento (puede que ya esté corriendo):',
                    error,
                );
            }
        };

        // Iniciar procesamiento y luego escuchar estado por SSE (fallback a polling)
        startProcessing().then(() => {
            startStatusStream();
        });

        return () => {
            console.log('🔄 Deteniendo stream/polling');
            stopPolling();
            stopStream();
        };
    }, [videoId, open, startStatusStream, stopPolling, stopStream]);

    const handleClose = async () => {
        if ((state.status === 'processing' || state.status === 'pending') && videoId) {
            console.log('Cancelling processing for', videoId);
            try {
                // Cancelar via HTTP en lugar de WebSocket
                await videoService.cancelProcessing(videoId);
            } catch (e) {
                console.error('Error cancelling:', e);
            }
        }
        stopPolling();
        stopStream();
        invalidateVideoQueries();
        onOpenChange(false);
    };

    const handleRetry = () => {
        if (onRetry) {
            onRetry();
        }
        handleClose();
    };

    const getResultIcon = () => {
        if (!state.videoResult) return null;

        switch (state.finalStatus) {
            case 'approved':
                return <CheckCircle2 className="w-16 h-16 text-green-500" />;
            case 'rejected':
                return <XCircle className="w-16 h-16 text-red-500" />;
            case 'review':
                return <Clock className="w-16 h-16 text-amber-500" />;
            default:
                return <FileVideo className="w-16 h-16 text-gray-500" />;
        }
    };

    const getResultColors = () => {
        switch (state.finalStatus) {
            case 'approved':
                return {
                    bg: 'bg-green-50',
                    border: 'border-green-500',
                    text: 'text-green-700',
                    badge: 'bg-green-100 text-green-800',
                };
            case 'rejected':
                return {
                    bg: 'bg-red-50',
                    border: 'border-red-500',
                    text: 'text-red-700',
                    badge: 'bg-red-100 text-red-800',
                };
            case 'review':
                return {
                    bg: 'bg-amber-50',
                    border: 'border-amber-500',
                    text: 'text-amber-700',
                    badge: 'bg-amber-100 text-amber-800',
                };
            default:
                return {
                    bg: 'bg-gray-50',
                    border: 'border-gray-500',
                    text: 'text-gray-700',
                    badge: 'bg-gray-100 text-gray-800',
                };
        }
    };

    const getResultLabel = () => {
        switch (state.finalStatus) {
            case 'approved':
                return '✅ Video Aprobado';
            case 'rejected':
                return '❌ Video Rechazado';
            case 'review':
                return '⏳ Requiere Revisión Manual';
            default:
                return 'Procesamiento Completado';
        }
    };

    const colors = getResultColors();

    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (!nextOpen) {
                    void handleClose();
                    return;
                }
                onOpenChange(nextOpen);
            }}
        >
            <DialogContent
                className="max-w-6xl max-h-[90vh] overflow-y-auto bg-white text-gray-900"
                onInteractOutside={(e: Event) => {
                    e.preventDefault();
                }}
            >
                <DialogHeader className="flex flex-row items-center justify-between pb-1">
                    <div className="text-left">
                        <DialogTitle className="text-lg font-bold flex items-center gap-2">
                            {state.status === 'processing' && (
                                <div className="relative">
                                    <Loader2 className="w-5 h-5 animate-spin text-tivit-red" />
                                    <span className="absolute inset-0 w-5 h-5 animate-ping opacity-75">
                                        <Loader2 className="w-5 h-5 text-tivit-red" />
                                    </span>
                                </div>
                            )}
                            {state.status === 'completed' && (
                                <Check className="w-5 h-5 text-green-500" />
                            )}
                            {state.status === 'error' && (
                                <AlertCircle className="w-5 h-5 text-red-500" />
                            )}
                            {state.status === 'cancelled' && (
                                <X className="w-5 h-5 text-gray-500" />
                            )}
                            {state.status === 'processing' ? (
                                <span className="animate-pulse">Procesando Video...</span>
                            ) : state.status === 'completed' ? (
                                'Análisis Completado'
                            ) : state.status === 'error' ? (
                                'Error en el Procesamiento'
                            ) : state.status === 'cancelled' ? (
                                'Procesamiento Cancelado'
                            ) : (
                                'Preparando...'
                            )}
                        </DialogTitle>
                        <DialogDescription className="text-xs text-gray-500">
                            ID: {videoId}
                        </DialogDescription>
                    </div>
                </DialogHeader>

                {/* --- 1. Top Result Banner (Outside Grid) --- */}
                {state.status === 'completed' && state.videoResult && (
                    <div
                        className={`mt-2 mx-1 rounded-xl border overflow-hidden animate-in fade-in slide-in-from-top-4 duration-500 flex items-center shadow-sm ${
                            state.finalStatus === 'approved'
                                ? 'bg-green-50 border-green-200'
                                : state.finalStatus === 'rejected'
                                  ? 'bg-red-50 border-red-200'
                                  : 'bg-amber-50 border-amber-200'
                        }`}
                    >
                        <div
                            className={`p-2 flex items-center justify-center border-r ${
                                state.finalStatus === 'approved'
                                    ? 'border-green-100 bg-green-100/50 text-green-600'
                                    : state.finalStatus === 'rejected'
                                      ? 'border-red-100 bg-red-100/50 text-red-600'
                                      : 'border-amber-100 bg-amber-100/50 text-amber-600'
                            }`}
                        >
                            {state.finalStatus === 'approved' && (
                                <CheckCircle2 className="w-6 h-6" />
                            )}
                            {state.finalStatus === 'rejected' && <XCircle className="w-6 h-6" />}
                            {state.finalStatus === 'review' && <Clock className="w-6 h-6" />}
                        </div>

                        <div className="flex-1 px-3 py-2">
                            <h4
                                className={`text-base font-bold ${
                                    state.finalStatus === 'approved'
                                        ? 'text-green-900'
                                        : state.finalStatus === 'rejected'
                                          ? 'text-red-900'
                                          : 'text-amber-900'
                                }`}
                            >
                                {getResultLabel()}
                            </h4>
                            <p
                                className={`text-xs font-medium ${
                                    state.finalStatus === 'approved'
                                        ? 'text-green-700'
                                        : state.finalStatus === 'rejected'
                                          ? 'text-red-700'
                                          : 'text-amber-700'
                                }`}
                            >
                                {state.videoResult.confianzaPorcentaje}% de confianza en la decisión
                                automatizada
                            </p>
                        </div>
                    </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-5 gap-6 mt-4">
                    {/* --- 2. Left Column: Video Player Only --- */}
                    <div className="md:col-span-3 space-y-6 flex flex-col">
                        {/* Video Player */}
                        <div className="aspect-video bg-black rounded-xl overflow-hidden flex items-center justify-center relative shadow-md border border-gray-200">
                            <video
                                ref={videoRef}
                                src={videoUrl || MOCK_VIDEO_URL}
                                className="w-full h-full object-contain"
                                autoPlay
                                muted
                                loop
                                playsInline
                                controls
                            />

                            {state.status === 'error' && (
                                <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 z-20">
                                    <AlertCircle size={48} className="text-red-500 mb-2" />
                                    <h3 className="text-lg font-bold text-white">
                                        Error en el análisis
                                    </h3>
                                    <p className="text-gray-300 text-sm text-center max-w-md px-4">
                                        {state.message}
                                    </p>
                                </div>
                            )}

                            {/* Overlay icon only if NOT completed (since we have the banner now) */}
                            {state.status === 'completed' && state.videoResult && (
                                <div className="absolute top-4 right-4 z-20">
                                    <div
                                        className={`px-3 py-1 rounded-full text-xs font-bold shadow-lg backdrop-blur-sm ${
                                            state.finalStatus === 'approved'
                                                ? 'bg-green-500/90 text-white'
                                                : state.finalStatus === 'rejected'
                                                  ? 'bg-red-500/90 text-white'
                                                  : 'bg-amber-500/90 text-white'
                                        }`}
                                    >
                                        {getResultLabel()}
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Error Details (Keep near video if error) */}
                        {(state.status === 'error' || state.status === 'cancelled') &&
                            state.error && (
                                <div className="p-6 rounded-xl bg-red-50 border border-red-200 shadow-sm">
                                    <div className="flex items-start gap-4">
                                        <div className="p-2 bg-red-100 rounded-full text-red-600">
                                            <AlertCircle className="w-6 h-6" />
                                        </div>
                                        <div className="flex-1">
                                            <h4 className="font-bold text-red-900 text-lg mb-1">
                                                {state.status === 'cancelled'
                                                    ? 'Procesamiento Cancelado'
                                                    : 'Error de Procesamiento'}
                                            </h4>
                                            <p className="text-sm text-red-700 mb-4 leading-relaxed">
                                                {state.error.message}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            )}
                        {/* --- Result Details (Moved to Left Column) --- */}
                        {state.status === 'completed' && state.videoResult && (
                            <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-700">
                                <div>
                                    <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                                        Título Generado
                                    </p>
                                    <h3 className="text-xl font-bold text-gray-900 leading-tight">
                                        {state.videoResult.titulo}
                                    </h3>
                                </div>

                                {state.videoResult.razon && (
                                    <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
                                        <p className="text-sm font-medium text-gray-700 leading-relaxed">
                                            <span className="font-bold text-gray-900 block mb-1">
                                                Razón de la decisión:
                                            </span>
                                            {state.videoResult.razon}
                                        </p>
                                    </div>
                                )}

                                {state.videoResult.analisis && (
                                    <details className="pt-2">
                                        <summary className="text-sm font-semibold text-tivit-red cursor-pointer hover:underline">
                                            Ver análisis técnico completo
                                        </summary>
                                        <div className="mt-3 text-xs text-gray-600 bg-gray-50 p-3 rounded border border-gray-100 font-mono leading-relaxed">
                                            {state.videoResult.analisis}
                                        </div>
                                    </details>
                                )}
                            </div>
                        )}
                    </div>

                    {/* --- 3. Right Column: Timeline Visual Mejorado --- */}
                    <div className="md:col-span-2 space-y-4">
                        {/* Progress Overview */}
                        <div className="bg-linear-to-br from-gray-50 to-gray-100 rounded-xl border border-gray-200 p-4 shadow-sm">
                            <div className="flex items-center justify-between mb-3">
                                <h3 className="text-sm font-bold text-gray-700 uppercase tracking-wide">
                                    Progreso del Análisis
                                </h3>
                                <span className="text-xs font-medium text-gray-500">
                                    Paso {Math.min(state.currentStep, 5)}/5
                                </span>
                            </div>

                            {/* Progress Bar */}
                            <div className="relative h-2 bg-gray-200 rounded-full overflow-hidden">
                                <div
                                    className="absolute top-0 left-0 h-full bg-gradient-to-r from-tivit-red via-red-500 to-red-400 transition-all duration-500 ease-out"
                                    style={{
                                        width: `${(Math.min(state.currentStep, 5) / 5) * 100}%`,
                                    }}
                                >
                                    {state.status === 'processing' && (
                                        <>
                                            <div className="absolute right-0 top-0 h-full w-8 bg-gradient-to-r from-transparent to-white opacity-30 animate-pulse" />
                                            <div
                                                className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-white to-transparent opacity-20 animate-[shimmer_2s_ease-in-out_infinite]"
                                                style={{
                                                    backgroundSize: '200% 100%',
                                                    animation: 'shimmer 2s ease-in-out infinite',
                                                }}
                                            />
                                        </>
                                    )}
                                </div>
                            </div>

                            {/* Current Step Message */}
                            {state.status === 'processing' && (
                                <div className="mt-3 flex items-center gap-2 text-xs text-gray-600">
                                    <div className="relative">
                                        <Loader2 className="w-3 h-3 animate-spin text-tivit-red" />
                                        <span className="absolute inset-0 w-3 h-3 rounded-full border border-tivit-red animate-ping opacity-75"></span>
                                    </div>
                                    <span className="font-medium animate-pulse">
                                        {state.message}
                                    </span>
                                </div>
                            )}
                        </div>

                        {/* Timeline de Pasos */}
                        <div className="bg-white rounded-xl border border-gray-200 p-4 max-h-[500px] overflow-y-auto">
                            <div className="space-y-3">
                                {PROCESSING_STEPS.map((step, index) => {
                                    const isCompleted =
                                        step.id < state.currentStep || state.status === 'completed';
                                    const isActive =
                                        step.id === state.currentStep &&
                                        state.status === 'processing';
                                    const isPending = step.id > state.currentStep;
                                    const isSkipped =
                                        state.stepStatus === 'skipped' &&
                                        step.id === state.currentStep;
                                    const Icon = step.icon;

                                    return (
                                        <div key={step.id} className="relative">
                                            {/* Connecting Line */}
                                            {index !== PROCESSING_STEPS.length - 1 && (
                                                <div
                                                    className={`absolute left-6 top-12 w-0.5 h-6 transition-colors duration-500 ${
                                                        isCompleted ? 'bg-green-400' : 'bg-gray-200'
                                                    }`}
                                                />
                                            )}

                                            <div
                                                className={`flex items-start gap-3 p-3 rounded-lg transition-all duration-300 ${
                                                    isActive
                                                        ? 'bg-red-50 border-2 border-red-200 shadow-md scale-[1.02]'
                                                        : isCompleted
                                                          ? 'bg-green-50/50 border border-green-100'
                                                          : 'border border-transparent'
                                                }`}
                                            >
                                                {/* Step Icon */}
                                                <div
                                                    className={`relative flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center transition-all duration-300 ${
                                                        isCompleted
                                                            ? 'bg-green-500 text-white shadow-lg shadow-green-200'
                                                            : isSkipped
                                                              ? 'bg-gray-300 text-white'
                                                              : isActive
                                                                ? 'bg-tivit-red text-white shadow-lg shadow-red-200 animate-pulse'
                                                                : 'bg-gray-100 text-gray-400'
                                                    }`}
                                                >
                                                    {isCompleted ? (
                                                        <Check
                                                            className="w-5 h-5"
                                                            strokeWidth={3}
                                                        />
                                                    ) : isSkipped ? (
                                                        <X className="w-5 h-5" />
                                                    ) : isActive ? (
                                                        <Loader2 className="w-5 h-5 animate-spin" />
                                                    ) : (
                                                        <Icon className="w-5 h-5" />
                                                    )}

                                                    {/* Pulse animation ring */}
                                                    {isActive && (
                                                        <span className="absolute inset-0 rounded-full border-2 border-tivit-red animate-ping opacity-75" />
                                                    )}
                                                </div>

                                                {/* Step Details */}
                                                <div className="flex-1 min-w-0 pt-1">
                                                    <div className="flex items-center justify-between mb-1">
                                                        <h4
                                                            className={`font-bold text-sm transition-colors ${
                                                                isActive
                                                                    ? 'text-tivit-red'
                                                                    : isCompleted
                                                                      ? 'text-gray-900'
                                                                      : 'text-gray-500'
                                                            }`}
                                                        >
                                                            {step.label}
                                                        </h4>
                                                        <span
                                                            className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                                                                isCompleted
                                                                    ? 'bg-green-100 text-green-700'
                                                                    : isSkipped
                                                                      ? 'bg-gray-100 text-gray-600'
                                                                      : isActive
                                                                        ? 'bg-red-100 text-tivit-red'
                                                                        : 'bg-gray-100 text-gray-500'
                                                            }`}
                                                        >
                                                            {isCompleted
                                                                ? '✓ Listo'
                                                                : isSkipped
                                                                  ? 'Omitido'
                                                                  : isActive
                                                                    ? step.estimatedTime
                                                                    : step.estimatedTime}
                                                        </span>
                                                    </div>
                                                    <p
                                                        className={`text-xs transition-colors ${
                                                            isActive
                                                                ? 'text-gray-700 font-medium'
                                                                : 'text-gray-500'
                                                        }`}
                                                    >
                                                        {step.description}
                                                    </p>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            {/* Completion Message */}
                            {state.status === 'completed' && (
                                <div className="mt-4 p-3 bg-linear-to-r from-green-50 to-emerald-50 border border-green-200 rounded-lg animate-in fade-in slide-in-from-bottom-2 duration-500">
                                    <div className="flex items-center gap-2 text-green-700">
                                        <Sparkles className="w-4 h-4" />
                                        <span className="text-sm font-bold">
                                            ¡Análisis completado exitosamente!
                                        </span>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* --- 5. Footer: Action Buttons (Sticky) --- */}
                <div className="sticky bottom-0 bg-white z-50 -mx-6 -mb-6 px-6 py-4 border-t border-gray-100 flex sm:justify-between justify-end items-center mt-6">
                    {/* Left side of footer (optional status text) */}
                    <div className="hidden sm:block text-xs text-gray-400">
                        {state.status === 'processing'
                            ? 'Procesando en segundo plano...'
                            : state.status === 'completed'
                              ? 'Proceso finalizado.'
                              : ''}
                    </div>

                    {/* Right side buttons */}
                    <div className="flex gap-3 w-full sm:w-auto">
                        {state.status === 'processing' || state.status === 'pending' ? (
                            <Button
                                variant="outline"
                                onClick={handleClose}
                                className="w-full sm:w-auto border-gray-300 text-gray-700 hover:bg-gray-50"
                            >
                                Cancelar
                            </Button>
                        ) : state.status === 'completed' ? (
                            <>
                                {workspaceId && workspaceId !== 'general' ? (
                                    <>
                                        <Button
                                            onClick={handleClose}
                                            variant="outline"
                                            className="flex-1 sm:flex-none"
                                        >
                                            Subir otro video
                                        </Button>
                                        <Button
                                            onClick={() => {
                                                handleClose();
                                                navigate({ to: `/proyecto/${workspaceId}` });
                                            }}
                                            className="flex-1 sm:flex-none bg-tivit-red hover:bg-tivit-red-dark text-white font-semibold shadow-lg shadow-red-200"
                                        >
                                            Ver Proyecto
                                        </Button>
                                    </>
                                ) : (
                                    <>
                                        <Button
                                            onClick={handleClose}
                                            variant="outline"
                                            className="flex-1 sm:flex-none"
                                        >
                                            Subir otro video
                                        </Button>
                                        <Button
                                            onClick={() => {
                                                handleClose();
                                                navigate({ to: '/mis-videos' });
                                            }}
                                            className="flex-1 sm:flex-none bg-tivit-red hover:bg-tivit-red-dark text-white font-semibold shadow-lg shadow-red-200"
                                        >
                                            Ir a Mis Videos
                                        </Button>
                                    </>
                                )}
                            </>
                        ) : (
                            <>
                                <Button
                                    onClick={handleClose}
                                    variant="outline"
                                    className="flex-1 sm:flex-none"
                                >
                                    Cerrar
                                </Button>
                                {state.error?.canRetry && (
                                    <Button
                                        onClick={handleRetry}
                                        className="flex-1 sm:flex-none bg-tivit-red hover:bg-tivit-red-dark text-white"
                                    >
                                        <RefreshCw className="w-4 h-4 mr-2" />
                                        Reintentar
                                    </Button>
                                )}
                            </>
                        )}
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
