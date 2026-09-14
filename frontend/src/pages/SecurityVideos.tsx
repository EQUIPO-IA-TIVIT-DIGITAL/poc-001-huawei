import { useState, useEffect, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { securityVideoService, SecurityVideo } from '../services/securityVideoService';
import { getErrorMessage } from '../lib/errors';
import { toast } from 'sonner';
import {
  Video,
  Plus,
  Clock,
  AlertTriangle,
  FileText,
  Trash2,
  RefreshCw,
  RotateCcw,
  CalendarDays,
  Timer,
} from 'lucide-react';
import { PageContainer, PageSection } from '../components/ui/page-container';
import { PageHeader } from '../components/ui/page-header';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { EmptyState } from '../components/ui/empty-state';
import { LoadingState } from '../components/ui/loading-state';
import { StatusBadge, type AppStatus } from '../components/ui/status-badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useTranslation, type TranslationKey } from '../i18n';

const ALL_ESTADOS = 'all';

const ESTADO_OPTIONS: { value: string; labelKey: TranslationKey }[] = [
  { value: ALL_ESTADOS, labelKey: 'securityVideos.estadoAll' },
  { value: 'uploading', labelKey: 'securityVideos.estadoUploading' },
  { value: 'uploaded', labelKey: 'securityVideos.estadoUploaded' },
  { value: 'motion_detecting', labelKey: 'securityVideos.estadoMotionDetecting' },
  { value: 'classifying', labelKey: 'securityVideos.estadoClassifying' },
  { value: 'deep_analyzing', labelKey: 'securityVideos.estadoDeepAnalyzing' },
  { value: 'generating_report', labelKey: 'securityVideos.estadoGeneratingReport' },
  { value: 'completed', labelKey: 'securityVideos.estadoCompleted' },
  { value: 'error', labelKey: 'securityVideos.estadoError' },
];

const PROCESSING_ESTADOS = [
  'uploading',
  'uploaded',
  'motion_detecting',
  'motion_detected',
  'analyzing',
  'classifying',
  'deep_analyzing',
  'generating_report',
];

const statusFromEstado = (estado: string): AppStatus => {
  if (estado === 'completed') return 'completed';
  if (estado === 'error') return 'failed';
  if (estado === 'uploading') return 'uploading';
  return 'processing';
};

export default function SecurityVideos() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [videos, setVideos] = useState<SecurityVideo[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtroEstado, setFiltroEstado] = useState<string>(ALL_ESTADOS);
  const [deleteTarget, setDeleteTarget] = useState<SecurityVideo | null>(null);
  const [deleting, setDeleting] = useState(false);
  const prevStatusRef = useRef<Record<string, { estado: string; hasReport: boolean }>>({});
  const hasLoadedOnceRef = useRef(false);

  useEffect(() => {
    cargarVideos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroEstado]);

  // Auto-refresh cada 10 segundos si hay videos en procesamiento
  useEffect(() => {
    const hasProcessingVideos = videos.some((v) => PROCESSING_ESTADOS.includes(v.estado));

    if (hasProcessingVideos) {
      const interval = setInterval(() => {
        cargarVideos();
      }, 10000); // 10 segundos

      return () => clearInterval(interval);
    }
  }, [videos]);

  const cargarVideos = async () => {
    try {
      setLoading(true);
      const params: { limit: number; estado?: string } = { limit: 50 };
      if (filtroEstado && filtroEstado !== ALL_ESTADOS) {
        params.estado = filtroEstado;
      }

      const response = await securityVideoService.listarVideos(params);
      const nextVideos = response.videos;
      const prevMap = prevStatusRef.current;

      if (hasLoadedOnceRef.current) {
        nextVideos.forEach((video) => {
          const hasReport = Boolean(video.reporte_pdf_url || video.reporte_txt_url);
          const prev = prevMap[video.id];
          if (
            video.estado === 'completed' &&
            hasReport &&
            (!prev || prev.estado !== 'completed' || !prev.hasReport)
          ) {
            toast.success(t('securityVideos.reportReady', { name: getVideoLabel(video) }));
          }
        });
      }

      prevStatusRef.current = Object.fromEntries(
        nextVideos.map((video) => [
          video.id,
          { estado: video.estado, hasReport: Boolean(video.reporte_pdf_url || video.reporte_txt_url) },
        ]),
      );

      hasLoadedOnceRef.current = true;
      setVideos(nextVideos);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const handleReintentar = async (videoId: string) => {
    try {
      const res = await securityVideoService.reintentarAnalisis(videoId);
      if (res.success) {
        toast.success(res.message || t('securityVideos.retrySuccess'));
        cargarVideos();
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const handleEliminar = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await securityVideoService.eliminarVideo(deleteTarget.id);
      toast.success(t('securityVideos.deleted'));
      setDeleteTarget(null);
      cargarVideos();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setDeleting(false);
    }
  };

  const formatDate = (isoDate: string) => {
    if (!isoDate) return 'N/A';
    const date = new Date(isoDate);
    return date.toLocaleString('es-ES', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getVideoLabel = (video: SecurityVideo) => {
    return video.metadata_tecnico?.filename_original || `Video ${video.id}`;
  };

  const readyCount = videos.filter(
    (video) => video.estado === 'completed' && (video.reporte_pdf_url || video.reporte_txt_url),
  ).length;

  return (
    <PageContainer className="pb-16">
      <PageHeader
        icon={Video}
        title={t('securityVideos.title')}
        description={t('securityVideos.description')}
        actions={
          <>
            {readyCount > 0 && (
              <Badge variant="success">{t('securityVideos.readyReports', { count: readyCount })}</Badge>
            )}
            <Button onClick={() => navigate({ to: '/security/upload' })}>
              <Plus aria-hidden="true" />
              {t('securityVideos.upload')}
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="w-full sm:w-72">
          <Select value={filtroEstado} onValueChange={setFiltroEstado}>
            <SelectTrigger aria-label={t('securityVideos.filterLabel')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ESTADO_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {t(option.labelKey)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" onClick={cargarVideos}>
          <RefreshCw aria-hidden="true" />
          {t('common.refresh')}
        </Button>
      </div>

      {loading && videos.length === 0 ? (
        <LoadingState label={t('common.loading')} />
      ) : videos.length === 0 ? (
        <EmptyState
          icon={<Video aria-hidden="true" />}
          title={t('securityVideos.emptyTitle')}
          description={t('securityVideos.emptyDescription')}
          action={
            <Button onClick={() => navigate({ to: '/security/upload' })}>
              <Plus aria-hidden="true" />
              {t('securityVideos.upload')}
            </Button>
          }
        />
      ) : (
        <PageSection>
          <div className="grid gap-5">
            {videos.map((video) => {
              const riesgo = video.estadisticas?.eventos_por_riesgo;
              const hasRiskAlert = Boolean(
                riesgo && (riesgo.CRITICO > 0 || riesgo.ALTO > 0),
              );
              const isAnalysisInProgress = [
                'motion_detecting',
                'motion_detected',
                'analyzing',
                'classifying',
                'deep_analyzing',
                'generating_report',
              ].includes(video.estado);

              return (
                <Card key={video.id} variant="elevated">
                  <CardContent className="p-6">
                    <div className="mb-4 flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <h3 className="mb-2 truncate text-lg font-semibold text-foreground">
                          {getVideoLabel(video)}
                        </h3>
                        {video.duracion_segundos > 0 && (
                          <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                            <span className="flex items-center gap-1.5">
                              <Clock size={15} aria-hidden="true" />
                              {securityVideoService.formatDuration(video.duracion_segundos)}
                            </span>
                          </div>
                        )}
                      </div>
                      <StatusBadge status={statusFromEstado(video.estado)} />
                    </div>

                    {video.estadisticas && Object.keys(video.estadisticas).length > 0 && (
                      <div className="mb-4 grid grid-cols-2 gap-3 rounded-lg border border-border bg-muted/50 p-4 sm:grid-cols-4">
                        <div>
                          <p className="text-xs text-muted-foreground">
                            {t('securityVideos.totalEvents')}
                          </p>
                          <p className="text-lg font-semibold text-foreground">
                            {video.eventos_count || video.estadisticas.total_eventos || 0}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">
                            {t('securityVideos.critical')}
                          </p>
                          <p className="text-lg font-semibold text-error">
                            {video.estadisticas.eventos_por_riesgo?.CRITICO || 0}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">
                            {t('securityVideos.highRisk')}
                          </p>
                          <p className="text-lg font-semibold text-warning">
                            {video.estadisticas.eventos_por_riesgo?.ALTO || 0}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">
                            {t('securityVideos.mediumLow')}
                          </p>
                          <p className="text-lg font-semibold text-foreground">
                            {(video.estadisticas.eventos_por_riesgo?.MEDIO || 0) +
                              (video.estadisticas.eventos_por_riesgo?.BAJO || 0)}
                          </p>
                        </div>
                      </div>
                    )}

                    {hasRiskAlert && (
                      <Alert variant="warning" className="mb-4">
                        <AlertTriangle aria-hidden="true" />
                        <AlertDescription>{t('securityVideos.riskAlert')}</AlertDescription>
                      </Alert>
                    )}

                    <div className="flex flex-wrap gap-3">
                      {video.estado === 'uploading' && (
                        <Alert variant="info" className="flex-1">
                          <AlertTitle>{t('securityVideos.uploadingTitle')}</AlertTitle>
                          <AlertDescription>{t('securityVideos.uploadingDesc')}</AlertDescription>
                        </Alert>
                      )}

                      {video.estado === 'completed' && (
                        <>
                          <Button onClick={() => navigate({ to: `/security/${video.id}` })}>
                            <FileText aria-hidden="true" />
                            {t('securityVideos.viewReport')}
                          </Button>
                          {video.reporte_pdf_url && (
                            <Button variant="outline" asChild>
                              <a
                                href={video.reporte_pdf_url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                <FileText aria-hidden="true" />
                                {t('securityVideos.downloadPdf')}
                              </a>
                            </Button>
                          )}
                        </>
                      )}

                      {video.estado === 'uploaded' && (
                        <Alert variant="info">
                          <AlertTitle>{t('securityVideos.queuedTitle')}</AlertTitle>
                          <AlertDescription>{t('securityVideos.queuedDesc')}</AlertDescription>
                        </Alert>
                      )}

                      {isAnalysisInProgress && (
                        <Alert variant="info">
                          <AlertTitle>{t('securityVideos.progressTitle')}</AlertTitle>
                          <AlertDescription>{t('securityVideos.progressDesc')}</AlertDescription>
                        </Alert>
                      )}

                      {video.estado === 'error' && (
                        <>
                          <Alert variant="error" className="flex-1">
                            <AlertTitle>{t('securityVideos.errorTitle')}</AlertTitle>
                            <AlertDescription>
                              {video.metadata_tecnico?.error ||
                                t('securityVideos.errorFallback')}
                            </AlertDescription>
                          </Alert>
                          <Button
                            variant="secondary"
                            className="border-warning-border bg-warning-surface text-warning"
                            onClick={() => handleReintentar(video.id)}
                          >
                            <RotateCcw aria-hidden="true" />
                            {t('securityVideos.retry')}
                          </Button>
                        </>
                      )}

                      <Button
                        variant="outline"
                        className="ml-auto text-error hover:bg-error-surface"
                        onClick={() => setDeleteTarget(video)}
                      >
                        <Trash2 aria-hidden="true" />
                        {t('common.delete')}
                      </Button>
                    </div>

                    {video.fecha_creacion && (
                      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-4 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1.5">
                          <CalendarDays size={13} aria-hidden="true" />
                          {t('securityVideos.created')}: {formatDate(video.fecha_creacion)}
                        </span>
                        {video.fecha_procesamiento && (
                          <span className="flex items-center gap-1.5">
                            <CalendarDays size={13} aria-hidden="true" />
                            {t('securityVideos.processed')}: {formatDate(video.fecha_procesamiento)}
                          </span>
                        )}
                        {video.tiempo_procesamiento_segundos && (
                          <span className="flex items-center gap-1.5">
                            <Timer size={13} aria-hidden="true" />
                            {t('securityVideos.time')}:{' '}
                            {securityVideoService.formatDuration(video.tiempo_procesamiento_segundos)}
                          </span>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </PageSection>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        onConfirm={handleEliminar}
        title={t('securityVideos.deleteTitle')}
        description={t('securityVideos.deleteDescription')}
        confirmText={t('common.delete')}
        loading={deleting}
      />
    </PageContainer>
  );
}
