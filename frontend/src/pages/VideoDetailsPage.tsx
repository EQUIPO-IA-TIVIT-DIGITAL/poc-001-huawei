import { useEffect, useState, useRef } from 'react';
import { useParams, Link } from '@tanstack/react-router';
import { apiRequest } from '../lib/api';
import {
  Video as VideoIcon,
  Type,
  Tag,
  ChevronLeft,
  Play,
  Clock,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { StatusBadge, type AppStatus } from '../components/ui/status-badge';
import { LoadingState } from '../components/ui/loading-state';
import { ErrorState } from '../components/ui/error-state';
import { EmptyState } from '../components/ui/empty-state';
import { useTranslation } from '../i18n';

interface Shot {
  start_time: number;
  end_time: number;
  start_formatted: string;
  end_formatted: string;
  shot_number: number;
}

interface LabelItem {
  entity?: { description?: string };
  description?: string;
  confidence?: number;
}

interface VideoDetails {
  id: string;
  titulo: string;
  descripcion: string;
  estado: string;
  video_url?: string;
  fecha_carga?: string;
  fecha_procesamiento?: string;
  resultado_ia?: string;
  confianza?: number;
  razon?: string;
  analisis?: string;
  shots: Shot[];
  texto_detectado: string[];
  labels: unknown[];
}

const statusFromRaw = (raw?: string): AppStatus => {
  const status = (raw || '').toUpperCase();
  if (status.includes('APROBADO')) return 'approved';
  if (status.includes('RECHAZADO')) return 'rejected';
  if (status.includes('PROCES')) return 'processing';
  return 'pending';
};

export default function VideoDetailsPage() {
  const { videoId } = useParams({ from: '/app/video/$videoId' });
  const { t, formatDate } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [details, setDetails] = useState<VideoDetails | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'summary' | 'shots' | 'text' | 'labels'>(
    'summary',
  );
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoId) {
      fetchDetails(videoId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  const fetchDetails = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiRequest<{ success: boolean; video: VideoDetails }>(
        `/socio/video/${id}/details`,
      );
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

  const jumpToTime = (time: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      void videoRef.current.play();
    }
  };

  const rawStatus = details?.resultado_ia || details?.estado || '';

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <LoadingState label={t('common.loading')} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <ErrorState
          title={t('videoDetails.loadError')}
          description={error}
          onRetry={() => videoId && fetchDetails(videoId)}
        />
        <div className="mt-4">
          <Button variant="outline" asChild>
            <Link to="/mis-videos">{t('videoDetails.back')}</Link>
          </Button>
        </div>
      </div>
    );
  }

  if (!details) return null;

  const labelName = (label: unknown): string => {
    if (typeof label === 'string') return label;
    if (label && typeof label === 'object') {
      const item = label as LabelItem;
      return item.entity?.description || item.description || t('videoDetails.objectFallback');
    }
    return t('videoDetails.objectFallback');
  };

  const labelConfidence = (label: unknown): string => {
    if (label && typeof label === 'object' && typeof (label as LabelItem).confidence === 'number') {
      return t('videoDetails.labelConfidence', {
        percent: Math.round(((label as LabelItem).confidence ?? 0) * 100),
      });
    }
    return '';
  };

  return (
    <div className="flex h-[calc(100vh-64px)] flex-col overflow-hidden bg-background text-foreground">
      {/* Sticky Header */}
      <div className="z-10 flex shrink-0 items-center gap-4 border-b border-border bg-card px-6 py-4">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/mis-videos" aria-label={t('videoDetails.back')}>
            <ChevronLeft aria-hidden="true" />
          </Link>
        </Button>
        <div className="min-w-0">
          <h1 className="flex flex-wrap items-center gap-3 text-xl font-semibold tracking-tight">
            <span className="truncate">{details.titulo || t('videoDetails.fallbackTitle')}</span>
            <StatusBadge
              status={statusFromRaw(rawStatus)}
              label={
                statusFromRaw(rawStatus) === 'approved'
                  ? t('videoDetails.statusApproved')
                  : statusFromRaw(rawStatus) === 'rejected'
                    ? t('videoDetails.statusRejected')
                    : rawStatus
              }
            />
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            {t('videoDetails.idLabel', { id: videoId })}
          </p>
        </div>
      </div>

      <div className="flex flex-1 flex-col overflow-hidden md:flex-row">
        {/* LEFT: Player */}
        <div className="group relative flex w-full flex-col items-center justify-center bg-black md:w-3/5">
          {details.video_url ? (
            <video
              ref={videoRef}
              src={details.video_url}
              className="max-h-full w-full object-contain"
              controls
              playsInline
            />
          ) : (
            <div className="flex flex-col items-center gap-3 px-6 text-center text-gray-300">
              <VideoIcon aria-hidden="true" size={48} />
              <p className="font-medium text-white">
                {details.estado?.toLowerCase() === 'procesando'
                  ? t('videoDetails.processing')
                  : t('videoDetails.unavailable')}
              </p>
              <p className="text-sm text-gray-400">{t('videoDetails.unavailableHint')}</p>
            </div>
          )}
        </div>

        {/* RIGHT: Data Panels */}
        <div className="flex w-full flex-col border-l border-border bg-muted/40 md:w-2/5">
          <Tabs
            value={activeTab}
            onValueChange={(value) => setActiveTab(value as typeof activeTab)}
            className="flex min-h-0 flex-1 flex-col"
          >
            <TabsList className="h-auto w-full shrink-0 justify-between rounded-none border-b border-border bg-card p-0">
              <TabsTrigger value="summary" className="flex-1 rounded-none py-3">
                {t('videoDetails.tabSummary')}
              </TabsTrigger>
              <TabsTrigger value="shots" className="flex-1 rounded-none py-3">
                {t('videoDetails.tabShots')}
              </TabsTrigger>
              <TabsTrigger value="text" className="flex-1 rounded-none py-3">
                {t('videoDetails.tabText')}
              </TabsTrigger>
              <TabsTrigger value="labels" className="flex-1 rounded-none py-3">
                {t('videoDetails.tabLabels')}
              </TabsTrigger>
            </TabsList>

            <div className="flex-1 overflow-y-auto p-4">
              <TabsContent value="summary" className="mt-0 space-y-6">
                <Card className="p-4">
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {t('videoDetails.decisionTitle')}
                  </h4>
                  <p className="font-medium leading-relaxed text-foreground">
                    {details.razon || t('videoDetails.noReason')}
                  </p>
                </Card>

                <div className="grid grid-cols-2 gap-4">
                  <Card className="p-3">
                    <p className="mb-1 text-xs text-muted-foreground">
                      {t('videoDetails.confidence')}
                    </p>
                    <span className="text-2xl font-bold text-primary">
                      {Math.round((details.confianza || 0) * 100)}%
                    </span>
                  </Card>
                  <Card className="p-3">
                    <p className="mb-1 text-xs text-muted-foreground">
                      {t('videoDetails.processedDate')}
                    </p>
                    <p className="text-sm font-bold text-foreground">
                      {details.fecha_procesamiento
                        ? formatDate(details.fecha_procesamiento)
                        : t('videoDetails.notAvailable')}
                    </p>
                  </Card>
                </div>

                {details.analisis && (
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {t('videoDetails.technicalAnalysis')}
                    </h4>
                    <Card className="whitespace-pre-wrap p-4 font-mono text-xs leading-relaxed text-muted-foreground">
                      {details.analisis}
                    </Card>
                  </div>
                )}
              </TabsContent>

              <TabsContent value="shots" className="mt-0 space-y-2">
                <p className="mb-4 px-1 text-xs text-muted-foreground">
                  {t('videoDetails.shotsCount', { count: details.shots?.length || 0 })}
                </p>
                {details.shots?.map((shot, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => jumpToTime(shot.start_time)}
                    className="group flex w-full items-center justify-between rounded-lg border border-border bg-card p-3 transition-colors hover:border-brand-border hover:bg-brand-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-xs font-bold text-muted-foreground transition-colors group-hover:bg-brand-soft group-hover:text-primary">
                        {idx + 1}
                      </div>
                      <div className="flex flex-col items-start">
                        <span className="text-sm font-bold text-foreground group-hover:text-primary">
                          {t('videoDetails.scene', { number: idx + 1 })}
                        </span>
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Clock size={11} aria-hidden="true" />
                          {t('videoDetails.sceneDuration', {
                            seconds: (shot.end_time - shot.start_time).toFixed(1),
                          })}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-muted px-2 py-1 font-mono text-xs font-medium text-muted-foreground">
                        {shot.start_formatted} - {shot.end_formatted}
                      </span>
                      <Play size={14} className="text-primary" aria-hidden="true" />
                    </div>
                  </button>
                ))}
                {(!details.shots || details.shots.length === 0) && (
                  <EmptyState
                    icon={<VideoIcon aria-hidden="true" />}
                    title={t('videoDetails.noShots')}
                  />
                )}
              </TabsContent>

              <TabsContent value="text" className="mt-0 space-y-3">
                <p className="mb-2 px-1 text-xs text-muted-foreground">
                  {t('videoDetails.ocrDescription')}
                </p>
                {details.texto_detectado?.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {details.texto_detectado.map((txt, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-foreground"
                      >
                        <Type size={12} className="text-muted-foreground" aria-hidden="true" />
                        {txt}
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={<Type aria-hidden="true" />}
                    title={t('videoDetails.noText')}
                  />
                )}
              </TabsContent>

              <TabsContent value="labels" className="mt-0 space-y-3">
                <p className="mb-2 px-1 text-xs text-muted-foreground">
                  {t('videoDetails.labelsDescription')}
                </p>
                {details.labels?.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {details.labels.map((label, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-2 rounded-lg border border-info-border bg-info-surface px-3 py-1.5 text-sm text-info"
                      >
                        <Tag size={12} className="text-info" aria-hidden="true" />
                        {labelName(label)}
                        <span className="text-[10px] opacity-70">{labelConfidence(label)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={<Tag aria-hidden="true" />}
                    title={t('videoDetails.noLabels')}
                  />
                )}
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
