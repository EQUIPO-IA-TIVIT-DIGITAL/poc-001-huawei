import { ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Activity,
  CheckCircle,
  Clock,
  FileText,
  Filter,
  Package,
  Plus,
  RefreshCw,
  RotateCcw,
  Shield,
  Trash2,
  Users,
  XCircle,
  LayoutGrid,
  Table,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  AnalysisComparison,
  OperationalAnalysisType,
  operationalVideoService,
} from '../services/operationalVideoService';
import { getErrorMessage } from '../lib/errors';
import { PageContainer } from '../components/ui/page-container';
import { PageHeader } from '../components/ui/page-header';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Progress } from '../components/ui/progress';
import { EmptyState } from '../components/ui/empty-state';
import { LoadingState } from '../components/ui/loading-state';
import { StatusBadge, type AppStatus } from '../components/ui/status-badge';
import { SearchInput } from '../components/ui/search-input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useTranslation } from '../i18n';

type ViewMode = 'cards' | 'table';

const ALL_TYPES = 'all';

const CATEGORY_ICON_MAP: Record<string, ReactNode> = {
  ACCESS_CONTROL: <Shield className="h-5 w-5 text-primary" aria-hidden="true" />,
  OCCUPANCY: <Users className="h-5 w-5 text-primary" aria-hidden="true" />,
  PEOPLE_FLOW: <Activity className="h-5 w-5 text-primary" aria-hidden="true" />,
  MERCHANDISE_CONTROL: <Package className="h-5 w-5 text-primary" aria-hidden="true" />,
  PARKING: <Activity className="h-5 w-5 text-primary" aria-hidden="true" />,
  WORK_SUPERVISION: <CheckCircle className="h-5 w-5 text-primary" aria-hidden="true" />,
};

const QUICK_START_ORDER = [
  'ACCESS_CONTROL',
  'MERCHANDISE_CONTROL',
  'OCCUPANCY',
  'PARKING',
  'PEOPLE_FLOW',
  'WORK_SUPERVISION',
];

const statusFromEstado = (estado: string): AppStatus => {
  if (estado === 'completed') return 'completed';
  if (estado === 'cancelled') return 'cancelled';
  if (estado === 'error') return 'failed';
  return 'processing';
};

const itemVariants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0 },
};

