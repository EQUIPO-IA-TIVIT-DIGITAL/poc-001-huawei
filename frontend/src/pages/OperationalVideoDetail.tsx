import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import {
  operationalVideoService,
  OperationalAnalysis,
  OperationalEvent,
  OperationalAnalysisType,
  SSEProgressData,
  PaginatedEvents,
} from '../services/operationalVideoService';
import { toast } from 'sonner';
import {
  ArrowLeft,
  Clock,
  Image,
  ChevronDown,
  ChevronUp,
  Loader2,
  User,
  ArrowRight,
  Package,
  RefreshCw,
  Download,
  AlertTriangle,
  XCircle,
  Ban,
  Activity,
} from 'lucide-react';
import { PageContainer } from '../components/ui/page-container';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Progress } from '../components/ui/progress';
import { LoadingState } from '../components/ui/loading-state';
import { ErrorState } from '../components/ui/error-state';
import { EmptyState } from '../components/ui/empty-state';
import { StatusBadge, type AppStatus } from '../components/ui/status-badge';
import { Pagination } from '../components/ui/pagination';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useTranslation } from '../i18n';

const statusFromEstado = (estado: string): AppStatus => {
  if (estado === 'completed') return 'completed';
  if (estado === 'error') return 'failed';
  if (estado === 'cancelled') return 'cancelled';
  return 'processing';
};

