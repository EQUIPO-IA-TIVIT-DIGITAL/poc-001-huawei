import { useState, useEffect, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { audioAnalysisService, AudioAnalysis } from '../services/audioAnalysisService';
import { getErrorMessage } from '../lib/errors';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus,
  Clock,
  FileText,
  Trash2,
  RefreshCw,
  Loader2,
  Headphones,
  RotateCcw,
  Ban,
  Mic,
  Timer,
  Sparkles,
  MessageSquare,
  Play,
  AudioWaveform,
  HardDrive,
  BarChart3,
  Zap,
  Eye,
} from 'lucide-react';
import { PageContainer } from '../components/ui/page-container';
import { PageHeader } from '../components/ui/page-header';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Progress } from '../components/ui/progress';
import { StatusBadge, type AppStatus } from '../components/ui/status-badge';
import { EmptyStateCard } from '../components/EmptyStateCard';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useTranslation, type TranslationKey } from '../i18n';

const AUDIO_STATUS_MAP: Record<string, { status: AppStatus; labelKey: TranslationKey }> = {
  pending: { status: 'pending', labelKey: 'audio.statusPending' },
  uploading: { status: 'uploading', labelKey: 'audio.statusUploading' },
  extracting_audio: { status: 'processing', labelKey: 'audio.statusExtracting' },
  audio_ready: { status: 'processing', labelKey: 'audio.statusAudioReady' },
  transcribing: { status: 'processing', labelKey: 'audio.statusTranscribing' },
  transcribed: { status: 'processing', labelKey: 'audio.statusTranscribed' },
  indexing: { status: 'processing', labelKey: 'audio.statusIndexing' },
  completed: { status: 'completed', labelKey: 'audio.statusCompleted' },
  cancelled: { status: 'cancelled', labelKey: 'audio.statusCancelled' },
  error: { status: 'failed', labelKey: 'audio.statusError' },
};

const getStatusConfig = (estado: string) =>
  AUDIO_STATUS_MAP[estado] ?? AUDIO_STATUS_MAP.pending;

