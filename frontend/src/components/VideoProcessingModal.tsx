import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
    Check,
    Loader2,
    AlertCircle,
    RefreshCw,
    CheckCircle2,
    XCircle,
    Clock,
    FileVideo,
    Upload,
    Timer,
    Eye,
    Brain,
    Sparkles,
} from 'lucide-react';
import { Button } from './ui/button';
import { videoService } from '../services/video';
import { useNavigate } from '@tanstack/react-router';
import { useQueryClient } from '@tanstack/react-query';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Progress } from './ui/progress';
import { Spinner } from './ui/spinner';
import { useTranslation } from '../i18n';
import type { TranslationKey } from '../i18n/es';

interface ProcessingStep {
    id: number;
    labelKey: TranslationKey;
    icon: LucideIcon;
    estimatedTime: string;
    descriptionKey: TranslationKey;
}

const PROCESSING_STEPS: ProcessingStep[] = [
    {
        id: 1,
        labelKey: 'videoProcessing.stepPreparation',
        icon: Upload,
        estimatedTime: '~5s',
        descriptionKey: 'videoProcessing.stepPreparationDesc',
    },
    {
        id: 2,
        labelKey: 'videoProcessing.stepVerification',
        icon: Timer,
        estimatedTime: '~2s',
        descriptionKey: 'videoProcessing.stepVerificationDesc',
    },
    {
        id: 3,
        labelKey: 'videoProcessing.stepQuickScan',
        icon: Eye,
        estimatedTime: '~5s',
        descriptionKey: 'videoProcessing.stepQuickScanDesc',
    },
    {
        id: 4,
        labelKey: 'videoProcessing.stepDeepAnalysis',
        icon: Brain,
        estimatedTime: '~15s',
        descriptionKey: 'videoProcessing.stepDeepAnalysisDesc',
    },
    {
        id: 5,
        labelKey: 'videoProcessing.stepDecision',
        icon: Sparkles,
        estimatedTime: '~5s',
        descriptionKey: 'videoProcessing.stepDecisionDesc',
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
    video_url?: string;
}

interface ProcessingError {
    errorCode: string;
    message: string;
    canRetry: boolean;
}

interface ClarificationQuestion {
    id: string;
    question: string;
}

interface ProcessingState {
    currentStep: number;
    stepStatus: 'running' | 'success' | 'warning' | 'error' | 'skipped' | 'pending';
    status: 'pending' | 'processing' | 'completed' | 'error' | 'cancelled' | 'clarification';
    message: string;
    details?: unknown;
    videoResult?: VideoResult;
    error?: ProcessingError;
    finalStatus?: 'approved' | 'rejected' | 'review' | 'unknown';
    clarificationQuestions?: ClarificationQuestion[];
}

interface StatusResponse {
    status?: string;
    step?: number;
    message?: string;
    details?: { errorCode?: string; canRetry?: boolean };
    error?: ProcessingError;
    final_result?: {
        video?: VideoResult & { video_url?: string };
        finalStatus?: ProcessingState['finalStatus'];
    };
}

interface VideoProcessingModalProps {
    videoId: string | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    videoFile?: File | null;
    onRetry?: () => void;
    workspaceId?: string;
}

const RESULT_STYLES: Record<
    NonNullable<ProcessingState['finalStatus']>,
    { surface: string; text: string; Icon: LucideIcon; labelKey: TranslationKey }
> = {
    approved: {
        surface: 'bg-success-surface border-success-border',
        text: 'text-success',
        Icon: CheckCircle2,
        labelKey: 'videoProcessing.approved',
    },
    rejected: {
        surface: 'bg-error-surface border-error-border',
        text: 'text-error',
        Icon: XCircle,
        labelKey: 'videoProcessing.rejected',
    },
    review: {
        surface: 'bg-warning-surface border-warning-border',
        text: 'text-warning',
        Icon: Clock,
        labelKey: 'videoProcessing.needsReview',
    },
    unknown: {
        surface: 'bg-muted border-border',
        text: 'text-muted-foreground',
        Icon: FileVideo,
        labelKey: 'videoProcessing.resultUnknown',
    },
};

export function VideoProcessingModal({
    videoId,
    open,
    onOpenChange,
    videoFile,
    onRetry,
    workspaceId,
}: VideoProcessingModalProps) {
    const { t } = useTranslation();
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
        message: t('videoProcessing.init'),
    });

    const [videoUrl, setVideoUrl] = useState<string | null>(null);

    const steps = useMemo(
        () =>
            PROCESSING_STEPS.map((step) => ({
                ...step,
                label: t(step.labelKey),
                description: t(step.descriptionKey),
            })),
        [t],
    );

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
        (response: StatusResponse | null | undefined) => {
            if (!response) return;

            if (response.status === 'completed' && response.final_result) {
                const resultVideo = response.final_result.video;
                setState((s) => ({
                    ...s,
                    currentStep: 6,
                    status: 'completed',
                    stepStatus: 'success',
                    message: response.message || t('status.completed'),
                    videoResult: resultVideo,
                    finalStatus: response.final_result?.finalStatus,
                }));

                if (resultVideo?.video_url) {
                    setVideoUrl(resultVideo.video_url);
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
                    message: response.message || t('audio.errorUnknown'),
                    currentStep: response.step || s.currentStep,
                    error: response.error || {
                        errorCode: response.details?.errorCode || 'UNKNOWN_ERROR',
                        message: response.message || t('audio.errorUnknown'),
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
                    message: response.message || t('status.cancelled'),
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
                    message: response.message || t('status.processing'),
                    status: 'processing',
                    details: response.details,
                }));
            }
        },
        [invalidateVideoQueries, stopPolling, stopStream, t],
    );

    useEffect(() => {
        if (videoFile) {
            const url = URL.createObjectURL(videoFile);
            setVideoUrl(url);
            return () => URL.revokeObjectURL(url);
        } else {
            setVideoUrl(null);
        }
    }, [videoFile]);

    const pollStatus = useCallback(async () => {
        if (!videoId) return;

        try {
            const response = await videoService.getVideoStatus(videoId);
            if (!response) return;
            applyStatusUpdate(response);
        } catch {
            // No detenemos el polling por errores de red temporales
        }
    }, [videoId, applyStatusUpdate]);

    const startPolling = useCallback(() => {
        if (pollingIntervalRef.current) return;
        void pollStatus();
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
                    const payload = JSON.parse(event.data) as StatusResponse;
                    applyStatusUpdate(payload);
                } catch {
                    // Ignora payloads SSE inválidos
                }
            };

            stream.onerror = () => {
                if (!sseFailedRef.current) {
                    sseFailedRef.current = true;
                    stopStream();
                    startPolling();
                }
            };
        } catch {
            startPolling();
        }
    }, [videoId, applyStatusUpdate, startPolling, stopStream]);

    useEffect(() => {
        if (!videoId || !open) {
            stopPolling();
            stopStream();
            setState({
                currentStep: 0,
                stepStatus: 'pending',
                status: 'pending',
                message: t('videoProcessing.waitingVideo'),
            });
            return;
        }

        sseFailedRef.current = false;

        const startProcessing = async () => {
            try {
                await videoService.startProcessing(videoId);
            } catch {
                // El procesamiento puede estar ya en curso
            }
        };

        void startProcessing().then(() => {
            startStatusStream();
        });

        return () => {
            stopPolling();
            stopStream();
        };
    }, [videoId, open, startStatusStream, stopPolling, stopStream, t]);

    const handleClose = async () => {
        if ((state.status === 'processing' || state.status === 'pending') && videoId) {
            try {
                await videoService.cancelProcessing(videoId);
            } catch {
                // Ignora errores al cancelar
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
        void handleClose();
    };

    const currentProgress = Math.min(state.currentStep, 5);
    const resultStyle = RESULT_STYLES[state.finalStatus ?? 'unknown'];
    const ResultIcon = resultStyle.Icon;

    const headerTitle =
        state.status === 'processing'
            ? t('videoProcessing.processingTitle')
            : state.status === 'completed'
                ? t('videoProcessing.completedTitle')
                : state.status === 'error'
                    ? t('videoProcessing.errorTitleProcessing')
                    : state.status === 'cancelled'
                        ? t('videoProcessing.cancelledTitle')
                        : t('videoProcessing.preparingTitle');

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
                className="max-h-[90vh] max-w-6xl overflow-y-auto"
                onInteractOutside={(e: Event) => {
                    e.preventDefault();
                }}
            >
                <DialogHeader className="flex-row items-center justify-between pb-1">
                    <div className="text-left">
                        <DialogTitle className="flex items-center gap-2 text-lg font-bold">
                            {state.status === 'processing' && (
                                <Loader2 className="h-5 w-5 animate-spin text-primary" aria-hidden="true" />
                            )}
                            {state.status === 'completed' && (
                                <Check className="h-5 w-5 text-success" aria-hidden="true" />
                            )}
                            {state.status === 'error' && (
                                <AlertCircle className="h-5 w-5 text-error" aria-hidden="true" />
                            )}
                            {state.status === 'cancelled' && (
                                <XCircle className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
                            )}
                            {headerTitle}
                        </DialogTitle>
                        <DialogDescription className="text-xs text-muted-foreground">
                            {t('videoProcessing.idLabel', { id: videoId ?? '' })}
                        </DialogDescription>
                    </div>
                </DialogHeader>

                {state.status === 'completed' && state.videoResult && (
                    <div
                        className={`mx-1 mt-2 flex items-center overflow-hidden rounded-xl border shadow-sm ${resultStyle.surface}`}
                        role="status"
                        aria-live="polite"
                    >
                        <div className={`flex items-center justify-center border-r border-border p-2 ${resultStyle.text}`}>
                            <ResultIcon className="h-6 w-6" aria-hidden="true" />
                        </div>
                        <div className="flex-1 px-3 py-2">
                            <h4 className={`text-base font-bold ${resultStyle.text}`}>
                                {t(resultStyle.labelKey)}
                            </h4>
                            <p className="text-xs font-medium text-muted-foreground">
                                {t('videoProcessing.confidenceDecision', {
                                    percent: state.videoResult.confianzaPorcentaje ?? 0,
                                })}
                            </p>
                        </div>
                    </div>
                )}

                <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-5">
                    <div className="flex flex-col space-y-6 md:col-span-3">
                        <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-xl border border-border bg-black shadow-sm">
                            {videoUrl ? (
                                <video
                                    ref={videoRef}
                                    src={videoUrl}
                                    className="h-full w-full object-contain"
                                    autoPlay
                                    muted
                                    loop
                                    playsInline
                                    controls
                                />
                            ) : (
                                <div className="flex flex-col items-center gap-2 px-6 text-center text-white/70">
                                    <FileVideo size={48} aria-hidden="true" />
                                    <p className="font-medium text-white">{t('videoProcessing.videoUnavailable')}</p>
                                    <p className="text-sm">{t('videoProcessing.videoUnavailableHint')}</p>
                                </div>
                            )}

                            {state.status === 'error' && (
                                <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-black/80">
                                    <AlertCircle size={48} className="mb-2 text-error" aria-hidden="true" />
                                    <h3 className="text-lg font-bold text-white">
                                        {t('videoProcessing.analysisError')}
                                    </h3>
                                    <p className="max-w-md px-4 text-center text-sm text-white/80">
                                        {state.message}
                                    </p>
                                </div>
                            )}

                            {state.status === 'completed' && state.videoResult && (
                                <div className="absolute right-4 top-4 z-20">
                                    <span
                                        className={`rounded-full px-3 py-1 text-xs font-bold text-white shadow-lg ${state.finalStatus === 'approved'
                                            ? 'bg-success'
                                            : state.finalStatus === 'rejected'
                                                ? 'bg-error'
                                                : 'bg-warning'
                                            }`}
                                    >
                                        {t(resultStyle.labelKey)}
                                    </span>
                                </div>
                            )}
                        </div>

                        {(state.status === 'error' || state.status === 'cancelled') && state.error && (
                            <div className="rounded-xl border border-error-border bg-error-surface p-6 shadow-sm">
                                <div className="flex items-start gap-4">
                                    <div className="rounded-full bg-error-surface p-2 text-error">
                                        <AlertCircle className="h-6 w-6" aria-hidden="true" />
                                    </div>
                                    <div className="flex-1">
                                        <h4 className="mb-1 text-lg font-bold text-error">
                                            {state.status === 'cancelled'
                                                ? t('videoProcessing.cancelledBanner')
                                                : t('videoProcessing.errorBanner')}
                                        </h4>
                                        <p className="text-sm leading-relaxed text-foreground">
                                            {state.error.message}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        )}

                        {state.status === 'completed' && state.videoResult && (
                            <div className="space-y-4">
                                <div>
                                    <p className="mb-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">
                                        {t('videoProcessing.generatedTitle')}
                                    </p>
                                    <h3 className="text-xl font-bold leading-tight text-foreground">
                                        {state.videoResult.titulo}
                                    </h3>
                                </div>

                                {state.videoResult.razon && (
                                    <div className="rounded-lg border border-border bg-muted/40 p-4">
                                        <p className="text-sm font-medium leading-relaxed text-muted-foreground">
                                            <span className="mb-1 block font-bold text-foreground">
                                                {t('videoProcessing.decisionReasonLabel')}
                                            </span>
                                            {state.videoResult.razon}
                                        </p>
                                    </div>
                                )}

                                {state.videoResult.analisis && (
                                    <details className="pt-2">
                                        <summary className="cursor-pointer text-sm font-semibold text-primary hover:underline">
                                            {t('videoProcessing.technicalAnalysis')}
                                        </summary>
                                        <div className="mt-3 rounded border border-border bg-muted/40 p-3 font-mono text-xs leading-relaxed text-muted-foreground">
                                            {state.videoResult.analisis}
                                        </div>
                                    </details>
                                )}
                            </div>
                        )}
                    </div>

                    <div className="space-y-4 md:col-span-2">
                        <div className="rounded-xl border border-border bg-muted/40 p-4 shadow-sm">
                            <div className="mb-3 flex items-center justify-between">
                                <h3 className="text-sm font-bold uppercase tracking-wide text-foreground">
                                    {t('videoProcessing.analysisProgressTitle')}
                                </h3>
                                <span className="text-xs font-medium text-muted-foreground">
                                    {t('videoProcessing.stepOf', { current: currentProgress })}
                                </span>
                            </div>

                            <Progress
                                value={(currentProgress / 5) * 100}
                                aria-label={t('videoProcessing.analysisProgressTitle')}
                            />

                            {state.status === 'processing' && (
                                <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground" aria-live="polite">
                                    <Loader2 className="h-3 w-3 animate-spin text-primary" aria-hidden="true" />
                                    <span className="animate-pulse font-medium">{state.message}</span>
                                </div>
                            )}
                        </div>

                        <div className="max-h-[500px] overflow-y-auto rounded-xl border border-border bg-card p-4">
                            <div className="space-y-3">
                                {steps.map((step, index) => {
                                    const isCompleted =
                                        step.id < state.currentStep || state.status === 'completed';
                                    const isActive =
                                        step.id === state.currentStep && state.status === 'processing';
                                    const isSkipped =
                                        state.stepStatus === 'skipped' && step.id === state.currentStep;
                                    const Icon = step.icon;

                                    return (
                                        <div key={step.id} className="relative">
                                            {index !== steps.length - 1 && (
                                                <div
                                                    className={`absolute left-6 top-12 h-6 w-0.5 transition-colors duration-500 ${isCompleted ? 'bg-success' : 'bg-border'
                                                        }`}
                                                />
                                            )}

                                            <div
                                                className={`flex items-start gap-3 rounded-lg p-3 transition-all duration-300 ${isActive
                                                    ? 'border-2 border-brand-border bg-brand-soft shadow-sm'
                                                    : isCompleted
                                                        ? 'border border-success-border bg-success-surface/50'
                                                        : 'border border-transparent'
                                                    }`}
                                            >
                                                <div
                                                    className={`relative flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full transition-all duration-300 ${isCompleted
                                                        ? 'bg-success text-success-foreground'
                                                        : isSkipped
                                                            ? 'bg-muted text-muted-foreground'
                                                            : isActive
                                                                ? 'bg-primary text-primary-foreground'
                                                                : 'bg-muted text-muted-foreground'
                                                        }`}
                                                >
                                                    {isCompleted ? (
                                                        <Check className="h-5 w-5" strokeWidth={3} aria-hidden="true" />
                                                    ) : isSkipped ? (
                                                        <XCircle className="h-5 w-5" aria-hidden="true" />
                                                    ) : isActive ? (
                                                        <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
                                                    ) : (
                                                        <Icon className="h-5 w-5" aria-hidden="true" />
                                                    )}

                                                    {isActive && (
                                                        <span className="absolute inset-0 animate-ping rounded-full border-2 border-primary opacity-75" />
                                                    )}
                                                </div>

                                                <div className="min-w-0 flex-1 pt-1">
                                                    <div className="mb-1 flex items-center justify-between">
                                                        <h4
                                                            className={`text-sm font-bold transition-colors ${isActive
                                                                ? 'text-primary'
                                                                : isCompleted
                                                                    ? 'text-foreground'
                                                                    : 'text-muted-foreground'
                                                                }`}
                                                        >
                                                            {step.label}
                                                        </h4>
                                                        <span
                                                            className={`rounded-full px-2 py-0.5 text-xs font-medium ${isCompleted
                                                                ? 'bg-success-surface text-success'
                                                                : isSkipped
                                                                    ? 'bg-muted text-muted-foreground'
                                                                    : isActive
                                                                        ? 'bg-brand-soft text-brand-hover'
                                                                        : 'bg-muted text-muted-foreground'
                                                                }`}
                                                        >
                                                            {isCompleted
                                                                ? t('videoProcessing.done')
                                                                : isSkipped
                                                                    ? t('videoProcessing.skipped')
                                                                    : step.estimatedTime}
                                                        </span>
                                                    </div>
                                                    <p
                                                        className={`text-xs transition-colors ${isActive ? 'font-medium text-foreground' : 'text-muted-foreground'
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

                            {state.status === 'completed' && (
                                <div className="mt-4 rounded-lg border border-success-border bg-success-surface p-3">
                                    <div className="flex items-center gap-2 text-success">
                                        <Sparkles className="h-4 w-4" aria-hidden="true" />
                                        <span className="text-sm font-bold">
                                            {t('videoProcessing.completedMessage')}
                                        </span>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                <div className="sticky bottom-0 z-50 -mx-6 -mb-6 mt-6 flex items-center justify-end border-t border-border bg-card px-6 py-4 sm:justify-between">
                    <div className="hidden text-xs text-muted-foreground sm:block" aria-live="polite">
                        {state.status === 'processing'
                            ? t('videoProcessing.background')
                            : state.status === 'completed'
                                ? t('videoProcessing.finished')
                                : ''}
                    </div>

                    <div className="flex w-full gap-3 sm:w-auto">
                        {state.status === 'processing' || state.status === 'pending' ? (
                            <Button variant="outline" onClick={handleClose} className="w-full sm:w-auto">
                                {t('common.cancel')}
                            </Button>
                        ) : state.status === 'completed' ? (
                            <>
                                {workspaceId && workspaceId !== 'general' ? (
                                    <>
                                        <Button onClick={handleClose} variant="outline" className="flex-1 sm:flex-none">
                                            {t('videoProcessing.uploadAnother')}
                                        </Button>
                                        <Button
                                            onClick={() => {
                                                void handleClose();
                                                navigate({ to: `/proyecto/${workspaceId}` });
                                            }}
                                            className="flex-1 sm:flex-none"
                                        >
                                            {t('videoProcessing.viewProject')}
                                        </Button>
                                    </>
                                ) : (
                                    <>
                                        <Button onClick={handleClose} variant="outline" className="flex-1 sm:flex-none">
                                            {t('videoProcessing.uploadAnother')}
                                        </Button>
                                        <Button
                                            onClick={() => {
                                                void handleClose();
                                                navigate({ to: '/mis-videos' });
                                            }}
                                            className="flex-1 sm:flex-none"
                                        >
                                            {t('videoProcessing.goToMyVideos')}
                                        </Button>
                                    </>
                                )}
                            </>
                        ) : (
                            <>
                                <Button onClick={handleClose} variant="outline" className="flex-1 sm:flex-none">
                                    {t('common.close')}
                                </Button>
                                {state.error?.canRetry && (
                                    <Button onClick={handleRetry} className="flex-1 sm:flex-none">
                                        <RefreshCw className="h-4 w-4" aria-hidden="true" />
                                        {t('common.retry')}
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
