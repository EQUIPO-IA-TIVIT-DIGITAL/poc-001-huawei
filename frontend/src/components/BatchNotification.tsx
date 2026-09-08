import { useState, useEffect, useCallback } from 'react';
import { X, CheckCircle2, XCircle, AlertTriangle, Loader2, ChevronDown, ChevronUp, Film } from 'lucide-react';
import { apiRequest } from '../lib/api';

interface VideoStatus {
    video_id: string;
    nombre: string;
    status: string;
    resultado?: string;
    titulo?: string;
    confianza?: number;
    error?: string;
    step?: number;
    total_steps?: number;
    message?: string;
}

interface BatchStatus {
    batch_id: string;
    status: 'processing' | 'completed';
    resumen: {
        total: number;
        completados: number;
        errores: number;
        procesando: number;
        pendientes: number;
        progreso_pct: number;
    };
    videos: VideoStatus[];
}

interface BatchNotificationProps {
    batchId: string;
    onClose: () => void;
    onComplete?: () => void;
}

export function BatchNotification({ batchId, onClose, onComplete }: BatchNotificationProps) {
    const [batchStatus, setBatchStatus] = useState<BatchStatus | null>(null);
    const [expanded, setExpanded] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isComplete, setIsComplete] = useState(false);

    const fetchStatus = useCallback(async () => {
        try {
            const data = await apiRequest<BatchStatus>(`/socio/batch/${batchId}/status`);
            if (data) {
                setBatchStatus(data);
                if (data.status === 'completed') {
                    setIsComplete(true);
                    if (onComplete) onComplete();
                }
            }
        } catch (err) {
            setError('Error consultando estado del batch');
        }
    }, [batchId, onComplete]);

    // Poll every 2 seconds while processing
    useEffect(() => {
        fetchStatus();
        const interval = setInterval(() => {
            if (!isComplete) {
                fetchStatus();
            }
        }, 2000);
        return () => clearInterval(interval);
    }, [fetchStatus, isComplete]);

    if (!batchStatus) {
        return (
            <div className="fixed bottom-4 right-4 z-50 bg-white rounded-2xl shadow-2xl border border-gray-200 p-4 w-96 animate-in slide-in-from-bottom-5">
                <div className="flex items-center gap-3">
                    <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
                    <span className="text-sm text-gray-700">Conectando...</span>
                </div>
            </div>
        );
    }

    const { resumen, videos } = batchStatus;
    const isProcessing = batchStatus.status === 'processing';

    const getStatusIcon = (video: VideoStatus) => {
        if (video.status === 'aprobado' || video.resultado === 'APROBADO') {
            return <CheckCircle2 className="w-4 h-4 text-green-500" />;
        }
        if (video.status === 'rechazado' || video.resultado === 'RECHAZADO') {
            return <XCircle className="w-4 h-4 text-red-500" />;
        }
        if (video.status === 'error') {
            return <AlertTriangle className="w-4 h-4 text-red-500" />;
        }
        if (video.status === 'en_revision' || video.resultado === 'REQUIERE_REVISION') {
            return <AlertTriangle className="w-4 h-4 text-amber-500" />;
        }
        if (video.status === 'procesando') {
            return (
                <div className="relative">
                    <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
                    <span className="absolute inset-0 w-4 h-4 rounded-full border border-blue-400 animate-ping opacity-75"></span>
                </div>
            );
        }
        return (
            <div className="relative">
                <Loader2 className="w-4 h-4 text-gray-400 animate-pulse" />
            </div>
        );
    };

    const getStatusLabel = (video: VideoStatus) => {
        if (video.resultado === 'APROBADO') return 'Aprobado';
        if (video.resultado === 'RECHAZADO') return 'Rechazado';
        if (video.resultado === 'REQUIERE_REVISION') return 'En revisión';
        if (video.status === 'error') return 'Error';
        if (video.status === 'procesando') {
            const step = video.step || 0;
            const total = video.total_steps || 5;
            return `Paso ${step}/${total}`;
        }
        return 'En cola';
    };

    return (
        <div className="fixed bottom-4 right-4 z-50 bg-white rounded-2xl shadow-2xl border border-gray-200 w-96 animate-in slide-in-from-bottom-5 overflow-hidden">
            {/* Header */}
            <div className="px-4 py-3 bg-gradient-to-r from-blue-50 to-indigo-50 border-b border-gray-100">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="relative w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center">
                            <Film className="w-4 h-4 text-white" />
                            {isProcessing && (
                                <>
                                    <span className="absolute inset-0 rounded-lg bg-blue-400 animate-ping opacity-75"></span>
                                    <span className="absolute inset-0 rounded-lg border-2 border-blue-400 animate-pulse"></span>
                                </>
                            )}
                        </div>
                        <div>
                            <p className="font-semibold text-gray-900 text-sm">
                                {isProcessing ? (
                                    <span className="animate-pulse">Procesando videos...</span>
                                ) : (
                                    'Procesamiento completado'
                                )}
                            </p>
                            <p className="text-xs text-gray-500">
                                {resumen.completados + resumen.errores}/{resumen.total} completados
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-1">
                        <button
                            onClick={() => setExpanded(!expanded)}
                            className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
                        >
                            {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
                        </button>
                        {!isProcessing && (
                            <button
                                onClick={onClose}
                                className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        )}
                    </div>
                </div>

                {/* Progress bar */}
                <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden relative">
                    <div
                        className={`h-full rounded-full transition-all duration-500 ${
                            isProcessing 
                                ? 'bg-gradient-to-r from-blue-500 via-indigo-500 to-blue-600' 
                                : resumen.errores > 0 
                                    ? 'bg-gradient-to-r from-amber-500 to-amber-600'
                                    : 'bg-gradient-to-r from-green-500 to-emerald-600'
                        }`}
                        style={{ width: `${resumen.progreso_pct}%` }}
                    >
                        {isProcessing && (
                            <>
                                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white to-transparent opacity-30 animate-pulse"></div>
                                <div className="absolute right-0 top-0 h-full w-8 bg-gradient-to-r from-transparent to-white opacity-20 animate-pulse"></div>
                            </>
                        )}
                    </div>
                </div>

                {/* Summary chips */}
                {!isProcessing && (
                    <div className="flex gap-2 mt-2 flex-wrap">
                        {resumen.completados > 0 && (
                            <span className="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded-full font-medium">
                                {resumen.completados - resumen.errores} aprobados
                            </span>
                        )}
                        {resumen.errores > 0 && (
                            <span className="text-xs px-2 py-0.5 bg-red-100 text-red-700 rounded-full font-medium">
                                {resumen.errores} errores
                            </span>
                        )}
                    </div>
                )}
            </div>

            {/* Video list (expanded) */}
            {expanded && (
                <div className="max-h-64 overflow-y-auto divide-y divide-gray-50">
                    {videos.map((video) => (
                        <div key={video.video_id} className="px-4 py-2.5 flex items-center gap-3 hover:bg-gray-50 transition-colors">
                            {getStatusIcon(video)}
                            <div className="flex-1 min-w-0">
                                <p className="text-sm text-gray-900 truncate" title={video.nombre}>
                                    {video.titulo || video.nombre}
                                </p>
                                {video.status === 'procesando' && video.message && (
                                    <p className="text-xs text-gray-500 truncate">{video.message}</p>
                                )}
                            </div>
                            <span className={`text-xs font-medium flex-shrink-0 ${
                                video.resultado === 'APROBADO' ? 'text-green-600' :
                                video.resultado === 'RECHAZADO' ? 'text-red-600' :
                                video.resultado === 'REQUIERE_REVISION' ? 'text-amber-600' :
                                video.status === 'error' ? 'text-red-600' :
                                'text-blue-600'
                            }`}>
                                {getStatusLabel(video)}
                            </span>
                        </div>
                    ))}
                </div>
            )}

            {error && (
                <div className="px-4 py-2 bg-red-50 text-red-600 text-xs border-t border-red-100">
                    {error}
                </div>
            )}
        </div>
    );
}
