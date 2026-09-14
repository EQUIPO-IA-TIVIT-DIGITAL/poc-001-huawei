import { useEffect, useState } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { toast } from 'sonner';
import {
  obtenerVideo,
  obtenerEventosVideo,
  SecurityVideo,
  EventoSeguridad,
  EstadoSecurityVideo,
} from '../services/securityVideoService';
import {
  ArrowLeft,
  Video,
  FileText,
  FileDown,
  BarChart3,
  AlertTriangle,
  Zap,
  CheckCircle2,
  ClipboardList,
  User,
  Car,
  Search,
  Film,
  CalendarDays,
  Timer,
} from 'lucide-react';
import { PageContainer } from '../components/ui/page-container';
import { PageHeader } from '../components/ui/page-header';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { LoadingState } from '../components/ui/loading-state';
import { ErrorState } from '../components/ui/error-state';
import { EmptyState } from '../components/ui/empty-state';
import { StatusBadge, type AppStatus } from '../components/ui/status-badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { useTranslation } from '../i18n';

const ESTADO_META: Record<string, { labelKey: string; status: AppStatus }> = {
  [EstadoSecurityVideo.UPLOADING]: { labelKey: 'securityDetail.statusUploading', status: 'uploading' },
  [EstadoSecurityVideo.UPLOADED]: { labelKey: 'securityDetail.statusUploaded', status: 'pending' },
  [EstadoSecurityVideo.PROCESSING]: { labelKey: 'securityDetail.statusProcessing', status: 'processing' },
  [EstadoSecurityVideo.ANALYZING]: { labelKey: 'securityDetail.statusAnalyzing', status: 'processing' },
  [EstadoSecurityVideo.COMPLETED]: { labelKey: 'securityDetail.statusCompleted', status: 'completed' },
  [EstadoSecurityVideo.ERROR]: { labelKey: 'securityDetail.statusError', status: 'failed' },
  [EstadoSecurityVideo.DETECTING_MOTION]: { labelKey: 'securityDetail.statusMotion', status: 'processing' },
  [EstadoSecurityVideo.MOTION_DETECTED]: { labelKey: 'securityDetail.statusMotionDetected', status: 'processing' },
  [EstadoSecurityVideo.CLASSIFYING]: { labelKey: 'securityDetail.statusClassifying', status: 'processing' },
  [EstadoSecurityVideo.CLASSIFIED]: { labelKey: 'securityDetail.statusClassified', status: 'processing' },
  [EstadoSecurityVideo.DEEP_ANALYZING]: { labelKey: 'securityDetail.statusDeepAnalyzing', status: 'processing' },
  [EstadoSecurityVideo.GENERATING_REPORT]: { labelKey: 'securityDetail.statusGeneratingReport', status: 'processing' },
};

const RIESGO_META: Record<
  string,
  { labelKey: string; variant: 'success' | 'warning' | 'destructive'; Icon: typeof AlertTriangle }
> = {
  BAJO: { labelKey: 'securityDetail.riskLowLabel', variant: 'success', Icon: CheckCircle2 },
  MEDIO: { labelKey: 'securityDetail.riskMediumLabel', variant: 'warning', Icon: Zap },
  ALTO: { labelKey: 'securityDetail.riskHighLabel', variant: 'warning', Icon: AlertTriangle },
  CRITICO: { labelKey: 'securityDetail.riskCriticalLabel', variant: 'destructive', Icon: AlertTriangle },
};

type TranslationKey = Parameters<ReturnType<typeof useTranslation>['t']>[0];