export default function OperationalVideos() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [filtroTipo, setFiltroTipo] = useState<string>(ALL_TYPES);
  const [searchTerm, setSearchTerm] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('cards');

  const [compareA, setCompareA] = useState('');
  const [compareB, setCompareB] = useState('');
  const [comparison, setComparison] = useState<AnalysisComparison | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<string | null>(null);

  const prevStatusRef = useRef<Record<string, string>>({});
  const hasLoadedOnceRef = useRef(false);

  const { data: types = {}, isLoading: loadingTypes } = useQuery({
    queryKey: ['operational-types'],
    queryFn: async () => operationalVideoService.listarTipos(),
    staleTime: 10 * 60 * 1000,
  });

  const {
    data: analyses = [],
    isLoading: loadingAnalyses,
    refetch: refetchAnalyses,
  } = useQuery({
    queryKey: ['operational-analyses', filtroTipo],
    queryFn: async () => {
      const params: { limit: number; analysis_type?: string } = { limit: 50 };
      if (filtroTipo && filtroTipo !== ALL_TYPES) params.analysis_type = filtroTipo;
      const response = await operationalVideoService.listarAnalisis(params);
      return response.analyses || [];
    },
    staleTime: 20 * 1000,
  });

  const deleteMutation = useMutation({
    mutationFn: async (analysisId: string) => operationalVideoService.eliminarAnalisis(analysisId),
    onSuccess: () => {
      toast.success(t('operational.deleted'));
      queryClient.invalidateQueries({ queryKey: ['operational-analyses'] });
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error));
    },
  });

  const reprocessMutation = useMutation({
    mutationFn: async (analysisId: string) => operationalVideoService.reprocesarAnalisis(analysisId),
    onSuccess: () => {
      toast.success(t('operational.reprocessSuccess'));
      queryClient.invalidateQueries({ queryKey: ['operational-analyses'] });
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error));
    },
  });

  const cancelMutation = useMutation({
    mutationFn: async (analysisId: string) => operationalVideoService.cancelarAnalisis(analysisId),
    onSuccess: () => {
      toast.info(t('operational.cancelSuccess'));
      queryClient.invalidateQueries({ queryKey: ['operational-analyses'] });
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error));
    },
  });

  const compareMutation = useMutation({
    mutationFn: async ({ a, b }: { a: string; b: string }) =>
      operationalVideoService.compararAnalisis(a, b),
    onSuccess: (result) => {
      setComparison(result);
      toast.success(t('operational.compareSuccess'));
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error));
    },
  });

  const loading = loadingTypes || loadingAnalyses;
  const hasProcessing = analyses.some((a) => operationalVideoService.isProcessing(a.estado));

  const completedAnalyses = useMemo(
    () => analyses.filter((a) => a.estado === 'completed'),
    [analyses],
  );

  const visibleAnalyses = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return analyses;

    return analyses.filter((a) => {
      const haystack = [
        a.video_filename,
        a.custom_context,
        a.analysis_type,
        a.nombre_camara,
        a.ubicacion,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [analyses, searchTerm]);

  useEffect(() => {
    if (!hasProcessing) return;
    const interval = window.setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ['operational-analyses'] });
    }, 10000);
    return () => window.clearInterval(interval);
  }, [hasProcessing, queryClient]);

  useEffect(() => {
    if (loading) return;
    if (!hasLoadedOnceRef.current) {
      prevStatusRef.current = Object.fromEntries(analyses.map((a) => [a.id, a.estado]));
      hasLoadedOnceRef.current = true;
      return;
    }

    analyses.forEach((a) => {
      const prev = prevStatusRef.current[a.id];
      if (a.estado === 'completed' && prev && prev !== 'completed') {
        toast.success(t('operational.completedToast', { name: a.video_filename }));
      }
      if (a.estado === 'cancelled' && prev && prev !== 'cancelled') {
        toast.info(t('operational.cancelledToast', { name: a.video_filename }));
      }
    });

    prevStatusRef.current = Object.fromEntries(analyses.map((a) => [a.id, a.estado]));
  }, [analyses, loading, t]);

  const getTypeInfo = (type: string): OperationalAnalysisType => {
    return (
      types[type] || {
        name: type,
        description: '',
        icon: '',
        key_metrics: [],
        estimated_minutes_per_hour: 8,
      }
    );
  };

  const getTypeIcon = (type: string): ReactNode => {
    return CATEGORY_ICON_MAP[type] || <Activity className="h-5 w-5 text-primary" aria-hidden="true" />;
  };

  const handleCompare = async () => {
    if (!compareA || !compareB || compareA === compareB) {
      toast.error(t('operational.compareSelectError'));
      return;
    }
    await compareMutation.mutateAsync({ a: compareA, b: compareB });
  };

  const handleReprocess = async (analysisId: string) => {
    await reprocessMutation.mutateAsync(analysisId);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    await deleteMutation.mutateAsync(deleteTarget);
    setDeleteTarget(null);
  };

  const confirmCancel = async () => {
    if (!cancelTarget) return;
    await cancelMutation.mutateAsync(cancelTarget);
    setCancelTarget(null);
  };

  const formatDate = (isoDate: string) => {
    if (!isoDate) return 'N/A';
    return new Date(isoDate).toLocaleString('es-ES', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const readyCount = analyses.filter((a) => a.estado === 'completed').length;

  return (
    <PageContainer className="pb-16">
      <PageHeader
        icon={Activity}
        title={t('operational.title')}
        description={t('operational.description')}
        actions={
          <>
            {readyCount > 0 && (
              <Badge variant="success">{t('operational.readyReports', { count: readyCount })}</Badge>
            )}
            {analyses.length > 0 && (
              <Button
                onClick={() =>
                  navigate({ to: '/operational/upload', search: { analysisType: undefined } })
                }
              >
                <Plus aria-hidden="true" />
                {t('operational.newAnalysis')}
              </Button>
            )}
          </>
        }
      />

      <Card>
        <CardContent className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
          <div
            role="group"
            aria-label={t('common.filter')}
            className="inline-flex w-fit gap-1 rounded-lg border border-border bg-muted p-1"
          >
            <button
              type="button"
              onClick={() => setViewMode('cards')}
              aria-pressed={viewMode === 'cards'}
              className={`inline-flex items-center gap-2 rounded-md px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                viewMode === 'cards'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <LayoutGrid size={16} aria-hidden="true" />
              {t('operational.viewCards')}
            </button>
            <button
              type="button"
              onClick={() => setViewMode('table')}
              aria-pressed={viewMode === 'table'}
              className={`inline-flex items-center gap-2 rounded-md px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                viewMode === 'table'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Table size={16} aria-hidden="true" />
              {t('operational.viewTable')}
            </button>
          </div>

          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <div className="lg:min-w-[320px] lg:flex-1">
              <SearchInput
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onClear={() => setSearchTerm('')}
                placeholder={t('operational.searchPlaceholder')}
                aria-label={t('common.search')}
              />
            </div>

            <div className="flex items-center gap-3">
              <div className="w-full sm:w-56">
                <Select value={filtroTipo} onValueChange={setFiltroTipo}>
                  <SelectTrigger aria-label={t('common.filter')}>
                    <Filter size={15} className="text-muted-foreground" aria-hidden="true" />
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL_TYPES}>{t('operational.filterAll')}</SelectItem>
                    {Object.entries(types).map(([key, info]) => (
                      <SelectItem key={key} value={key}>
                        {info.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <Button
                variant="outline"
                size="icon"
                onClick={() => refetchAnalyses()}
                aria-label={t('common.refresh')}
              >
                <RefreshCw aria-hidden="true" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {completedAnalyses.length >= 2 && (
        <Card>
          <CardHeader>
            <CardTitle>{t('operational.compareTitle')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
              <Select value={compareA} onValueChange={setCompareA}>
                <SelectTrigger aria-label={t('operational.compareA')}>
                  <SelectValue placeholder={t('operational.compareA')} />
                </SelectTrigger>
                <SelectContent>
                  {completedAnalyses.map((a) => (
                    <SelectItem key={`a-${a.id}`} value={a.id}>
                      {a.video_filename}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={compareB} onValueChange={setCompareB}>
                <SelectTrigger aria-label={t('operational.compareB')}>
                  <SelectValue placeholder={t('operational.compareB')} />
                </SelectTrigger>
                <SelectContent>
                  {completedAnalyses.map((a) => (
                    <SelectItem key={`b-${a.id}`} value={a.id}>
                      {a.video_filename}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Button onClick={handleCompare} loading={compareMutation.isPending}>
                {compareMutation.isPending
                  ? t('operational.comparing')
                  : t('operational.compare')}
              </Button>

              {comparison && (
                <Button variant="outline" onClick={() => setComparison(null)}>
                  {t('operational.clear')}
                </Button>
              )}
            </div>

            {comparison && (
              <div className="rounded-lg border border-border bg-muted/50 p-4">
                <p className="mb-2 text-sm font-semibold text-foreground">
                  {t('operational.result')}
                </p>
                <p className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>{t('operational.eventsA', { count: comparison.analysis_a.total_events })}</span>
                  <span>{t('operational.eventsB', { count: comparison.analysis_b.total_events })}</span>
                  <span>{t('operational.delta', { count: comparison.event_count_delta })}</span>
                </p>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {Object.entries(comparison.deltas)
                    .slice(0, 8)
                    .map(([key, val]) => (
                      <div key={key} className="rounded-md border border-border bg-card p-2.5">
                        <p className="text-xs uppercase text-muted-foreground">
                          {key.replace(/_/g, ' ')}
                        </p>
                        <p className="text-sm text-foreground">
                          A: {val.analysis_a} - B: {val.analysis_b} - Delta: {val.delta} (
                          {val.delta_pct}%)
                        </p>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {loading && <LoadingState label={t('common.loading')} />}

      {!loading && analyses.length === 0 && (
        <EmptyState
          icon={<Activity aria-hidden="true" />}
          title={t('operational.emptyTitle')}
          description={t('operational.emptyDescription')}
          className="py-16"
          action={
            <div className="flex flex-col items-center gap-6">
              <div className="flex flex-wrap justify-center gap-2">
                {QUICK_START_ORDER.filter((key) => types[key]).map((key) => (
                  <Button
                    key={key}
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      navigate({ to: '/operational/upload', search: { analysisType: key } })
                    }
                    aria-label={`${t('operational.newAnalysis')} ${types[key].name}`}
                  >
                    {getTypeIcon(key)}
                    {types[key].name}
                  </Button>
                ))}
              </div>
              <Button
                onClick={() =>
                  navigate({ to: '/operational/upload', search: { analysisType: undefined } })
                }
              >
                <Plus aria-hidden="true" />
                {t('operational.createNew')}
              </Button>
            </div>
          }
        />
      )}

      {!loading && analyses.length > 0 && visibleAnalyses.length === 0 && (
        <EmptyState
          icon={<Filter aria-hidden="true" />}
          title={t('operational.noResultsTitle')}
          description={t('operational.noResultsDescription')}
        />
      )}

      {!loading && visibleAnalyses.length > 0 && viewMode === 'cards' && (
        <div className="grid gap-5">
          <AnimatePresence>
            {visibleAnalyses.map((analysis, index) => {
              const typeInfo = getTypeInfo(analysis.analysis_type);
              const isProc = operationalVideoService.isProcessing(analysis.estado);

              return (
                <motion.div
                  key={analysis.id}
                  variants={itemVariants}
                  initial="hidden"
                  animate="show"
                  exit="hidden"
                  transition={{ duration: 0.25, delay: Math.min(index * 0.03, 0.2) }}
                >
                  <Card variant="elevated">
                    <CardContent className="p-6">
                      <div className="mb-5 flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1 pr-2">
                          <div className="mb-2 flex items-center gap-2">
                            {getTypeIcon(analysis.analysis_type)}
                            <span className="text-xs font-bold uppercase tracking-wide text-primary">
                              {typeInfo.name}
                            </span>
                          </div>
                          <h3 className="mb-1.5 truncate text-xl font-bold text-foreground">
                            {analysis.video_filename}
                          </h3>
                          {analysis.custom_context && (
                            <p className="line-clamp-2 text-sm italic leading-relaxed text-muted-foreground">
                              &ldquo;{analysis.custom_context}&rdquo;
                            </p>
                          )}
                        </div>
                        <StatusBadge status={statusFromEstado(analysis.estado)} />
                      </div>

                      {isProc && analysis.progress > 0 && (
                        <div className="mb-5 rounded-lg border border-border bg-muted/50 p-4">
                          <div className="mb-1.5 flex justify-between text-xs font-bold uppercase tracking-wide text-muted-foreground">
                            <span>{analysis.current_phase || t('operational.processing')}</span>
                            <span className="text-foreground">{Math.round(analysis.progress)}%</span>
                          </div>
                          <Progress value={analysis.progress} aria-label={typeInfo.name} />
                        </div>
                      )}

                      {analysis.scan_stats && Object.keys(analysis.scan_stats).length > 0 && (
                        <div className="mb-5 grid grid-cols-3 gap-3 rounded-lg border border-border bg-muted/50 p-4">
                          <div>
                            <p className="mb-1 text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                              {t('operational.segments')}
                            </p>
                            <p className="text-xl font-bold text-foreground">
                              {analysis.scan_stats.segments_for_analysis || 0}
                            </p>
                          </div>
                          <div>
                            <p className="mb-1 text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                              {t('operational.detectedEvents')}
                            </p>
                            <p className="text-xl font-bold text-primary">
                              {analysis.scan_stats.total_events ??
                                analysis.scan_stats.detected_events ??
                                0}
                            </p>
                          </div>
                          <div>
                            <p className="mb-1 text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                              {t('operational.duration')}
                            </p>
                            <p className="text-xl font-bold text-foreground">
                              {analysis.video_duration > 0
                                ? operationalVideoService.formatDuration(analysis.video_duration)
                                : 'N/A'}
                            </p>
                          </div>
                        </div>
                      )}

                      <div className="flex flex-wrap gap-3">
                        {analysis.estado === 'completed' && (
                          <Button
                            onClick={() => navigate({ to: `/operational/${analysis.id}` })}
                          >
                            <FileText aria-hidden="true" />
                            {t('operational.viewDetail')}
                          </Button>
                        )}

                        {isProc && operationalVideoService.isCancellable(analysis.estado) && (
                          <Button
                            variant="outline"
                            onClick={() => setCancelTarget(analysis.id)}
                          >
                            <XCircle aria-hidden="true" />
                            {t('operational.cancel')}
                          </Button>
                        )}

                        {analysis.estado === 'error' && (
                          <Button
                            variant="secondary"
                            className="border-warning-border bg-warning-surface text-warning"
                            onClick={() => handleReprocess(analysis.id)}
                          >
                            <RotateCcw aria-hidden="true" />
                            {t('operational.reprocess')}
                          </Button>
                        )}

                        <Button
                          variant="ghost"
                          className="ml-auto text-error hover:bg-error-surface"
                          onClick={() => setDeleteTarget(analysis.id)}
                        >
                          <Trash2 aria-hidden="true" />
                          {t('operational.delete')}
                        </Button>
                      </div>

                      {analysis.created_at && (
                        <div className="mt-5 flex items-center gap-2 border-t border-border pt-4 text-xs font-medium text-muted-foreground">
                          <Clock size={13} aria-hidden="true" />
                          <span>
                            {t('operational.created')}: {formatDate(analysis.created_at)}
                            {analysis.completed_at && (
                              <>
                                {' '}
                                &bull; {t('operational.completedAt')}:{' '}
                                {formatDate(analysis.completed_at)}
                              </>
                            )}
                            {analysis.tiempo_procesamiento_segundos > 0 && (
                              <span className="hidden sm:inline">
                                {' '}
                                &bull; {t('operational.time')}:{' '}
                                {operationalVideoService.formatDuration(
                                  analysis.tiempo_procesamiento_segundos,
                                )}
                              </span>
                            )}
                          </span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}

      {!loading && visibleAnalyses.length > 0 && viewMode === 'table' && (
        <Card variant="elevated" className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold">{t('operational.headerType')}</th>
                  <th className="px-4 py-3 text-left font-semibold">{t('operational.headerFile')}</th>
                  <th className="px-4 py-3 text-left font-semibold">{t('operational.headerStatus')}</th>
                  <th className="px-4 py-3 text-left font-semibold">
                    {t('operational.headerCreated')}
                  </th>
                  <th className="px-4 py-3 text-right font-semibold">
                    {t('operational.headerActions')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {visibleAnalyses.map((analysis) => {
                  const typeInfo = getTypeInfo(analysis.analysis_type);
                  const isProc = operationalVideoService.isProcessing(analysis.estado);

                  return (
                    <tr key={analysis.id} className="border-t border-border hover:bg-muted/40">
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-2 font-medium text-primary">
                          {getTypeIcon(analysis.analysis_type)}
                          {typeInfo.name}
                        </span>
                      </td>
                      <td className="max-w-[340px] truncate px-4 py-3 text-foreground">
                        {analysis.video_filename}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={statusFromEstado(analysis.estado)} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDate(analysis.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-2">
                          {analysis.estado === 'completed' && (
                            <Button
                              variant="outline"
                              size="xs"
                              onClick={() => navigate({ to: `/operational/${analysis.id}` })}
                            >
                              {t('operational.detail')}
                            </Button>
                          )}
                          {analysis.estado === 'error' && (
                            <Button
                              variant="secondary"
                              size="xs"
                              className="border-warning-border bg-warning-surface text-warning"
                              onClick={() => handleReprocess(analysis.id)}
                            >
                              {t('operational.reprocess')}
                            </Button>
                          )}
                          {isProc && operationalVideoService.isCancellable(analysis.estado) && (
                            <Button
                              variant="outline"
                              size="xs"
                              onClick={() => setCancelTarget(analysis.id)}
                            >
                              {t('operational.cancel')}
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="xs"
                            className="text-error hover:bg-error-surface"
                            onClick={() => setDeleteTarget(analysis.id)}
                          >
                            {t('operational.delete')}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        onConfirm={confirmDelete}
        title={t('operational.deleteTitle')}
        description={t('operational.deleteDescription')}
        confirmText={t('common.delete')}
        loading={deleteMutation.isPending}
      />

      <ConfirmDialog
        open={cancelTarget !== null}
        onOpenChange={(open) => !open && setCancelTarget(null)}
        onConfirm={confirmCancel}
        title={t('operational.cancelTitle')}
        description={t('operational.cancelDescription')}
        confirmText={t('operational.cancel')}
        variant="warning"
        loading={cancelMutation.isPending}
      />
    </PageContainer>
  );
}
