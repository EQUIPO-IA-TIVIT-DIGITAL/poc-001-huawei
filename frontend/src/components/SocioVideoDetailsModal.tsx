import { useEffect, useState, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs';
import { videoService, Video } from '../services/video';
import {
    AlertCircle, Calendar, RotateCcw,
    Info, Timer, Hash, MessageSquare, Film, Sparkles, FileText, Volume2, VolumeX,
    Mic, AlertOctagon, Image,
} from 'lucide-react';
import { Button } from './ui/button';
import { StatusBadge, type AppStatus } from './ui/status-badge';
import { Progress } from './ui/progress';
import { Spinner } from './ui/spinner';
import { getApiBaseUrl } from '../lib/backendUrl';
import { useTranslation } from '../i18n';
import type { TranslationKey } from '../i18n/es';

interface SocioVideoDetailsModalProps {
    video: Video | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

interface GeminiVision {
    recomendacion?: string;
    confianza?: number;
    puntuacion_seguridad?: number;
    descripcion_contenido?: string;
    elementos_detectados?: string[];
    tags_sugeridos?: string[];
    tipo_contenido?: string;
    escenario_principal?: string;
    calidad_visual?: string;
}

interface SpeechAnalysis {
    success?: boolean;
    tiene_audio?: boolean;
    tiene_voz?: boolean;
    transcripcion?: string;
    confianza_transcripcion?: number;
    duracion_audio?: number;
    idiomas_detectados?: string[];
    sentimiento?: { interpretacion?: string };
}

interface VideoMetadata {
    titulo?: string;
    nombre_archivo?: string;
    duracion_segundos?: number;
    video_url?: string;
    thumbnail_generado?: boolean;
    fecha_subida?: string;
    resultado_ia?: string;
    confianza_ia?: number;
    razon_decision?: string;
    razon_rechazo?: string;
    gemini_vision?: GeminiVision;
    speech_analysis?: SpeechAnalysis;
}

type DetailTab = 'resumen' | 'gemini' | 'audio';

function resolveVideoUrl(url: string): string {
    return url.startsWith('/') ? `${getApiBaseUrl()}${url}` : url;
}

function getStatus(video: Video, metadatos: VideoMetadata): { status: AppStatus; labelKey: TranslationKey } {
    const estado = video.estado;
    const resultado = video.resultado_ia || metadatos.resultado_ia;

    if (estado === 'completado' || estado === 'aprobado' || resultado === 'APROBADO') {
        return { status: 'approved', labelKey: 'status.approved' };
    }
    if (estado === 'rechazado' || resultado === 'RECHAZADO') {
        return { status: 'rejected', labelKey: 'status.rejected' };
    }
    if (estado === 'en_revision' || resultado === 'REQUIERE_REVISION') {
        return { status: 'pending', labelKey: 'videoModal.statusReview' };
    }
    if (estado === 'procesando') {
        return { status: 'processing', labelKey: 'status.processing' };
    }
    return { status: 'pending', labelKey: 'status.pending' };
}

export function SocioVideoDetailsModal({ video, open, onOpenChange }: SocioVideoDetailsModalProps) {
    const { t } = useTranslation();
    const [activeTab, setActiveTab] = useState<DetailTab>('resumen');
    const videoRef = useRef<HTMLVideoElement>(null);
    const [videoUrl, setVideoUrl] = useState<string | null>(null);
    const [videoError, setVideoError] = useState(false);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (open && video) {
            setActiveTab('resumen');
            setVideoError(false);
            const metaUrl = video.metadatos_ia?.video_url || video.video_url;
            if (metaUrl) {
                setVideoUrl(resolveVideoUrl(metaUrl));
            } else {
                void fetchSignedUrl(video.id);
            }
        } else {
            setVideoUrl(null);
        }
    }, [open, video]);

    const fetchSignedUrl = async (videoId: string) => {
        setLoading(true);
        try {
            const res = await videoService.getSignedUrl(videoId);
            if (res && res.signed_url) {
                setVideoUrl(resolveVideoUrl(res.signed_url));
            }
        } catch {
            setVideoError(true);
        } finally {
            setLoading(false);
        }
    };

    if (!video) return null;

    const metadatos = (video.metadatos_ia || {}) as VideoMetadata;
    const geminiVision = metadatos.gemini_vision || {};
    const speechAnalysis = metadatos.speech_analysis || {};
    const statusInfo = getStatus(video, metadatos);
    const confidence = metadatos.confianza_ia || 0;
    const confidencePercent = Math.round(confidence * 100);
    const confidenceTone =
        confidence >= 0.7 ? 'bg-success' : confidence >= 0.5 ? 'bg-warning' : 'bg-error';
    const geminiConfidence = geminiVision.confianza || 0;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="flex h-[85vh] max-w-6xl flex-col overflow-hidden p-0">
                <DialogHeader className="flex-row items-center justify-between gap-4 border-b border-border bg-muted/50 px-6 py-3">
                    <div className="flex flex-wrap items-center gap-3">
                        <DialogTitle className="text-lg font-bold">{t('videoModal.title')}</DialogTitle>
                        <StatusBadge status={statusInfo.status} label={t(statusInfo.labelKey)} />
                    </div>
                    <DialogDescription className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                            <Hash size={12} aria-hidden="true" />
                            {video.id.slice(0, 8)}...
                        </span>
                        <span className="inline-flex items-center gap-1">
                            <Calendar size={12} aria-hidden="true" />
                            {metadatos.fecha_subida
                                ? new Date(metadatos.fecha_subida).toLocaleDateString()
                                : t('videoDetails.notAvailable')}
                        </span>
                    </DialogDescription>
                </DialogHeader>

                <div className="flex flex-1 overflow-hidden">
                    <div className="flex w-3/5 flex-col border-r border-border bg-muted/30">
                        <div className="flex flex-1 items-center justify-center p-4">
                            <div className="aspect-video w-full overflow-hidden rounded-xl bg-black shadow-sm">
                                {loading ? (
                                    <div className="flex h-full w-full items-center justify-center">
                                        <Spinner size="xl" className="text-primary" label={t('common.loading')} />
                                    </div>
                                ) : !videoUrl ? (
                                    <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-muted-foreground">
                                        <AlertCircle size={48} aria-hidden="true" />
                                        <p className="text-sm">{t('videoModal.videoUnavailable')}</p>
                                    </div>
                                ) : videoError ? (
                                    <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-muted-foreground">
                                        <AlertCircle size={48} className="text-error" aria-hidden="true" />
                                        <p className="text-sm">{t('videoModal.videoError')}</p>
                                        <Button variant="outline" size="sm" onClick={() => setVideoError(false)}>
                                            <RotateCcw aria-hidden="true" />
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
                                        {metadatos.duracion_segundos || video.duracion_segundos || 0}s
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
                        <Tabs
                            value={activeTab}
                            onValueChange={(value) => setActiveTab(value as DetailTab)}
                            className="flex h-full flex-col"
                        >
                            <TabsList className="w-full justify-start rounded-none border-b border-border bg-card p-0">
                                <TabsTrigger value="resumen" className="flex-1 rounded-none py-2.5">
                                    <Info aria-hidden="true" /> {t('videoModal.tabSummary')}
                                </TabsTrigger>
                                <TabsTrigger value="gemini" className="flex-1 rounded-none py-2.5">
                                    <Sparkles aria-hidden="true" /> {t('videoModal.tabVisual')}
                                </TabsTrigger>
                                <TabsTrigger value="audio" className="flex-1 rounded-none py-2.5">
                                    <Mic aria-hidden="true" /> {t('videoModal.tabAudio')}
                                </TabsTrigger>
                            </TabsList>

                            <div className="flex-1 overflow-y-auto p-4">
                                <TabsContent value="resumen" className="mt-0 space-y-3">
                                    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <div className="mb-1 text-xs text-muted-foreground">
                                                    {t('videoModal.resultTitle')}
                                                </div>
                                                <StatusBadge status={statusInfo.status} label={t(statusInfo.labelKey)} />
                                            </div>
                                            <div className="text-right">
                                                <div className="text-3xl font-bold text-foreground">{confidencePercent}%</div>
                                                <div className="text-xs text-muted-foreground">{t('videoModal.confidence')}</div>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                        <div className="mb-2 flex items-center gap-1 text-xs text-muted-foreground">
                                            <FileText size={12} aria-hidden="true" /> {t('videoModal.titleLabel')}
                                        </div>
                                        <p className="text-sm font-medium text-foreground">
                                            {metadatos.titulo || video.descripcion || t('videoModal.noTitle')}
                                        </p>
                                    </div>

                                    {(metadatos.razon_rechazo || video.razon_rechazo) && (
                                        <div className="rounded-xl border border-error-border bg-error-surface p-4">
                                            <div className="mb-2 flex items-center gap-1 text-xs font-bold text-error">
                                                <AlertOctagon size={12} aria-hidden="true" /> {t('videoModal.rejectionReason')}
                                            </div>
                                            <p className="text-sm text-foreground">
                                                {metadatos.razon_rechazo || video.razon_rechazo}
                                            </p>
                                        </div>
                                    )}

                                    {metadatos.razon_decision && (
                                        <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                            <div className="mb-2 flex items-center gap-1 text-xs text-muted-foreground">
                                                <MessageSquare size={12} aria-hidden="true" /> {t('videoModal.decisionReason')}
                                            </div>
                                            <p className="text-sm text-muted-foreground">{metadatos.razon_decision}</p>
                                        </div>
                                    )}

                                    <div className="grid grid-cols-2 gap-2">
                                        <div className="rounded-lg border border-border bg-card p-3 shadow-sm">
                                            <div className="text-xs text-muted-foreground">{t('videoModal.statusLabel')}</div>
                                            <div className="font-medium text-foreground">{video.estado}</div>
                                        </div>
                                        <div className="rounded-lg border border-border bg-card p-3 shadow-sm">
                                            <div className="text-xs text-muted-foreground">{t('videoModal.durationLabel')}</div>
                                            <div className="font-medium text-foreground">
                                                {metadatos.duracion_segundos || video.duracion_segundos || 0}s
                                            </div>
                                        </div>
                                    </div>
                                </TabsContent>

                                <TabsContent value="gemini" className="mt-0 space-y-3">
                                    {Object.keys(geminiVision).length === 0 ? (
                                        <div className="flex flex-col items-center gap-2 py-8 text-center text-muted-foreground">
                                            <Sparkles size={32} className="opacity-50" aria-hidden="true" />
                                            <p className="text-sm">{t('videoModal.visualEmpty')}</p>
                                        </div>
                                    ) : (
                                        <>
                                            <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                                <div className="mb-3 flex items-center justify-between">
                                                    <StatusBadge
                                                        status={geminiVision.recomendacion === 'aprobar' ? 'approved' : 'rejected'}
                                                        label={geminiVision.recomendacion?.toUpperCase() || t('videoDetails.notAvailable')}
                                                    />
                                                    <div className="text-right">
                                                        <div className="text-2xl font-bold text-foreground">{geminiConfidence}%</div>
                                                        <div className="text-xs text-muted-foreground">{t('videoModal.confidence')}</div>
                                                    </div>
                                                </div>
                                                <div className="flex gap-3 text-sm">
                                                    <div className="flex-1 rounded-lg bg-muted/50 p-2 text-center">
                                                        <div className="text-xs text-muted-foreground">{t('videoModal.security')}</div>
                                                        <div className={`font-bold ${(geminiVision.puntuacion_seguridad || 0) > 50 ? 'text-success' : 'text-error'}`}>
                                                            {geminiVision.puntuacion_seguridad || 0}%
                                                        </div>
                                                    </div>
                                                    <div className="flex-1 rounded-lg bg-muted/50 p-2 text-center">
                                                        <div className="text-xs text-muted-foreground">{t('videoModal.visualQuality')}</div>
                                                        <div className="font-bold capitalize text-foreground">
                                                            {geminiVision.calidad_visual || t('videoDetails.notAvailable')}
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                                <div className="mb-2 text-xs text-muted-foreground">
                                                    {t('videoModal.contentDescription')}
                                                </div>
                                                <p className="text-sm text-muted-foreground">
                                                    {geminiVision.descripcion_contenido || t('videoDetails.notAvailable')}
                                                </p>
                                            </div>

                                            <div className="grid grid-cols-2 gap-3">
                                                <div className="rounded-xl border border-border bg-card p-3 shadow-sm">
                                                    <div className="mb-1 text-xs text-muted-foreground">
                                                        {t('videoModal.contentType')}
                                                    </div>
                                                    <div className="font-medium capitalize text-foreground">
                                                        {geminiVision.tipo_contenido || t('videoDetails.notAvailable')}
                                                    </div>
                                                </div>
                                                <div className="rounded-xl border border-border bg-card p-3 shadow-sm">
                                                    <div className="mb-1 text-xs text-muted-foreground">
                                                        {t('videoModal.scenario')}
                                                    </div>
                                                    <div className="text-sm font-medium text-foreground">
                                                        {geminiVision.escenario_principal || t('videoDetails.notAvailable')}
                                                    </div>
                                                </div>
                                            </div>

                                            {geminiVision.tags_sugeridos && geminiVision.tags_sugeridos.length > 0 && (
                                                <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                                    <div className="mb-2 text-xs text-muted-foreground">
                                                        {t('videoModal.suggestedTags')}
                                                    </div>
                                                    <div className="flex flex-wrap gap-2">
                                                        {geminiVision.tags_sugeridos.map((tag) => (
                                                            <span
                                                                key={tag}
                                                                className="rounded-full border border-brand-border bg-brand-soft px-2 py-1 text-xs font-medium text-brand-hover"
                                                            >
                                                                {tag}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {geminiVision.elementos_detectados && geminiVision.elementos_detectados.length > 0 && (
                                                <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                                    <div className="mb-2 text-xs text-muted-foreground">
                                                        {t('videoModal.detectedElements')}
                                                    </div>
                                                    <div className="flex flex-wrap gap-2">
                                                        {geminiVision.elementos_detectados.map((elem) => (
                                                            <span
                                                                key={elem}
                                                                className="rounded-full border border-info-border bg-info-surface px-2 py-1 text-xs font-medium text-info"
                                                            >
                                                                {elem}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </>
                                    )}
                                </TabsContent>

                                <TabsContent value="audio" className="mt-0 space-y-3">
                                    {!speechAnalysis.success ? (
                                        <div className="flex flex-col items-center gap-2 py-8 text-center text-muted-foreground">
                                            <VolumeX size={32} className="opacity-50" aria-hidden="true" />
                                            <p className="text-sm">{t('videoModal.audioEmpty')}</p>
                                        </div>
                                    ) : (
                                        <>
                                            <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                                <div className="grid grid-cols-3 gap-3 text-center">
                                                    <div className={`rounded-lg p-3 ${speechAnalysis.tiene_audio ? 'bg-success-surface' : 'bg-muted'}`}>
                                                        <Volume2
                                                            size={20}
                                                            className={`mx-auto mb-1 ${speechAnalysis.tiene_audio ? 'text-success' : 'text-muted-foreground'}`}
                                                            aria-hidden="true"
                                                        />
                                                        <div className={`text-xs font-medium ${speechAnalysis.tiene_audio ? 'text-success' : 'text-muted-foreground'}`}>
                                                            {speechAnalysis.tiene_audio ? t('videoModal.withAudio') : t('videoModal.withoutAudio')}
                                                        </div>
                                                    </div>
                                                    <div className={`rounded-lg p-3 ${speechAnalysis.tiene_voz ? 'bg-info-surface' : 'bg-muted'}`}>
                                                        <Mic
                                                            size={20}
                                                            className={`mx-auto mb-1 ${speechAnalysis.tiene_voz ? 'text-info' : 'text-muted-foreground'}`}
                                                            aria-hidden="true"
                                                        />
                                                        <div className={`text-xs font-medium ${speechAnalysis.tiene_voz ? 'text-info' : 'text-muted-foreground'}`}>
                                                            {speechAnalysis.tiene_voz ? t('videoModal.withVoiceBadge') : t('videoModal.withoutVoiceBadge')}
                                                        </div>
                                                    </div>
                                                    <div className="rounded-lg bg-muted p-3">
                                                        <Timer size={20} className="mx-auto mb-1 text-muted-foreground" aria-hidden="true" />
                                                        <div className="text-xs font-medium text-foreground">
                                                            {speechAnalysis.duracion_audio || 0}s
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>

                                            {speechAnalysis.transcripcion && (
                                                <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                                    <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
                                                        <span>{t('videoModal.transcription')}</span>
                                                        <span className="text-success">
                                                            {t('videoModal.confidenceShort', {
                                                                percent: Math.round((speechAnalysis.confianza_transcripcion || 0) * 100),
                                                            })}
                                                        </span>
                                                    </div>
                                                    <p className="rounded-lg bg-muted p-3 text-sm italic text-foreground">
                                                        &ldquo;{speechAnalysis.transcripcion}&rdquo;
                                                    </p>
                                                </div>
                                            )}

                                            {speechAnalysis.idiomas_detectados && speechAnalysis.idiomas_detectados.length > 0 && (
                                                <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                                    <div className="mb-2 text-xs text-muted-foreground">
                                                        {t('videoModal.detectedLanguages')}
                                                    </div>
                                                    <div className="flex flex-wrap gap-2">
                                                        {speechAnalysis.idiomas_detectados.map((idioma) => (
                                                            <span
                                                                key={idioma}
                                                                className="rounded-full border border-info-border bg-info-surface px-2 py-1 text-xs font-medium text-info"
                                                            >
                                                                {idioma}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {speechAnalysis.sentimiento && (
                                                <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                                                    <div className="mb-2 text-xs text-muted-foreground">
                                                        {t('videoModal.sentiment')}
                                                    </div>
                                                    <StatusBadge
                                                        status={speechAnalysis.sentimiento.interpretacion === 'negativo' ? 'rejected' : 'approved'}
                                                        label={speechAnalysis.sentimiento.interpretacion || t('videoModal.neutral')}
                                                    />
                                                </div>
                                            )}
                                        </>
                                    )}
                                </TabsContent>
                            </div>
                        </Tabs>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