export default function OperationalVideoDetail() {
  const { analysisId } = useParams({ strict: false }) as { analysisId: string };
  const navigate = useNavigate();
  const { t, formatDateTime } = useTranslation();

  // Core state
  const [analysis, setAnalysis] = useState<OperationalAnalysis | null>(null);
  const [events, setEvents] = useState<OperationalEvent[]>([]);
  const [types, setTypes] = useState<Record<string, OperationalAnalysisType>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null);

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalEvents, setTotalEvents] = useState(0);
  const PER_PAGE = 20;

  // SSE
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollingCleanupRef = useRef<(() => void) | null>(null);
  const [sseConnected, setSSEConnected] = useState(false);

  // Reprocess
  const [reprocessing, setReprocessing] = useState(false);

  // Cancel
  const [cancelling, setCancelling] = useState(false);
  const [showCancelDialog, setShowCancelDialog] = useState(false);

  // ETA
  const [etaSeconds, setEtaSeconds] = useState<number | null>(null);

  // ═══════════════════════════════════════════════════
  // DATA LOADING
  // ═══════════════════════════════════════════════════

  useEffect(() => {
    if (analysisId) loadData();
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (pollingCleanupRef.current) {
        pollingCleanupRef.current();
        pollingCleanupRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId]);

  const loadData = async () => {
    try {
      setLoading(true);
      setLoadError(false);
      const [a, t] = await Promise.all([
        operationalVideoService.obtenerAnalisis(analysisId),
        operationalVideoService.listarTipos(),
      ]);
      setAnalysis(a);
      setTypes(t);

      if (a.estado === 'completed') {
        await loadEvents(1);
      } else if (operationalVideoService.isProcessing(a.estado)) {
        startSSE();
      }
    } catch (error) {
      setLoadError(true);
      toast.error(getErrorText(error, t('operationalDetail.loadError')));
    } finally {
      setLoading(false);
    }
  };

  const loadEvents = async (page: number) => {
    try {
      const res: PaginatedEvents = await operationalVideoService.obtenerEventos(
        analysisId,
        page,
        PER_PAGE,
      );
      setEvents(res.events);
      setCurrentPage(res.page);
      setTotalPages(res.total_pages);
      setTotalEvents(res.total);
    } catch {
      toast.error(t('operationalDetail.eventsError'));
    }
  };

  // ═══════════════════════════════════════════════════
  // SSE — REAL-TIME PROGRESS
  // ═══════════════════════════════════════════════════

  const startSSE = useCallback(() => {
    if (eventSourceRef.current) return;

    try {
      const es = operationalVideoService.connectSSE(
        analysisId,
        (data: SSEProgressData) => {
          setSSEConnected(true);
          if (data.eta_seconds != null) {
            setEtaSeconds(data.eta_seconds);
          }

          setAnalysis((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              estado: data.status,
              progress: data.progress,
              current_phase: data.current_phase,
              summary: data.summary || prev.summary,
              scan_stats: data.scan_stats || prev.scan_stats,
              error_message: data.error_message || prev.error_message,
            };
          });

          if (data.final) {
            setSSEConnected(false);
            setEtaSeconds(null);
            eventSourceRef.current = null;
            if (data.status === 'completed') {
              toast.success(t('operationalDetail.completedToast'));
              loadEvents(1);
              operationalVideoService.obtenerAnalisis(analysisId).then((a) => {
                setAnalysis(a);
              });
            } else if (data.status === 'cancelled') {
              toast.info(t('operationalDetail.cancelledToast'));
            } else if (data.status === 'error') {
              toast.error(t('operationalDetail.failedToast'));
            }
          }
        },
        () => {
          setSSEConnected(false);
          eventSourceRef.current = null;
          startPolling();
        },
      );
      eventSourceRef.current = es;
    } catch {
      startPolling();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId]);

  // Polling fallback
  const startPolling = useCallback(() => {
    if (pollingCleanupRef.current) {
      pollingCleanupRef.current();
      pollingCleanupRef.current = null;
    }

    const interval = setInterval(async () => {
      try {
        const updated = await operationalVideoService.obtenerAnalisis(analysisId);
        setAnalysis(updated);
        if (updated.estado === 'completed') {
          clearInterval(interval);
          pollingCleanupRef.current = null;
          await loadEvents(1);
          toast.success(t('operationalDetail.completedToast'));
        } else if (updated.estado === 'error') {
          clearInterval(interval);
          pollingCleanupRef.current = null;
          toast.error(t('operationalDetail.failedToast'));
        }
      } catch {
        /* ignore polling errors */
      }
    }, 8000);

    pollingCleanupRef.current = () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId]);

  // ═══════════════════════════════════════════════════
  // ACTIONS
  // ═══════════════════════════════════════════════════

  const handleReprocess = async () => {
    if (!analysis || analysis.estado !== 'error') return;
    try {
      setReprocessing(true);
      const res = await operationalVideoService.reprocesarAnalisis(analysisId);
      toast.success(res.message || t('operationalDetail.reprocessSuccess'));
      setAnalysis((prev) =>
        prev ? { ...prev, estado: 'pending', progress: 0, current_phase: '' } : prev,
      );
      setEvents([]);
      startSSE();
    } catch (error) {
      toast.error(getErrorText(error, t('operationalDetail.reprocessFailed')));
    } finally {
      setReprocessing(false);
    }
  };

  const handleCancel = async () => {
    if (!analysis || !operationalVideoService.isCancellable(analysis.estado)) return;
    try {
      setCancelling(true);
      await operationalVideoService.cancelarAnalisis(analysisId);
      toast.info(t('operationalDetail.cancelSuccess'));
      setAnalysis((prev) => (prev ? { ...prev, estado: 'cancelled' } : prev));
      setEtaSeconds(null);
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (pollingCleanupRef.current) {
        pollingCleanupRef.current();
        pollingCleanupRef.current = null;
      }
    } catch (error) {
      toast.error(getErrorText(error, t('operationalDetail.cancelFailed')));
    } finally {
      setCancelling(false);
      setShowCancelDialog(false);
    }
  };

  // ═══════════════════════════════════════════════════
  // HELPERS
  // ═══════════════════════════════════════════════════

  const formatTime = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
  };

  // ═══════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════

  if (loading) {
    return <LoadingState label={t('operationalDetail.loading')} className="min-h-[60vh]" />;
  }

  if (loadError && !analysis) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <ErrorState
          title={t('operationalDetail.loadError')}
          description={t('common.errorGeneric')}
          onRetry={loadData}
        />
        <div className="mt-4">
          <Button variant="outline" onClick={() => navigate({ to: '/operational' })}>
            {t('common.back')}
          </Button>
        </div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <EmptyState
          icon={<Activity aria-hidden="true" />}
          title={t('operationalDetail.notFound')}
          action={
            <Button onClick={() => navigate({ to: '/operational' })}>{t('common.back')}</Button>
          }
        />
      </div>
    );
  }

  const typeInfo = types[analysis.analysis_type] || {
    name: analysis.analysis_type,
    description: '',
    icon: '',
    key_metrics: [],
    estimated_minutes_per_hour: 0,
  };
  const isProcessing = operationalVideoService.isProcessing(analysis.estado);
  const isCancellable = operationalVideoService.isCancellable(analysis.estado);
  const isCancelled = analysis.estado === 'cancelled';
  const isError = analysis.estado === 'error';
  const isCompleted = analysis.estado === 'completed';

  return (
    <PageContainer className="max-w-5xl pb-16">
      <Button
        variant="ghost"
        onClick={() => navigate({ to: '/operational' })}
        className="w-fit px-0 font-bold hover:bg-transparent"
      >
        <ArrowLeft aria-hidden="true" />
        {t('operationalDetail.back')}
      </Button>

      <Card variant="elevated" className="p-8 lg:p-10">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-start">
          <div className="min-w-0 flex-1">
            <div className="mb-3 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-brand-border bg-brand-soft text-brand">
                <Activity size={20} aria-hidden="true" />
              </div>
              <span className="text-[13px] font-bold uppercase tracking-wide text-primary">
                {typeInfo.name}
              </span>
              {sseConnected && (
                <Badge variant="success" className="animate-pulse">
                  <span className="h-1.5 w-1.5 rounded-full bg-success" aria-hidden="true" />
                  {t('operationalDetail.live')}
                </Badge>
              )}
            </div>
            <h1 className="mb-2 truncate text-3xl font-bold tracking-tight text-foreground lg:text-4xl">
              {analysis.video_filename}
            </h1>
            {analysis.custom_context && (
              <p className="mt-2 text-base font-medium italic text-muted-foreground">
                &quot;{analysis.custom_context}&quot;
              </p>
            )}
            <div className="mt-4 flex flex-wrap gap-4 text-[13px] font-bold uppercase tracking-wide text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <Image className="h-4 w-4" aria-hidden="true" />
                {analysis.nombre_camara || t('operationalDetail.noCamera')}
              </span>
              <span
                className={`flex items-center gap-1.5 ${
                  analysis.ubicacion ? 'text-warning' : 'text-muted-foreground'
                }`}
              >
                {analysis.ubicacion ? (
                  <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <XCircle className="h-4 w-4" aria-hidden="true" />
                )}
                {analysis.ubicacion || t('operationalDetail.noLocation')}
              </span>
              {analysis.video_duration > 0 && (
                <span className="flex items-center gap-1.5">
                  <Clock className="h-4 w-4" aria-hidden="true" />
                  {operationalVideoService.formatDuration(analysis.video_duration)}
                </span>
              )}
            </div>
          </div>

          <div className="relative z-10 flex shrink-0 flex-wrap items-center gap-3 md:flex-nowrap">
            {isCompleted && analysis.report_pdf_url && (
              <Button asChild>
                <a href={analysis.report_pdf_url} target="_blank" rel="noopener noreferrer">
                  <Download aria-hidden="true" />
                  {t('operationalDetail.downloadReport')}
                </a>
              </Button>
            )}

            {isCancellable && (
              <Button
                variant="outline"
                onClick={() => setShowCancelDialog(true)}
                disabled={cancelling}
                className="text-error hover:bg-error-surface"
              >
                {cancelling ? (
                  <Loader2 className="animate-spin" aria-hidden="true" />
                ) : (
                  <XCircle aria-hidden="true" />
                )}
                {t('operationalDetail.cancel')}
              </Button>
            )}

            {isError && (
              <Button
                variant="secondary"
                className="border-warning-border bg-warning-surface text-warning hover:bg-warning-surface/80"
                onClick={handleReprocess}
                loading={reprocessing}
              >
                {!reprocessing && <RefreshCw aria-hidden="true" />}
                {t('operationalDetail.reprocess')}
              </Button>
            )}

            <StatusBadge
              status={statusFromEstado(analysis.estado)}
              label={operationalVideoService.getEstadoTexto(analysis.estado)}
            />
          </div>
        </div>

        {isProcessing && analysis.progress > 0 && (
          <div
            className="mt-8 rounded-2xl border border-border bg-muted/50 p-5"
            aria-live="polite"
          >
            <div className="mb-2 flex justify-between text-[13px] font-bold uppercase tracking-wide text-muted-foreground">
              <span>{analysis.current_phase || t('operationalDetail.processingDefault')}</span>
              <div className="flex items-center gap-4">
                {etaSeconds != null && etaSeconds > 0 && (
                  <span className="flex items-center gap-1.5 text-primary">
                    <Clock className="h-4 w-4" aria-hidden="true" />
                    {t('operationalDetail.eta', {
                      time: operationalVideoService.formatETA(etaSeconds),
                    })}
                  </span>
                )}
                <span className="text-foreground">{Math.round(analysis.progress)}%</span>
              </div>
            </div>
            <Progress value={analysis.progress} aria-label={t('operationalDetail.processingDefault')} />
          </div>
        )}

        {isCancelled && (
          <Alert className="mt-6 items-center">
            <Ban aria-hidden="true" />
            <AlertDescription className="font-bold text-muted-foreground">
              {t('operationalDetail.cancelledInfo')}
            </AlertDescription>
          </Alert>
        )}

        {isError && analysis.error_message && (
          <Alert variant="error" className="mt-6">
            <AlertTriangle aria-hidden="true" />
            <AlertDescription className="font-bold">{analysis.error_message}</AlertDescription>
          </Alert>
        )}
      </Card>

      {/* Events Timeline with Pagination */}
      {events.length > 0 ? (
        <Card variant="elevated" className="p-8 lg:p-10">
          <div className="mb-6 flex items-center justify-between">
            <h2 className="flex items-center gap-3 text-xl font-bold text-foreground lg:text-2xl">
              <Image className="h-6 w-6 text-primary" aria-hidden="true" />
              {t('operationalDetail.eventsTitle', { count: totalEvents })}
            </h2>
          </div>

          <div className="space-y-4">
            {events.map((event, idx) => {
              const isExpanded = expandedEvent === event.id;
              const globalIdx = (currentPage - 1) * PER_PAGE + idx + 1;

              return (
                <div
                  key={event.id}
                  className={`overflow-hidden rounded-2xl border transition-all duration-300 ${
                    isExpanded
                      ? 'border-border bg-muted/30 shadow-card'
                      : 'border-border hover:shadow-card'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setExpandedEvent(isExpanded ? null : event.id)}
                    aria-expanded={isExpanded}
                    className="flex w-full items-center justify-between p-5 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring lg:px-6"
                  >
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="rounded-full border border-border bg-muted px-3 py-1 font-mono text-[12px] font-bold text-muted-foreground">
                        #{globalIdx}
                      </span>
                      <span className="text-[14px] font-bold tracking-wide text-foreground">
                        {formatTime(event.timestamp_start)} — {formatTime(event.timestamp_end)}
                      </span>
                      <Badge variant="destructive" className="uppercase">
                        {event.event_type.replace(/_/g, ' ')}
                      </Badge>
                      {event.direction && (
                        <span className="ml-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                          <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                          {event.direction}
                        </span>
                      )}
                    </div>
                    <div className="rounded-full bg-muted p-1.5 text-muted-foreground">
                      {isExpanded ? (
                        <ChevronUp className="h-5 w-5" aria-hidden="true" />
                      ) : (
                        <ChevronDown className="h-5 w-5" aria-hidden="true" />
                      )}
                    </div>
                  </button>

                  {isExpanded && (
                    <div className="mt-2 border-t border-border p-5 pt-0 lg:px-6">
                      <div className="mt-4 grid grid-cols-1 gap-6 lg:grid-cols-2">
                        <div className="space-y-4">
                          {event.person_description && (
                            <div className="flex items-start gap-3 rounded-2xl border border-border bg-card p-4">
                              <User className="mt-0.5 h-5 w-5 text-primary" aria-hidden="true" />
                              <div>
                                <p className="mb-1 text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                                  {t('operationalDetail.person')}
                                </p>
                                <p className="text-[14px] font-medium text-foreground">
                                  {event.person_description}
                                </p>
                              </div>
                            </div>
                          )}
                          {event.carried_objects && (
                            <div className="flex items-start gap-3 rounded-2xl border border-border bg-card p-4">
                              <Package className="mt-0.5 h-5 w-5 text-primary" aria-hidden="true" />
                              <div>
                                <p className="mb-1 text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                                  {t('operationalDetail.objects')}
                                </p>
                                <p className="text-[14px] font-medium text-foreground">
                                  {event.carried_objects}
                                </p>
                              </div>
                            </div>
                          )}
                          {event.confidence && (
                            <p className="px-1 text-[12px] font-bold uppercase tracking-wide text-muted-foreground">
                              {t('operationalDetail.confidence', { value: event.confidence })}
                            </p>
                          )}
                          {event.details && Object.keys(event.details).length > 0 && (
                            <details className="mt-4 rounded-2xl border border-border bg-card p-4">
                              <summary className="flex cursor-pointer items-center gap-2 text-[12px] font-bold uppercase tracking-wide text-muted-foreground hover:text-primary">
                                {t('operationalDetail.completeMeta')}
                              </summary>
                              <pre className="mt-4 max-h-48 overflow-auto rounded-xl border border-border bg-muted p-4 text-xs text-muted-foreground">
                                {JSON.stringify(event.details, null, 2)}
                              </pre>
                            </details>
                          )}
                        </div>

                        {event.frame_urls && event.frame_urls.length > 0 && (
                          <div className="rounded-2xl border border-border bg-card p-4">
                            <p className="mb-3 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                              <Image className="h-4 w-4" aria-hidden="true" />
                              {t('operationalDetail.captures', { count: event.frame_urls.length })}
                            </p>
                            <div className="grid grid-cols-2 gap-3">
                              {event.frame_urls.map((url, fIdx) => (
                                <a
                                  key={fIdx}
                                  href={url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="overflow-hidden rounded-xl border border-border"
                                >
                                  <img
                                    src={url}
                                    alt={t('operationalDetail.frame', { number: fIdx + 1 })}
                                    crossOrigin="use-credentials"
                                    className="h-32 w-full object-cover transition-transform duration-500 hover:scale-105"
                                    loading="lazy"
                                  />
                                </a>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {totalPages > 1 && (
            <Pagination
              page={currentPage}
              totalPages={totalPages}
              onPageChange={loadEvents}
              className="mt-8"
            />
          )}
        </Card>
      ) : isCompleted ? (
        <EmptyState
          icon={<Activity aria-hidden="true" />}
          title={t('operationalDetail.completedNoEventsTitle')}
          description={t('operationalDetail.completedNoEventsDesc')}
        />
      ) : null}

      <div className="mt-8 text-center text-[12px] font-bold uppercase tracking-wide text-muted-foreground">
        {t('operationalDetail.createdAt', { date: formatDateTime(analysis.created_at) })}
        {analysis.completed_at && (
          <> &bull; {t('operationalDetail.completedAt', { date: formatDateTime(analysis.completed_at) })}</>
        )}
        {analysis.tiempo_procesamiento_segundos > 0 && (
          <>
            {' '}
            &bull;{' '}
            {t('operationalDetail.processingTime', {
              time: operationalVideoService.formatDuration(
                analysis.tiempo_procesamiento_segundos,
              ),
            })}
          </>
        )}
      </div>

      <ConfirmDialog
        open={showCancelDialog}
        onOpenChange={setShowCancelDialog}
        onConfirm={handleCancel}
        title={t('operationalDetail.cancelTitle')}
        description={t('operationalDetail.cancelDescription')}
        confirmText={t('operationalDetail.cancel')}
        variant="warning"
        loading={cancelling}
      />
    </PageContainer>
  );
}

function getErrorText(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  if (error && typeof error === 'object' && 'message' in error) {
    return String((error as { message: unknown }).message);
  }
  return fallback;
}
