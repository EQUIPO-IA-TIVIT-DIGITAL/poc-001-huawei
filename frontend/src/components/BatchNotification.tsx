import { useState, useEffect, useCallback } from 'react';
import {
    X, CheckCircle2, XCircle, AlertTriangle, Loader2, ChevronDown, ChevronUp, Film,
} from 'lucide-react';
import { apiRequest } from '../lib/api';
import { Progress } from './ui/progress';
import { Button } from './ui/button';
import { useTranslation } from '../i18n';
import type { TranslationKey } from '../i18n/es';

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

function getStatusIcon(video: VideoStatus) {
    if (video.status === 'aprobado' || video.resultado === 'APROBADO') {
        return <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />;
    }
    if (video.status === 'rechazado' || video.resultado === 'RECHAZADO') {
        return <XCircle className="h-4 w-4 text-error" aria-hidden="true" />;
    }
    if (video.status === 'error') {
        return <AlertTriangle className="h-4 w-4 text-error" aria-hidden="true" />;
    }
    if (video.status === 'en_revision' || video.resultado === 'REQUIERE_REVISION') {
        return <AlertTriangle className="h-4 w-4 text-warning" aria-hidden="true" />;
    }
    if (video.status === 'procesando') {
        return (
            <div className="relative">
                <Loader2 className="h-4 w-4 animate-spin text-info" aria-hidden="true" />
                <span className="absolute inset-0 animate-ping rounded-full border border-info opacity-75" />
            </div>
        );
    }
    return <Loader2 className="h-4 w-4 animate-pulse text-muted-foreground" aria-hidden="true" />;
}

function getStatusLabel(video: VideoStatus, t: (key: TranslationKey, vars?: Record<string, string | number>) => string) {
    if (video.resultado === 'APROBADO') return t('batch.statusApproved');
    if (video.resultado === 'RECHAZADO') return t('batch.statusRejected');
    if (video.resultado === 'REQUIERE_REVISION') return t('batch.statusReview');
    if (video.status === 'error') return t('batch.statusError');
    if (video.status === 'procesando') {
        return t('batch.statusStep', {
            step: video.step || 0,
            total: video.total_steps || 5,
        });
    }
    return t('batch.statusQueued');
}

export function BatchNotification({ batchId, onClose, onComplete }: BatchNotificationProps) {
    const { t } = useTranslation();
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
        } catch {
            setError(t('batch.loadError'));
        }
    }, [batchId, onComplete, t]);

    useEffect(() => {
        void fetchStatus();
        const interval = setInterval(() => {
            if (!isComplete) {
                void fetchStatus();
            }
        }, 2000);
        return () => clearInterval(interval);
    }, [fetchStatus, isComplete]);

    if (!batchStatus) {
        return (
            <div className="fixed bottom-4 right-4 z-50 w-96 rounded-2xl border border-border bg-card p-4 shadow-popover">
                <div className="flex items-center gap-3" aria-live="polite">
                    <Loader2 className="h-5 w-5 animate-spin text-primary" aria-hidden="true" />
                    <span className="text-sm text-muted-foreground">{t('batch.connecting')}</span>
                </div>
            </div>
        );
    }

    const { resumen, videos } = batchStatus;
    const isProcessing = batchStatus.status === 'processing';
    const progressTone = isProcessing
        ? 'bg-primary'
        : resumen.errores > 0
            ? 'bg-warning'
            : 'bg-success';

    return (
        <div
            className="fixed bottom-4 right-4 z-50 w-96 overflow-hidden rounded-2xl border border-border bg-card shadow-popover"
            aria-live="polite"
        >
            <div className="border-b border-border bg-muted/40 px-4 py-3">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
                            <Film className="h-4 w-4 text-primary-foreground" aria-hidden="true" />
                            {isProcessing && (
                                <span className="absolute inset-0 animate-ping rounded-lg bg-primary opacity-40" />
                            )}
                        </div>
                        <div>
                            <p className="text-sm font-semibold text-foreground">
                                {isProcessing ? (
                                    <span className="animate-pulse">{t('batch.processing')}</span>
                                ) : (
                                    t('batch.completedTitle')
                                )}
                            </p>
                            <p className="text-xs text-muted-foreground">
                                {t('batch.progressCount', {
                                    done: resumen.completados + resumen.errores,
                                    total: resumen.total,
                                })}
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-1">
                        <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={expanded ? t('batch.collapse') : t('batch.expand')}
                            aria-expanded={expanded}
                            onClick={() => setExpanded(!expanded)}
                        >
                            {expanded ? (
                                <ChevronDown aria-hidden="true" />
                            ) : (
                                <ChevronUp aria-hidden="true" />
                            )}
                        </Button>
                        {!isProcessing && (
                            <Button
                                variant="ghost"
                                size="icon-sm"
                                aria-label={t('batch.close')}
                                onClick={onClose}
                            >
                                <X aria-hidden="true" />
                            </Button>
                        )}
                    </div>
                </div>

                <Progress
                    value={resumen.progreso_pct}
                    indicatorClassName={progressTone}
                    className="mt-2"
                    aria-label={t('batch.progressLabel')}
                />

                {!isProcessing && (
                    <div className="mt-2 flex flex-wrap gap-2">
                        {resumen.completados > 0 && (
                            <span className="rounded-full bg-success-surface px-2 py-0.5 text-xs font-medium text-success">
                                {t('batch.approvedCount', {
                                    count: resumen.completados - resumen.errores,
                                })}
                            </span>
                        )}
                        {resumen.errores > 0 && (
                            <span className="rounded-full bg-error-surface px-2 py-0.5 text-xs font-medium text-error">
                                {t('batch.errorCount', { count: resumen.errores })}
                            </span>
                        )}
                    </div>
                )}
            </div>

            {expanded && (
                <div
                    className="max-h-64 divide-y divide-border overflow-y-auto"
                    aria-label={t('batch.listLabel')}
                >
                    {videos.map((video) => (
                        <div
                            key={video.video_id}
                            className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-muted/40"
                        >
                            {getStatusIcon(video)}
                            <div className="min-w-0 flex-1">
                                <p className="truncate text-sm text-foreground" title={video.nombre}>
                                    {video.titulo || video.nombre}
                                </p>
                                {video.status === 'procesando' && video.message && (
                                    <p className="truncate text-xs text-muted-foreground">{video.message}</p>
                                )}
                            </div>
                            <span
                                className={`flex-shrink-0 text-xs font-medium ${video.resultado === 'APROBADO'
                                    ? 'text-success'
                                    : video.resultado === 'RECHAZADO'
                                        ? 'text-error'
                                        : video.resultado === 'REQUIERE_REVISION'
                                            ? 'text-warning'
                                            : video.status === 'error'
                                                ? 'text-error'
                                                : 'text-info'
                                    }`}
                            >
                                {getStatusLabel(video, t)}
                            </span>
                        </div>
                    ))}
                </div>
            )}

            {error && (
                <div className="border-t border-error-border bg-error-surface px-4 py-2 text-xs text-error">
                    {error}
                </div>
            )}
        </div>
    );
}