export default function AudioAnalyses() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [analyses, setAnalyses] = useState<AudioAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedPlayerById, setExpandedPlayerById] = useState<Record<string, boolean>>({});
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const prevStatusRef = useRef<Record<string, string>>({});
  const hasLoadedOnceRef = useRef(false);

  useEffect(() => {
    cargarAnalisis();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-refresh cada 10s si hay análisis en curso
  useEffect(() => {
    const hasProcessing = analyses.some((a) => audioAnalysisService.isProcessing(a.estado));
    if (hasProcessing) {
      const interval = setInterval(cargarAnalisis, 10000);
      return () => clearInterval(interval);
    }
  }, [analyses]);

  const cargarAnalisis = async () => {
    try {
      setLoading(true);
      const response = await audioAnalysisService.listarAnalisis();
      const nextAnalyses = response.analyses;

      // Notificar cuando un análisis se completa
      if (hasLoadedOnceRef.current) {
        nextAnalyses.forEach((a) => {
          const prev = prevStatusRef.current[a.id];
          if (a.estado === 'completed' && prev && prev !== 'completed') {
            toast.success(
              t('audio.transcriptionCompleted', { name: a.titulo || a.video_filename }),
            );
          }
        });
      }

      prevStatusRef.current = Object.fromEntries(nextAnalyses.map((a) => [a.id, a.estado]));
      hasLoadedOnceRef.current = true;
      setAnalyses(nextAnalyses);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const handleEliminar = (analysisId: string, titulo: string) => {
    setDeleteTarget({ id: analysisId, title: titulo });
  };

  const confirmEliminar = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await audioAnalysisService.eliminarAnalisis(deleteTarget.id);
      toast.success(t('audio.deleted'));
      setDeleteTarget(null);
      cargarAnalisis();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setDeleting(false);
    }
  };

  const handleReprocesar = async (analysisId: string) => {
    try {
      await audioAnalysisService.reprocesarAnalisis(analysisId);
      toast.success(t('audio.reprocessed'));
      cargarAnalisis();
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const dateFormatter = new Intl.DateTimeFormat('es-ES', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  const formatDate = (isoDate: string) => {
    if (!isoDate) return t('common.noDate');
    const date = new Date(isoDate);
    if (Number.isNaN(date.getTime())) return t('common.noDate');
    return dateFormatter.format(date);
  };

  const getFriendlyTitle = (analysis: AudioAnalysis): string => {
    const raw = (analysis.titulo || analysis.video_filename || '').trim();
    if (!raw) return t('audio.defaultTitle');

    let cleaned = raw
      .replace(/\.[a-z0-9]{2,4}$/i, '')
      .replace(/[_-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    if (/^whatsapp ptt/i.test(cleaned)) {
      cleaned = cleaned.replace(/^whatsapp ptt\s*/i, t('audio.whatsappAudio'));
    }

    return cleaned || t('audio.defaultTitle');
  };

  const getContextSnippet = (analysis: AudioAnalysis): string => {
    const snippet = (analysis.full_transcription || analysis.descripcion || '').trim();
    return snippet.length > 0 ? snippet : t('audio.noContext');
  };

  const readyCount = analyses.filter((a) => a.estado === 'completed').length;
  const processingCount = analyses.filter((a) =>
    audioAnalysisService.isProcessing(a.estado),
  ).length;
  const isEmpty = !loading && analyses.length === 0;

  return (
    <PageContainer className="pb-16">
      <PageHeader
        icon={Headphones}
        title={t('audio.title')}
        description={t('audio.description')}
        actions={
          <>
            {analyses.length > 0 && (
              <Button variant="outline" onClick={cargarAnalisis}>
                <RefreshCw aria-hidden="true" />
                {t('common.refresh')}
              </Button>
            )}
            {!isEmpty && (
              <Button onClick={() => navigate({ to: '/audio/upload' })}>
                <Plus aria-hidden="true" />
                {t('audio.newAnalysis')}
              </Button>
            )}
          </>
        }
      />

      {analyses.length > 0 && (
        <div className="flex flex-wrap gap-3">
          <Badge variant="muted">
            <AudioWaveform aria-hidden="true" />
            {t('audio.total')}: {analyses.length}
          </Badge>
          <Badge variant="success">
            <Zap aria-hidden="true" />
            {t('audio.completed')}: {readyCount}
          </Badge>
          {processingCount > 0 && (
            <Badge variant="warning">
              <Loader2 className="animate-spin" aria-hidden="true" />
              {t('audio.processing')}: {processingCount}
            </Badge>
          )}
        </div>
      )}

      {loading && analyses.length === 0 && (
        <LoadingAnalyses label={t('audio.loading')} />
      )}

      {!loading && analyses.length === 0 && (
        <EmptyStateCard
          icon={<Headphones className="h-7 w-7" />}
          title={t('audio.emptyTitle')}
          description={t('audio.emptyDescription')}
          primaryActionLabel={t('audio.newAnalysis')}
          primaryActionIcon={<Plus className="h-5 w-5" />}
          onPrimaryAction={() => navigate({ to: '/audio/upload' })}
          features={[
            { icon: <Mic className="h-3.5 w-3.5" aria-hidden="true" />, label: t('audio.featureTranscription') },
            { icon: <Timer className="h-3.5 w-3.5" aria-hidden="true" />, label: t('audio.featureTimestamps') },
            { icon: <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />, label: t('audio.featureQueries') },
            { icon: <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />, label: t('audio.featureSummary') },
          ]}
        />
      )}

      {!loading && analyses.length > 0 && (
        <div className="grid gap-5">
          <AnimatePresence>
            {analyses.map((analysis, index) => {
              const isProc = audioAnalysisService.isProcessing(analysis.estado);
              const friendlyTitle = getFriendlyTitle(analysis);
              const contextSnippet = getContextSnippet(analysis);
              const canPlayInline = Boolean(
                analysis.audio_url && analysis.audio_url.startsWith('http'),
              );
              const showPlayer = Boolean(expandedPlayerById[analysis.id]) && canPlayInline;
              const statusConfig = getStatusConfig(analysis.estado);

              return (
                <motion.article
                  key={analysis.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  transition={{ duration: 0.3, delay: Math.min(index * 0.05, 0.3) }}
                >
                  <Card variant="elevated" className="overflow-hidden">
                    <CardContent className="p-6 lg:p-7">
                      <div className="mb-4 flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <div className="mb-2 flex items-center gap-3">
                            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-primary">
                              <Headphones className="h-5 w-5" aria-hidden="true" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <h3
                                className="truncate text-base font-bold text-foreground"
                                title={friendlyTitle}
                              >
                                {friendlyTitle}
                              </h3>
                            </div>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                if (canPlayInline) {
                                  setExpandedPlayerById((prev) => ({
                                    ...prev,
                                    [analysis.id]: !prev[analysis.id],
                                  }));
                                } else {
                                  navigate({ to: `/audio/${analysis.id}` });
                                }
                              }}
                              aria-label={
                                canPlayInline
                                  ? t('audio.listenTitle')
                                  : t('audio.openToListen')
                              }
                            >
                              <Play aria-hidden="true" />
                              {t('audio.listen')}
                            </Button>
                            <StatusBadge
                              status={statusConfig.status}
                              label={t(statusConfig.labelKey)}
                            />
                          </div>
                          <p
                            className="truncate pl-[52px] text-sm font-medium text-muted-foreground"
                            title={contextSnippet}
                          >
                            {contextSnippet}
                          </p>
                        </div>
                      </div>

                      <AnimatePresence>
                        {showPlayer && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="mb-4 ml-12 overflow-hidden"
                          >
                            <div className="rounded-lg border border-border bg-muted/50 p-3">
                              <audio
                                controls
                                preload="none"
                                className="w-full"
                                src={analysis.audio_url}
                              />
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>

                      {isProc && analysis.progress > 0 && (
                        <div className="mb-4 ml-12">
                          <div className="mb-1.5 flex justify-between text-xs text-muted-foreground">
                            <span className="font-medium">
                              {analysis.current_phase || t('operational.processing')}
                            </span>
                            <span className="font-semibold text-foreground">
                              {Math.round(analysis.progress)}%
                            </span>
                          </div>
                          <Progress value={analysis.progress} />
                        </div>
                      )}

                      {analysis.estado === 'completed' && (
                        <div className="mb-4 ml-12 flex flex-wrap items-center gap-2">
                          <Badge variant="muted">
                            <BarChart3 aria-hidden="true" />
                            {t('audio.segments', { count: analysis.total_segments })}
                          </Badge>
                          <Badge variant="success">
                            <Zap aria-hidden="true" />
                            {t('audio.confidence', {
                              percent: (analysis.average_confidence * 100).toFixed(0),
                            })}
                          </Badge>
                          {analysis.video_duration > 0 && (
                            <Badge variant="info">
                              <Clock aria-hidden="true" />
                              {audioAnalysisService.formatDuration(analysis.video_duration)}
                            </Badge>
                          )}
                          {analysis.video_size_mb > 0 && (
                            <Badge variant="secondary">
                              <HardDrive aria-hidden="true" />
                              {analysis.video_size_mb.toFixed(1)} MB
                            </Badge>
                          )}
                        </div>
                      )}

                      <div className="ml-12 flex items-center justify-between gap-3">
                        <Button
                          variant="ghost"
                          size="xs"
                          className="text-muted-foreground hover:text-error hover:bg-error-surface"
                          onClick={() => handleEliminar(analysis.id, friendlyTitle)}
                        >
                          <Trash2 aria-hidden="true" />
                          {t('audio.delete')}
                        </Button>

                        <div className="flex items-center gap-2">
                          {analysis.estado === 'completed' && (
                            <>
                              <Button
                                className="min-w-[140px]"
                                onClick={() => navigate({ to: `/audio/${analysis.id}` })}
                                aria-label={t('audio.viewAnalysis')}
                              >
                                <Eye aria-hidden="true" />
                                {t('audio.viewAnalysis')}
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => navigate({ to: `/audio/${analysis.id}` })}
                              >
                                <FileText aria-hidden="true" />
                                {t('audio.transcription')}
                              </Button>
                              <Button onClick={() => navigate({ to: `/audio/${analysis.id}` })}>
                                <MessageSquare aria-hidden="true" />
                                {t('audio.askAi')}
                              </Button>
                            </>
                          )}

                          {isProc && (
                            <div className="flex items-center gap-2 rounded-lg border border-warning-border bg-warning-surface px-3.5 py-2">
                              <Loader2 className="h-3.5 w-3.5 animate-spin text-warning" aria-hidden="true" />
                              <div className="text-xs">
                                <p className="font-semibold text-warning">
                                  {t('operational.processing')}
                                </p>
                                <p className="text-muted-foreground">
                                  {analysis.current_phase || t('audio.statusTranscribing')}
                                </p>
                              </div>
                            </div>
                          )}

                          {analysis.estado === 'cancelled' && (
                            <div className="flex items-center gap-2 rounded-lg border border-border bg-muted px-3.5 py-2">
                              <Ban className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                              <span className="text-xs font-medium text-muted-foreground">
                                {t('audio.cancelled')}
                              </span>
                            </div>
                          )}

                          {analysis.estado === 'error' && (
                            <>
                              <div className="flex items-center gap-2 rounded-lg border border-error-border bg-error-surface px-3.5 py-2">
                                <div className="text-xs">
                                  <p className="font-semibold text-error">{t('audio.statusError')}</p>
                                  <p className="max-w-[200px] truncate text-muted-foreground">
                                    {analysis.error_message || t('audio.errorUnknown')}
                                  </p>
                                </div>
                              </div>
                              <Button
                                variant="secondary"
                                size="sm"
                                className="border-warning-border bg-warning-surface text-warning"
                                onClick={() => handleReprocesar(analysis.id)}
                              >
                                <RotateCcw aria-hidden="true" />
                                {t('audio.reprocess')}
                              </Button>
                            </>
                          )}
                        </div>
                      </div>

                      {analysis.created_at && (
                        <div className="ml-12 mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-3 text-[11px] text-muted-foreground">
                          <span className="flex items-center gap-1.5">
                            <Clock size={12} aria-hidden="true" />
                            {t('audio.created')}: {formatDate(analysis.created_at)}
                          </span>
                          {analysis.completed_at && (
                            <span className="flex items-center gap-1.5">
                              <Clock size={12} aria-hidden="true" />
                              {t('audio.completedAt')}: {formatDate(analysis.completed_at)}
                            </span>
                          )}
                          {analysis.tiempo_procesamiento_segundos > 0 && (
                            <span className="flex items-center gap-1.5">
                              <Timer size={12} aria-hidden="true" />
                              {t('audio.time')}:{' '}
                              {audioAnalysisService.formatDuration(
                                analysis.tiempo_procesamiento_segundos,
                              )}
                            </span>
                          )}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </motion.article>
              );
            })}
          </AnimatePresence>
        </div>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        onConfirm={confirmEliminar}
        title={t('audio.deleteTitle')}
        description={t('audio.deleteDescription', { title: deleteTarget?.title ?? '' })}
        confirmText={t('common.delete')}
        loading={deleting}
      />
    </PageContainer>
  );
}

function LoadingAnalyses({ label }: { label: string }) {
  return (
    <div className="flex min-h-40 w-full flex-col items-center justify-center gap-3 py-10">
      <div className="relative inline-block">
        <div className="h-14 w-14 animate-spin rounded-full border-4 border-border border-t-primary" />
        <Headphones
          className="absolute left-1/2 top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2 text-primary"
          aria-hidden="true"
        />
      </div>
      <p className="text-sm font-medium text-muted-foreground">{label}</p>
    </div>
  );
}
