import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import {
  audioAnalysisService,
  AudioAnalysis,
  AudioSegment,
  AudioQueryResult,
} from '../services/audioAnalysisService';
import { toast } from 'sonner';
import {
  ArrowLeft,
  Headphones,
  Clock,
  FileText,
  MessageSquare,
  RotateCcw,
  AlertCircle,
  Sparkles,
  BarChart3,
  HardDrive,
  Zap,
  Radio,
} from 'lucide-react';
import { ChatTab } from '../components/audio-detail/ChatTab';
import { TranscriptionTab } from '../components/audio-detail/TranscriptionTab';
import { SummaryTab } from '../components/audio-detail/SummaryTab';
import { PageContainer } from '../components/ui/page-container';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { Progress } from '../components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { LoadingState } from '../components/ui/loading-state';
import { ErrorState } from '../components/ui/error-state';
import { StatusBadge, type AppStatus } from '../components/ui/status-badge';
import { useTranslation } from '../i18n';

interface ChatMessage {
  id: string;
  type: 'user' | 'assistant';
  question?: string;
  result?: AudioQueryResult;
  timestamp: Date;
}

const statusFromEstado = (estado: string): AppStatus => {
  if (estado === 'completed') return 'completed';
  if (estado === 'error') return 'failed';
  if (estado === 'cancelled') return 'cancelled';
  return 'processing';
};