export default function SecurityVideoDetail() {
  const params = useParams({ strict: false });
  const videoId = params.videoId as string;
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [video, setVideo] = useState<SecurityVideo | null>(null);
  const [eventos, setEventos] = useState<EventoSeguridad[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [filtroClasificacion, setFiltroClasificacion] = useState<string>('TODOS');

  useEffect(() => {
    cargarDatos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  const cargarDatos = async () => {
    try {
      setLoading(true);
      setError(false);
      const [videoData, eventosData] = await Promise.all([
        obtenerVideo(videoId),
        obtenerEventosVideo(videoId),
      ]);
      setVideo(videoData);
      setEventos(eventosData);
    } catch {
      setError(true);
      toast.error(t('securityDetail.loadError'));
    } finally {
      setLoading(false);
    }
  };

  const getNivelRiesgo = (evento: EventoSeguridad): string => {
    return evento.nivel_riesgo || evento.analisis_detallado?.gemini_video?.nivel_riesgo || 'BAJO';
  };

  const eventosFiltrados =
    filtroClasificacion === 'TODOS'
      ? eventos
      : eventos.filter((e) => getNivelRiesgo(e) === filtroClasificacion);

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hours > 0) return `${hours}h ${minutes}min`;
    if (minutes > 0) return `${minutes}min ${secs}s`;
    return `${secs}s`;
  };

  const formatTimestamp = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${hours.toString().padStart(2, '0')}:${minutes
      .toString()
      .padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const getVideoLabel = (videoData: SecurityVideo) => {
    return videoData.metadata_tecnico?.filename_original || `Video ${videoData.id}`;
  };

  const riesgoBadge = (nivel: string) => {
    const meta = RIESGO_META[nivel] || RIESGO_META.BAJO;
    const { Icon } = meta;
    return (
      <Badge variant={meta.variant} className="gap-1">
        <Icon aria-hidden="true" />
        {t(meta.labelKey as TranslationKey)}
      </Badge>
    );
  };

  if (loading) {
    return <LoadingState label={t('securityDetail.loading')} className="min-h-[60vh]" />;
  }

  if (error && !video) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <ErrorState
          title={t('securityDetail.loadError')}
          description={t('common.errorGeneric')}
          onRetry={cargarDatos}
        />
        <div className="mt-4">
          <Button variant="outline" onClick={() => navigate({ to: '/security' })}>
            {t('securityDetail.back')}
          </Button>
        </div>
      </div>
    );
  }

  if (!video) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <EmptyState
          icon={<Video aria-hidden="true" />}
          title={t('securityDetail.notFound')}
          action={
            <Button onClick={() => navigate({ to: '/security' })}>
              {t('securityDetail.back')}
            </Button>
          }
        />
      </div>
    );
  }

  const stats = video.estadisticas || {};
  const eventosPorRiesgo = stats.eventos_por_riesgo || {};
  const riesgoCounts = {
    critico:
      eventosPorRiesgo['CRITICO'] || eventos.filter((e) => getNivelRiesgo(e) === 'CRITICO').length,
    alto: eventosPorRiesgo['ALTO'] || eventos.filter((e) => getNivelRiesgo(e) === 'ALTO').length,
    medio: eventosPorRiesgo['MEDIO'] || eventos.filter((e) => getNivelRiesgo(e) === 'MEDIO').length,
    bajo: eventosPorRiesgo['BAJO'] || eventos.filter((e) => getNivelRiesgo(e) === 'BAJO').length,
  };

  const estadoMeta = ESTADO_META[video.estado];

  return (
    <PageContainer className="pb-16">
      <Button
        variant="ghost"
        onClick={() => navigate({ to: '/security' })}
        className="w-fit px-0 hover:bg-transparent"
      >
        <ArrowLeft aria-hidden="true" />
        {t('securityDetail.back')}
      </Button>

      <PageHeader icon={Video} title={t('securityDetail.title')} />

      {/* Información general del video */}
      <Card variant="elevated">
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div>
            <CardTitle className="text-2xl">{getVideoLabel(video)}</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">{t('securityDetail.subtitle')}</p>
          </div>
          {estadoMeta && (
            <StatusBadge
              status={estadoMeta.status}
              label={t(estadoMeta.labelKey as TranslationKey)}
            />
          )}
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-lg border border-border bg-muted/50 p-4">
              <p className="text-sm text-muted-foreground">{t('securityDetail.file')}</p>
              <p className="text-lg font-semibold text-foreground">{getVideoLabel(video)}</p>
            </div>
            <div className="rounded-lg border border-border bg-muted/50 p-4">
              <p className="text-sm text-muted-foreground">{t('securityDetail.duration')}</p>
              <p className="text-lg font-semibold text-foreground">
                {formatDuration(video.duracion_segundos)}
              </p>
            </div>
            {video.tiempo_procesamiento_segundos && (
              <div className="rounded-lg border border-border bg-muted/50 p-4">
                <p className="text-sm text-muted-foreground">
                  {t('securityDetail.processingTime')}
                </p>
                <p className="text-lg font-semibold text-foreground">
                  {formatDuration(video.tiempo_procesamiento_segundos)}
                </p>
              </div>
            )}
          </div>

          {video.fecha_creacion && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <CalendarDays size={13} aria-hidden="true" />
                {video.fecha_creacion}
              </span>
              {video.tiempo_procesamiento_segundos && (
                <span className="flex items-center gap-1.5">
                  <Timer size={13} aria-hidden="true" />
                  {formatDuration(video.tiempo_procesamiento_segundos)}
                </span>
              )}
            </div>
          )}

          {/* Reportes */}
          {(video.reporte_txt_url || video.reporte_pdf_url) && (
            <div className="border-t border-border pt-6">
              <h3 className="mb-3 flex items-center gap-2 text-lg font-semibold text-foreground">
                <FileText size={18} aria-hidden="true" />
                {t('securityDetail.reports')}
              </h3>
              <div className="flex flex-wrap gap-3">
                {video.reporte_txt_url && (
                  <Button asChild>
                    <a href={video.reporte_txt_url} target="_blank" rel="noopener noreferrer">
                      <FileDown aria-hidden="true" />
                      {t('securityDetail.downloadTxt')}
                    </a>
                  </Button>
                )}
                {video.reporte_pdf_url && (
                  <Button variant="danger" asChild>
                    <a href={video.reporte_pdf_url} target="_blank" rel="noopener noreferrer">
                      <FileText aria-hidden="true" />
                      {t('securityDetail.downloadPdf')}
                    </a>
                  </Button>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Estadísticas */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-4">
        <StatCard
          icon={<BarChart3 size={20} aria-hidden="true" />}
          label={t('securityDetail.totalEvents')}
          value={stats.total_eventos ?? eventos.length}
          tone="info"
        />
        <StatCard
          icon={<AlertTriangle size={20} aria-hidden="true" />}
          label={t('securityDetail.criticalHigh')}
          value={riesgoCounts.critico + riesgoCounts.alto}
          tone="error"
        />
        <StatCard
          icon={<Zap size={20} aria-hidden="true" />}
          label={t('securityDetail.mediumRisk')}
          value={riesgoCounts.medio}
          tone="warning"
        />
        <StatCard
          icon={<CheckCircle2 size={20} aria-hidden="true" />}
          label={t('securityDetail.lowRisk')}
          value={riesgoCounts.bajo}
          tone="success"
        />
      </div>

      {/* Resumen ejecutivo */}
      {stats.resumen_ejecutivo && (
        <Card variant="elevated">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ClipboardList size={18} aria-hidden="true" />
              {t('securityDetail.executiveSummary')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-foreground">{stats.resumen_ejecutivo}</p>
            {stats.nivel_riesgo_global && (
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-muted-foreground">
                  {t('securityDetail.globalRisk')}
                </span>
                {riesgoBadge(stats.nivel_riesgo_global)}
              </div>
            )}
            {stats.total_personas_detectadas > 0 && (
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <User size={14} aria-hidden="true" />
                  {t('securityDetail.detectedPeople', {
                    count: stats.total_personas_detectadas,
                  })}
                </span>
                <span className="flex items-center gap-1.5">
                  <Car size={14} aria-hidden="true" />
                  {t('securityDetail.detectedVehicles', {
                    count: stats.total_vehiculos_detectados || 0,
                  })}
                </span>
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Lista de eventos */}
      <Card variant="elevated">
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-4">
          <CardTitle className="text-xl">
            {t('securityDetail.timeline', { count: eventosFiltrados.length })}
          </CardTitle>
          <div className="w-full sm:w-64">
            <Select value={filtroClasificacion} onValueChange={setFiltroClasificacion}>
              <SelectTrigger aria-label={t('securityDetail.filterLabel')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="TODOS">{t('securityDetail.filterAll')}</SelectItem>
                <SelectItem value="CRITICO">{t('securityDetail.riskCritical')}</SelectItem>
                <SelectItem value="ALTO">{t('securityDetail.riskHigh')}</SelectItem>
                <SelectItem value="MEDIO">{t('securityDetail.riskMedium')}</SelectItem>
                <SelectItem value="BAJO">{t('securityDetail.riskLow')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {eventosFiltrados.length === 0 ? (
            <EmptyState
              icon={<Search aria-hidden="true" />}
              title={t('securityDetail.noEvents')}
              className="border-0"
            />
          ) : (
            <div className="space-y-4">
              {eventosFiltrados.map((evento) => (
                <div
                  key={evento.id}
                  className="rounded-xl border border-border bg-card p-4 transition-shadow hover:shadow-card"
                >
                  <div className="mb-3 flex items-start justify-between">
                    <div className="flex-1">
                      <div className="mb-2 flex flex-wrap items-center gap-3">
                        {riesgoBadge(getNivelRiesgo(evento))}
                        <span className="text-sm text-muted-foreground">
                          {formatTimestamp(evento.timestamp_inicio)} -{' '}
                          {formatTimestamp(evento.timestamp_fin)}
                        </span>
                        <span className="text-sm text-muted-foreground">
                          ({evento.duracion.toFixed(1)}s)
                        </span>
                      </div>
                      <p className="text-foreground">
                        {evento.descripcion || evento.descripcion_gemini}
                      </p>
                      {evento.confianza && (
                        <p className="mt-1 text-sm text-muted-foreground">
                          {t('securityDetail.confidence', {
                            percent: (evento.confianza * 100).toFixed(1),
                          })}
                        </p>
                      )}
                      {(evento.personas_count > 0 || evento.vehiculos_count > 0) && (
                        <div className="mt-1 flex gap-3 text-xs text-muted-foreground">
                          {evento.personas_count > 0 && (
                            <span className="flex items-center gap-1">
                              <User size={12} aria-hidden="true" />
                              {t('securityDetail.peopleCount', { count: evento.personas_count })}
                            </span>
                          )}
                          {evento.vehiculos_count > 0 && (
                            <span className="flex items-center gap-1">
                              <Car size={12} aria-hidden="true" />
                              {t('securityDetail.vehicleCount', { count: evento.vehiculos_count })}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {evento.analisis_detallado &&
                    Object.keys(evento.analisis_detallado).length > 0 && (
                      <div className="mt-3 border-t border-border pt-3">
                        <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-foreground">
                          <Search size={14} aria-hidden="true" />
                          {t('securityDetail.analysisDetailed')}
                        </p>
                        <div className="rounded bg-muted p-3">
                          <pre className="whitespace-pre-wrap font-mono text-xs text-muted-foreground">
                            {JSON.stringify(evento.analisis_detallado, null, 2)}
                          </pre>
                        </div>
                      </div>
                    )}
                  {!evento.analisis_detallado &&
                    evento.analisis_profundo &&
                    Object.keys(evento.analisis_profundo).length > 0 && (
                      <div className="mt-3 border-t border-border pt-3">
                        <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-foreground">
                          <Search size={14} aria-hidden="true" />
                          {t('securityDetail.analysisDeep')}
                        </p>
                        <div className="rounded bg-muted p-3">
                          <pre className="whitespace-pre-wrap font-mono text-xs text-muted-foreground">
                            {JSON.stringify(evento.analisis_profundo, null, 2)}
                          </pre>
                        </div>
                      </div>
                    )}

                  {evento.clip_url && (
                    <div className="mt-3">
                      <Button variant="link" size="sm" className="px-0" asChild>
                        <a href={evento.clip_url} target="_blank" rel="noopener noreferrer">
                          <Film aria-hidden="true" />
                          {t('securityDetail.viewClip')}
                        </a>
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}

function StatCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone: 'info' | 'error' | 'warning' | 'success';
}) {
  const toneClasses = {
    info: 'bg-info-surface text-info',
    error: 'bg-error-surface text-error',
    warning: 'bg-warning-surface text-warning',
    success: 'bg-success-surface text-success',
  } as const;

  return (
    <Card variant="elevated" className="flex items-center justify-between p-6">
      <div>
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="text-3xl font-bold text-foreground">{value}</p>
      </div>
      <span className={`rounded-lg p-2.5 ${toneClasses[tone]}`}>{icon}</span>
    </Card>
  );
}
