import { useEffect, useState, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { apiRequest } from '../lib/api';
import { getApiBaseUrl } from '../lib/backendUrl';
import {
    AlertCircle, FileText, Film, Hash, Image, MessageSquare, RotateCcw,
    Timer, Volume2, AlertOctagon, RotateCw,
} from 'lucide-react';
import { Button } from './ui/button';
import { StatusBadge, type AppStatus } from './ui/status-badge';
import { Progress } from './ui/progress';
import { Spinner } from './ui/spinner';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';
import { useTranslation } from '../i18n';
import type { TranslationKey } from '../i18n/es';

interface VideoDetailsModalProps {
    videoId: string | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

interface VideoShot {
    start_time?: string;
    end_time?: string;
    startTimeOffset?: string;
    endTimeOffset?: string;
    start_formatted?: string;
    end_formatted?: string;
}

interface VideoLabel {
    entity?: string;
    categoria?: string;
    confianza?: number;
    description?: string;
    categoryEntities?: Array<{ description?: string }>;
    segments?: Array<{ segment?: { startTimeOffset?: string; endTimeOffset?: string }; confidence?: number }>;
}

interface VideoLogo {
    entity?: string;
    description?: string;
    confianza?: number;
    tracks?: Array<{
        segment?: { startTimeOffset?: string; endTimeOffset?: string };
        confidence?: number;
    }>;
}

interface ExplicitContent {
    pornographyLikelihood?: string;
    frames?: Array<{
        timeOffset?: string;
        pornographyLikelihood?: string;
    }>;
}

interface VideoDetails {
    id: string;
    titulo: string;
    descripcion: string;
    estado: string;
    fecha_carga?: string;
    fecha_procesamiento?: string;
    resultado_ia?: string;
    confianza?: number;
    razon?: string;
    razon_rechazo?: string;
    analisis?: string;
    video_url?: string;
    duracion_segundos?: number;
    shots: VideoShot[];
    texto_detectado: string[];
    labels: VideoLabel[];
    metadatos_ia?: {
        titulo?: string;
        nombre_archivo?: string;
        duracion_segundos?: number;
        storage_uri?: string;
        video_url?: string;
        thumbnail_generado?: boolean;
        fecha_subida?: string;
        resultado_ia?: string;
        confianza_ia?: number;
        razon_decision?: string;
        razon_rechazo?: string;
        analisis_ia?: string;
        gemini_vision?: {
            recomendacion?: string;
            confianza?: number;
            puntuacion_seguridad?: number;
            personas_detectadas?: number;
            descripcion_contenido?: string;
            razon_recomendacion?: string;
            alertas_criticas?: string[];
            banderas_rojas?: string[];
            elementos_detectados?: string[];
            tags_sugeridos?: string[];
            tipo_contenido?: string;
            escenario_principal?: string;
            calidad_visual?: string;
            autenticidad?: number;
        };
        speech_analysis?: {
            success?: boolean;
            tiene_audio?: boolean;
            tiene_voz?: boolean;
            transcripcion?: string;
            confianza_transcripcion?: number;
            duracion_audio?: number;
            idiomas_detectados?: string[];
            palabras_prohibidas?: string[];
            sentimiento?: {
                interpretacion?: string;
                score?: number;
                magnitud?: number;
            };
        };
        decision_deepseek?: {
            aprobado?: boolean;
            confianza?: number;
            razon?: string;
            analisis?: string;
            factores_decision?: string[];
        };
        video_intelligence?: {
            labels?: VideoLabel[];
            shots?: VideoShot[];
            text?: string[];
            logos?: VideoLogo[];
            explicit_content?: ExplicitContent;
        };
    };
}

function resolveVideoUrl(url: string): string {
    return url.startsWith('/') ? `${getApiBaseUrl()}${url}` : url;
}

function getStatus(details: VideoDetails | null): { status: AppStatus; labelKey: TranslationKey } {
    const raw = (details?.resultado_ia || details?.estado || '').toLowerCase();
    if (raw === 'aprobado' || raw === 'completado') {
        return { status: 'approved', labelKey: 'status.approved' };
    }
    if (raw === 'rechazado') {
        return { status: 'rejected', labelKey: 'status.rejected' };
    }
    if (raw === 'en_revision' || raw === 'requiere_revision') {
        return { status: 'pending', labelKey: 'videoModal.statusReview' };
    }
    if (raw === 'procesando') {
        return { status: 'processing', labelKey: 'status.processing' };
    }
    return { status: 'pending', labelKey: 'status.pending' };
}

export function VideoDetailsModal({ videoId, open, onOpenChange }: VideoDetailsModalProps) {
    const { t } = useTranslation();
    const [loading, setLoading] = useState(true);
    const [details, setDetails] = useState<VideoDetails | null>(null);
    const [error, setError] = useState<string | null>(null);
    const videoRef = useRef<HTMLVideoElement>(null);
    const [videoError, setVideoError] = useState(false);

    useEffect(() => {
        if (open && videoId) {
            fetchDetails(videoId);
            setVideoError(false);
        } else {
            setDetails(null);
            setLoading(true);
        }
    }, [open, videoId]);

    const fetchDetails = async (id: string) => {
        setLoading(true);
        setError(null);
        try {
            const response = await apiRequest<{ success: boolean; video: VideoDetails }>(`/socio/video/${id}/details`);
            if (response?.success) {
                setDetails(response.video);
            } else {
                setError(t('videoDetails.loadError'));
            }
        } catch (e) {
            if (e instanceof Error && e.message) {
                setError(e.message);
            } else {
                setError(t('videoDetails.connectionError'));
            }
        } finally {
            setLoading(false);
        }
    };

    const statusInfo = getStatus(details);
    const metadatos = details?.metadatos_ia || {};
    const speechAnalysis = metadatos.speech_analysis || {};
    const rawVideoUrl = metadatos.video_url || details?.video_url;
    const videoUrl = rawVideoUrl ? resolveVideoUrl(rawVideoUrl) : null;
    const confidence = metadatos.confianza_ia || details?.confianza || 0;
    const confidencePercent = Math.round(confidence * 100);
    const confidenceTone =
        confidence >= 0.7 ? 'bg-success' : confidence >= 0.5 ? 'bg-warning' : 'bg-error';

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="flex h-[85vh] max-w-6xl flex-col overflow-hidden p-0">
                <DialogHeader className="flex-row items-center justify-between gap-4 border-b border-border bg-muted/50 px-6 py-3">
                    <div className="flex flex-wrap items-center gap-3">
                        <DialogTitle className="text-lg font-bold">
                            {loading ? t('common.loading') : t('videoModal.title')}
                        </DialogTitle>
                        {!loading && details && (
                            <StatusBadge status={statusInfo.status} label={t(statusInfo.labelKey)} />
                        )}
                    </div>
                    <DialogDescription className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                            <Hash size={12} aria-hidden="true" />
                            {videoId?.slice(0, 8)}...
                        </span>
                    </DialogDescription>
                </DialogHeader>

                {loading ? (
                    <div className="flex flex-1 items-center justify-center bg-muted/30">
                        <Spinner size="xl" className="text-primary" label={t('common.loading')} />
                    </div>
                ) : error ? (
                    <div className="flex flex-1 items-center justify-center p-8">
                        <Alert variant="error" className="max-w-md">
                            <AlertCircle aria-hidden="true" />
                            <AlertTitle>{t('common.error')}</AlertTitle>
                            <AlertDescription>{error}</AlertDescription>
                            <Button
                                variant="outline"
                                size="sm"
                                className="mt-2 w-fit"
                                onClick={() => videoId && fetchDetails(videoId)}
                            >
                                <RotateCcw aria-hidden="true" />
                                {t('common.retry')}
                            </Button>
                        </Alert>
                    </div>
                ) : details ? (
                    <div className="flex flex-1 overflow-hidden">
                        <div className="flex w-3/5 flex-col border-r border-border bg-muted/30">
                            <div className="flex flex-1 items-center justify-center p-4">
                                <div className="aspect-video w-full overflow-hidden rounded-xl bg-black shadow-sm">
                                    {!videoUrl ? (
                                        <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-muted-foreground">
                                            <AlertCircle size={48} aria-hidden="true" />
                                            <p className="text-sm">{t('videoModal.videoUnavailable')}</p>
                                        </div>
                                    ) : videoError ? (
                                        <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-muted-foreground">
                                            <AlertCircle size={48} className="text-error" aria-hidden="true" />
                                            <p className="text-sm">{t('videoModal.videoError')}</p>
                                            <Button variant="outline" size="sm" onClick={() => setVideoError(false)}>
                                                <RotateCw aria-hidden="true" />
                                                {t('common.retry')}
                                            </Button>
                                        </div>
                                    ) : (
                                        <video
                                            ref={videoRef}
                                            src={videoUrl}
                                            className="h-full w-full bg-black object-contain"
                                            controls
                                            playsInline
                                            crossOrigin="use-credentials"
                                            onError={() => setVideoError(true)}
                                        />
                                    )}
                                </div>
                            </div>

                            <div className="border-t border-border bg-card p-3">
                                <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                                    <div className="rounded-lg border border-border bg-muted/40 p-2">
                                        <div className="mb-1 flex items-center gap-1 text-muted-foreground">
                                            <Film size={12} aria-hidden="true" /> {t('videoModal.file')}
                                        </div>
                                        <div className="truncate font-medium text-foreground">
                                            {metadatos.nombre_archivo || t('videoDetails.notAvailable')}
                                        </div>
                                    </div>
                                    <div className="rounded-lg border border-border bg-muted/40 p-2">
                                        <div className="mb-1 flex items-center gap-1 text-muted-foreground">
                                            <Timer size={12} aria-hidden="true" /> {t('videoModal.durationLabel')}
                                        </div>
                                        <div className="font-medium text-foreground">
                                            {metadatos.duracion_segundos || details.duracion_segundos || 0}s
                                        </div>
                                    </div>
                                    <div className="rounded-lg border border-border bg-muted/40 p-2">
                                        <div className="mb-1 flex items-center gap-1 text-muted-foreground">
                                            <Image size={12} aria-hidden="true" /> {t('videoModal.thumbnail')}
                                        </div>
                                        <div className={`font-medium ${metadatos.thumbnail_generado ? 'text-success' : 'text-error'}`}>
                                            {metadatos.thumbnail_generado ? t('videoModal.generated') : t('videoModal.notGenerated')}
                                        </div>
                                    </div>
                                    <div className="rounded-lg border border-border bg-muted/40 p-2">
                                        <div className="mb-1 flex items-center gap-1 text-muted-foreground">
                                            <Volume2 size={12} aria-hidden="true" /> {t('videoModal.audio')}
                                        </div>
                                        <div className={`font-medium ${speechAnalysis.tiene_audio ? 'text-success' : 'text-muted-foreground'}`}>
                                            {speechAnalysis.tiene_audio
                                                ? speechAnalysis.tiene_voz
                                                    ? t('videoModal.withVoice')
                                                    : t('videoModal.withoutVoice')
                                                : t('videoModal.noAudio')}
                                        </div>
                                    </div>
                                </div>

                                <div className="mt-3 flex items-center gap-3">
                                    <span className="text-xs text-muted-foreground">{t('videoModal.aiConfidence')}</span>
                                    <Progress
                                        value={confidencePercent}
                                        indicatorClassName={confidenceTone}
                                        className="flex-1"
                                        aria-label={t('videoModal.aiConfidence')}
                                    />
                                    <span className="text-sm font-bold text-foreground">{confidencePercent}%</span>
                                </div>
                            </div>
                        </div>

                        <div className="flex w-2/5 flex-col bg-muted/30">
                            <div className="flex-1 space-y-3 overflow-y-auto p-4">
                                <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <div className="mb-1 text-xs text-muted-foreground">
                                                {t('videoModal.resultTitle')}
                                            </div>
                                            <StatusBadge
                                                status={statusInfo.status}
                                                label={t(statusInfo.labelKey)}
                                            />
                                        </div>
                                        <div className="text-right">
                                            <div className="text-3xl font-bold text-foreground">{confidencePercent}%</div>
                                            <div className="text-xs text-muted-foreground">
                                                {t('videoModal.confidence')}
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                    <div className="mb-2 flex items-center gap-1 text-xs text-muted-foreground">
                                        <FileText size={12} aria-hidden="true" /> {t('videoModal.titleLabel')}
                                    </div>
                                    <p className="text-sm font-medium text-foreground">
                                        {details.titulo || t('videoModal.noTitle')}
                                    </p>
                                </div>

                                {(metadatos.razon_rechazo || details.razon_rechazo) && (
                                    <div className="rounded-xl border border-error-border bg-error-surface p-4">
                                        <div className="mb-2 flex items-center gap-1 text-xs font-bold text-error">
                                            <AlertOctagon size={12} aria-hidden="true" /> {t('videoModal.rejectionReason')}
                                        </div>
                                        <p className="text-sm text-foreground">
                                            {metadatos.razon_rechazo || details.razon_rechazo}
                                        </p>
                                    </div>
                                )}

                                {metadatos.razon_decision && (
                                    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                        <div className="mb-2 flex items-center gap-1 text-xs text-muted-foreground">
                                            <MessageSquare size={12} aria-hidden="true" /> {t('videoModal.decision')}
                                        </div>
                                        <p className="text-sm text-muted-foreground">{metadatos.razon_decision}</p>
                                    </div>
                                )}

                                <div className="grid grid-cols-2 gap-2">
                                    <div className="rounded-lg border border-border bg-card p-3 shadow-sm">
                                        <div className="text-xs text-muted-foreground">{t('videoModal.statusLabel')}</div>
                                        <div className="font-medium capitalize text-foreground">{details.estado}</div>
                                    </div>
                                    <div className="rounded-lg border border-border bg-card p-3 shadow-sm">
                                        <div className="text-xs text-muted-foreground">{t('videoModal.durationLabel')}</div>
                                        <div className="font-medium text-foreground">
                                            {metadatos.duracion_segundos || details.duracion_segundos || 0}s
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                ) : null}
            </DialogContent>
        </Dialog>
    );
}