export default function AudioAnalysisDetail() {
  const { analysisId } = useParams({ strict: false });
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [analysis, setAnalysis] = useState<AudioAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'query' | 'transcription' | 'summary'>('query');

  // Chat / Query state
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [queryInput, setQueryInput] = useState('');
  const [querying, setQuerying] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Transcription state
  const [segments, setSegments] = useState<AudioSegment[]>([]);
  const [segmentsCursor, setSegmentsCursor] = useState<string | null>(null);
  const [totalSegments, setTotalSegments] = useState(0);
  const [loadingSegments, setLoadingSegments] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<
    (AudioSegment & { timestamp_formatted: string })[]
  >([]);
  const [searching, setSearching] = useState(false);

  // Polling for processing status
  const [polling, setPolling] = useState(false);
  const [streamConnected, setStreamConnected] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    if (analysisId) loadAnalysis();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  // Auto-refresh while processing (SSE first, polling fallback)
  useEffect(() => {
    if (analysis && audioAnalysisService.isProcessing(analysis.estado)) {
      setPolling(false);
      setStreamConnected(true);

      const streamUrl = audioAnalysisService.getEstadoStreamUrl(analysisId!);
      const source = new EventSource(streamUrl);

      source.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          setAnalysis((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              estado: payload.status,
              progress: payload.progress,
              current_phase: payload.current_phase,
              error_message: payload.error_message,
            };
          });

          if (!audioAnalysisService.isProcessing(payload.status)) {
            source.close();
            setStreamConnected(false);
            if (payload.status === 'completed') {
              toast.success(t('audioDetail.completedToast'));
            }
          }
        } catch {
          // ignore malformed event payload
        }
      };

      source.onerror = () => {
        source.close();
        setStreamConnected(false);
        setPolling(true);
      };

      return () => {
        source.close();
        setStreamConnected(false);
      };
    }

    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysis?.estado, analysisId]);

  useEffect(() => {
    if (polling && analysis && audioAnalysisService.isProcessing(analysis.estado)) {
      const interval = setInterval(async () => {
        try {
          const res = await audioAnalysisService.obtenerAnalisis(analysisId!);
          setAnalysis(res.analysis);
          if (!audioAnalysisService.isProcessing(res.analysis.estado)) {
            setPolling(false);
            if (res.analysis.estado === 'completed') {
              toast.success(t('audioDetail.completedToast'));
            }
          }
        } catch {
          // silently continue polling fallback
        }
      }, 5000);
      return () => clearInterval(interval);
    } else {
      setPolling(false);
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [polling, analysis?.estado, analysisId]);

  const loadAnalysis = async () => {
    try {
      setLoading(true);
      const res = await audioAnalysisService.obtenerAnalisis(analysisId!);
      setAnalysis(res.analysis);
    } catch (error) {
      toast.error(getErrorText(error, t('audioDetail.loadError')));
    } finally {
      setLoading(false);
    }
  };

  const loadSegments = async (reset = false) => {
    try {
      setLoadingSegments(true);
      const cursor = reset ? undefined : segmentsCursor || undefined;
      const res = await audioAnalysisService.obtenerSegmentos(analysisId!, 1, 50, cursor);

      if (reset) {
        setSegments(res.segments);
      } else {
        setSegments((prev) => [...prev, ...res.segments]);
      }

      setTotalSegments(res.total);
      setSegmentsCursor(res.next_cursor || null);
    } catch {
      toast.error(t('audioDetail.segmentsError'));
    } finally {
      setLoadingSegments(false);
    }
  };

  const handleQuery = async () => {
    if (!queryInput.trim() || querying) return;

    const question = queryInput.trim();
    setQueryInput('');

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      type: 'user',
      question,
      timestamp: new Date(),
    };
    setChatMessages((prev) => [...prev, userMsg]);
    setQuerying(true);

    try {
      const result = await audioAnalysisService.consultarContenido(analysisId!, question);

      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        type: 'assistant',
        result,
        timestamp: new Date(),
      };
      setChatMessages((prev) => [...prev, assistantMsg]);
    } catch (error) {
      toast.error(getErrorText(error, t('audioDetail.queryError')));
      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        type: 'assistant',
        result: {
          success: false,
          respuesta: t('audioDetail.queryErrorMessage'),
          momentos_relevantes: [],
          encontrado: false,
          confianza: 'baja',
          segments_found: 0,
          error: getErrorText(error, ''),
        },
        timestamp: new Date(),
      };
      setChatMessages((prev) => [...prev, errorMsg]);
    } finally {
      setQuerying(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    try {
      setSearching(true);
      const res = await audioAnalysisService.buscarEnTranscripcion(analysisId!, searchQuery);
      setSearchResults(res.results);
      if (res.total === 0) {
        toast.info(t('audioDetail.searchNoResults'));
      }
    } catch {
      toast.error(t('audioDetail.searchError'));
    } finally {
      setSearching(false);
    }
  };

  const getPlayableAudioUrl = (): string | null => {
    if (analysis?.audio_url?.startsWith('http')) return analysis.audio_url;
    if (analysis?.video_url?.startsWith('http')) return analysis.video_url;
    return null;
  };

  const handleSeekTo = (seconds: number) => {
    const playableUrl = getPlayableAudioUrl();
    if (!playableUrl || !audioRef.current) {
      toast.info(t('audioDetail.playbackUnavailable'));
      return;
    }

    try {
      audioRef.current.currentTime = Math.max(0, seconds);
      void audioRef.current.play();
    } catch {
      toast.warning(t('audioDetail.playbackFailed'));
    }
  };

  const copyTranscription = () => {
    if (analysis?.full_transcription) {
      const text = analysis.full_transcription;
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand('copy');
      document.body.removeChild(textarea);
      toast[copied ? 'success' : 'error'](
        copied ? t('audioDetail.copySuccess') : t('audioDetail.copyFailed'),
      );
    }
  };

  const handleReprocess = async () => {
    try {
      await audioAnalysisService.reprocesarAnalisis(analysisId!);
      toast.success(t('audioDetail.reprocessStarted'));
      loadAnalysis();
    } catch {
      toast.error(t('audioDetail.reprocessFailed'));
    }
  };

  if (loading) {
    return <LoadingState label={t('audioDetail.loading')} className="min-h-[60vh]" />;
  }

  if (!analysis) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <ErrorState
          title={t('audioDetail.notFoundTitle')}
          description={t('audioDetail.notFoundDescription')}
          onRetry={loadAnalysis}
        />
        <div className="mt-4">
          <Button variant="outline" onClick={() => navigate({ to: '/audio' })}>
            {t('common.back')}
          </Button>
        </div>
      </div>
    );
  }

  const isCompleted = analysis.estado === 'completed';
  const isProcessing = audioAnalysisService.isProcessing(analysis.estado);
  const playableUrl = getPlayableAudioUrl();

  return (
    <PageContainer className="max-w-6xl pb-32">
      <Button
        variant="ghost"
        onClick={() => navigate({ to: '/audio' })}
        className="px-0 hover:bg-transparent"
      >
        <ArrowLeft aria-hidden="true" />
        {t('audioDetail.back')}
      </Button>

      {/* Info Card */}
      <Card variant="elevated" className="p-8 lg:p-10">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-start">
          <div className="flex items-start gap-5">
            <div className="relative shrink-0">
              <div
                className={`flex h-16 w-16 items-center justify-center rounded-2xl border ${
                  isCompleted
                    ? 'border-success-border bg-success-surface text-success'
                    : isProcessing
                      ? 'border-warning-border bg-warning-surface text-warning'
                      : 'border-error-border bg-error-surface text-error'
                }`}
              >
                <Headphones className="h-8 w-8" aria-hidden="true" />
              </div>
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-foreground lg:text-3xl">
                {analysis.titulo || analysis.video_filename}
              </h1>
              {analysis.descripcion && (
                <p className="mt-1.5 text-[15px] text-muted-foreground">{analysis.descripcion}</p>
              )}
              <div className="mt-4 flex flex-wrap items-center gap-2">
                {analysis.video_duration > 0 && (
                  <Badge variant="muted" className="gap-1.5 px-3 py-1.5">
                    <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                    {audioAnalysisService.formatDuration(analysis.video_duration)}
                  </Badge>
                )}
                {analysis.video_size_mb > 0 && (
                  <Badge variant="muted" className="gap-1.5 px-3 py-1.5">
                    <HardDrive className="h-3.5 w-3.5" aria-hidden="true" />
                    {analysis.video_size_mb.toFixed(1)} MB
                  </Badge>
                )}
                {analysis.total_segments > 0 && (
                  <Badge variant="muted" className="gap-1.5 px-3 py-1.5">
                    <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('audioDetail.segments', { count: analysis.total_segments })}
                  </Badge>
                )}
                {analysis.average_confidence > 0 && (
                  <Badge variant="success" className="gap-1.5 px-3 py-1.5">
                    <Zap className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('audioDetail.confidence', {
                      percent: (analysis.average_confidence * 100).toFixed(0),
                    })}
                  </Badge>
                )}
              </div>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-3">
            {isCompleted && (
              <Button variant="outline" onClick={handleReprocess}>
                <RotateCcw aria-hidden="true" />
                {t('audioDetail.reprocess')}
              </Button>
            )}
            <StatusBadge
              status={statusFromEstado(analysis.estado)}
              label={audioAnalysisService.getEstadoLabel(analysis.estado)}
            />
          </div>
        </div>

        {/* Progress bar */}
        {isProcessing && analysis.progress > 0 && (
          <div className="mt-5">
            <div className="mb-1.5 flex justify-between text-xs text-muted-foreground">
              <span className="font-medium">
                {analysis.current_phase || t('audioDetail.processing')}
              </span>
              <span className="font-semibold text-foreground">
                {Math.round(analysis.progress)}%
              </span>
            </div>
            <Progress
              value={analysis.progress}
              aria-label={t('audioDetail.processing')}
              aria-valuetext={`${Math.round(analysis.progress)}%`}
            />
          </div>
        )}

        {/* Error */}
        {analysis.estado === 'error' && (
          <Alert variant="error" className="mt-5 items-center">
            <AlertCircle aria-hidden="true" />
            <div className="flex-1">
              <AlertTitle>{t('audioDetail.errorTitle')}</AlertTitle>
              <AlertDescription>{analysis.error_message}</AlertDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleReprocess}
              className="text-error hover:bg-error-surface"
            >
              <RotateCcw aria-hidden="true" />
              {t('audioDetail.reprocess')}
            </Button>
          </Alert>
        )}
      </Card>

      {/* Tabs (only when completed) */}
      {isCompleted && (
        <Tabs
          value={activeTab}
          onValueChange={(value) => {
            const next = value as typeof activeTab;
            setActiveTab(next);
            if (next === 'transcription' && segments.length === 0) loadSegments(true);
          }}
          className="space-y-6"
        >
          <TabsList className="grid h-auto w-full grid-cols-3 rounded-lg p-1.5">
            <TabsTrigger value="query" className="gap-2 py-2.5">
              <MessageSquare aria-hidden="true" />
              {t('audioDetail.tabQueries')}
            </TabsTrigger>
            <TabsTrigger value="transcription" className="gap-2 py-2.5">
              <FileText aria-hidden="true" />
              {t('audioDetail.tabTranscription')}
            </TabsTrigger>
            <TabsTrigger value="summary" className="gap-2 py-2.5">
              <Sparkles aria-hidden="true" />
              {t('audioDetail.tabSummary')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="query" className="mt-0">
            <ChatTab
              chatMessages={chatMessages}
              querying={querying}
              queryInput={queryInput}
              setQueryInput={setQueryInput}
              onQuery={handleQuery}
            />
          </TabsContent>

          <TabsContent value="transcription" className="mt-0">
            <TranscriptionTab
              analysis={analysis}
              segments={segments}
              totalSegments={totalSegments}
              segmentsCursor={segmentsCursor}
              loadingSegments={loadingSegments}
              onLoadSegments={loadSegments}
              searchQuery={searchQuery}
              setSearchQuery={setSearchQuery}
              searching={searching}
              onSearch={handleSearch}
              searchResults={searchResults}
              clearSearch={() => {
                setSearchResults([]);
                setSearchQuery('');
              }}
              onCopyTranscription={copyTranscription}
              onSeekTo={handleSeekTo}
            />
          </TabsContent>

          <TabsContent value="summary" className="mt-0">
            <SummaryTab analysis={analysis} />
          </TabsContent>
        </Tabs>
      )}

      {/* Processing state */}
      {isProcessing && (
        <Card variant="elevated" className="p-10 text-center">
          <div className="relative mb-5 inline-block">
            <div className="h-20 w-20 rounded-full border-4 border-muted border-t-primary animate-spin" />
            <Headphones
              className="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-primary"
              aria-hidden="true"
            />
          </div>
          <h3 className="mb-2 text-xl font-bold text-foreground">
            {t('audioDetail.processingTitle')}
          </h3>
          <p className="mx-auto mb-5 max-w-md text-muted-foreground">
            {analysis.current_phase || t('audioDetail.processingDefaultPhase')}
          </p>
          {analysis.progress > 0 && (
            <div
              className="mx-auto max-w-md"
              aria-live="polite"
              aria-label={t('audioDetail.processing')}
            >
              <Progress value={analysis.progress} />
              <p className="mt-2 text-sm font-medium text-muted-foreground">
                {t('audioDetail.progressCompleted', { percent: Math.round(analysis.progress) })}
              </p>
            </div>
          )}
          <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
            <span
              className={`h-2 w-2 rounded-full ${
                streamConnected ? 'bg-success animate-pulse' : 'bg-gray-300'
              }`}
              aria-hidden="true"
            />
            {streamConnected ? t('audioDetail.liveConnected') : t('audioDetail.autoUpdate')}
          </p>
        </Card>
      )}

      {/* Audio player bottom bar */}
      {isCompleted && playableUrl && (
        <div className="fixed bottom-4 left-1/2 z-40 w-[min(900px,calc(100%-2rem))] -translate-x-1/2">
          <Card variant="elevated" className="border-border/80 bg-card/95 p-4 backdrop-blur-xl">
            <div className="mb-2.5 flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <Radio className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
              {t('audioDetail.playerTitle')}
            </div>
            <audio ref={audioRef} controls preload="none" className="w-full" src={playableUrl} />
          </Card>
        </div>
      )}
    </PageContainer>
  );
}

function getErrorText(error: unknown, fallback: string): string {
  if (error && typeof error === 'object') {
    const withResponse = error as {
      response?: { data?: { error?: string } };
      message?: string;
    };
    return withResponse.response?.data?.error || withResponse.message || fallback;
  }
  return fallback;
}
