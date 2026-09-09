import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import {
  audioAnalysisService,
  AudioAnalysis,
  AudioSegment,
  AudioQueryResult,
} from '../services/audioAnalysisService';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowLeft,
  Headphones,
  Loader2,
  CheckCircle,
  Clock,
  FileText,
  MessageSquare,
  RotateCcw,
  AlertCircle,
  Sparkles,
  Play,
  BarChart3,
  HardDrive,
  Zap,
  Radio,
} from 'lucide-react';
import { ChatTab } from '../components/audio-detail/ChatTab';
import { TranscriptionTab } from '../components/audio-detail/TranscriptionTab';
import { SummaryTab } from '../components/audio-detail/SummaryTab';

interface ChatMessage {
  id: string;
  type: 'user' | 'assistant';
  question?: string;
  result?: AudioQueryResult;
  timestamp: Date;
}

export default function AudioAnalysisDetail() {
  const { analysisId } = useParams({ strict: false });
  const navigate = useNavigate();

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
  const [searchResults, setSearchResults] = useState<(AudioSegment & { timestamp_formatted: string })[]>([]);
  const [searching, setSearching] = useState(false);

  // Polling for processing status
  const [polling, setPolling] = useState(false);
  const [streamConnected, setStreamConnected] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    if (analysisId) loadAnalysis();
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
              toast.success('Transcripción completada. ¡Ya puedes hacer consultas!');
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
              toast.success('Transcripción completada. ¡Ya puedes hacer consultas!');
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
  }, [polling, analysis?.estado, analysisId]);

  const loadAnalysis = async () => {
    try {
      setLoading(true);
      const res = await audioAnalysisService.obtenerAnalisis(analysisId!);
      setAnalysis(res.analysis);
    } catch (error: any) {
      toast.error(error.response?.data?.error || 'Error cargando análisis');
    } finally {
      setLoading(false);
    }
  };

  const loadSegments = async (reset = false) => {
    try {
      setLoadingSegments(true);
      const cursor = reset ? undefined : (segmentsCursor || undefined);
      const res = await audioAnalysisService.obtenerSegmentos(analysisId!, 1, 50, cursor);

      if (reset) {
        setSegments(res.segments);
      } else {
        setSegments(prev => [...prev, ...res.segments]);
      }

      setTotalSegments(res.total);
      setSegmentsCursor(res.next_cursor || null);
    } catch (error: any) {
      toast.error('Error cargando segmentos');
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
    setChatMessages(prev => [...prev, userMsg]);
    setQuerying(true);

    try {
      const result = await audioAnalysisService.consultarContenido(analysisId!, question);

      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        type: 'assistant',
        result,
        timestamp: new Date(),
      };
      setChatMessages(prev => [...prev, assistantMsg]);
    } catch (error: any) {
      toast.error(error.response?.data?.error || 'Error procesando consulta');
      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        type: 'assistant',
        result: {
          success: false,
          respuesta: 'Error al procesar la consulta. Inténtalo de nuevo.',
          momentos_relevantes: [],
          encontrado: false,
          confianza: 'baja',
          segments_found: 0,
          error: error.response?.data?.error || error.message,
        },
        timestamp: new Date(),
      };
      setChatMessages(prev => [...prev, errorMsg]);
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
        toast.info('No se encontraron coincidencias');
      }
    } catch (error: any) {
      toast.error('Error en la búsqueda');
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
      toast.info('Reproducción inline no disponible para este archivo.');
      return;
    }

    try {
      audioRef.current.currentTime = Math.max(0, seconds);
      void audioRef.current.play();
    } catch {
      toast.warning('No se pudo iniciar la reproducción en este momento.');
    }
  };

  const copyTranscription = () => {
    if (analysis?.full_transcription) {
      navigator.clipboard.writeText(analysis.full_transcription);
      toast.success('Transcripción copiada al portapapeles');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-gray-50 to-stone-100 flex items-center justify-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center"
        >
          <div className="relative inline-block mb-5">
            <div className="w-16 h-16 rounded-full border-4 border-gray-100 border-t-tivit-red animate-spin" />
            <Headphones className="w-6 h-6 text-tivit-red absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
          </div>
          <p className="text-gray-500 font-medium">Cargando análisis...</p>
        </motion.div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-gray-50 to-stone-100 flex items-center justify-center">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center bg-white rounded-2xl p-10 shadow-sm border border-gray-100"
        >
          <AlertCircle className="w-14 h-14 text-red-400 mx-auto mb-4" />
          <p className="text-gray-700 font-semibold text-lg mb-1">Análisis no encontrado</p>
          <p className="text-gray-500 text-sm mb-5">El análisis que buscas no existe o fue eliminado.</p>
          <button
            onClick={() => navigate({ to: '/audio' })}
            className="px-5 py-2.5 bg-gradient-to-r from-tivit-red to-rose-600 text-white rounded-xl font-medium shadow-sm"
          >
            Volver
          </button>
        </motion.div>
      </div>
    );
  }

  const isCompleted = analysis.estado === 'completed';
  const isProcessing = audioAnalysisService.isProcessing(analysis.estado);

  const tabs = [
    { key: 'query' as const, label: 'Consultas', icon: MessageSquare },
    { key: 'transcription' as const, label: 'Transcripción', icon: FileText },
    { key: 'summary' as const, label: 'Resumen IA', icon: Sparkles },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-gray-50 to-stone-100">
      {/* Decorative top bar */}
      <div className="h-1 bg-gradient-to-r from-tivit-red via-red-400 to-rose-500" />

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Back navigation */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.3 }}
          className="mb-8"
        >
          <button
            onClick={() => navigate({ to: '/audio' })}
            className="flex items-center gap-2 text-slate-500 hover:text-slate-800 transition-colors group"
          >
            <ArrowLeft className="w-5 h-5 group-hover:-translate-x-1 transition-transform" />
            <span className="text-[15px] font-semibold">Volver a Análisis de Audio</span>
          </button>
        </motion.div>

        {/* Info Card */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="relative bg-white rounded-3xl border border-slate-100 shadow-sm p-8 lg:p-10 mb-8 overflow-hidden"
        >
          {/* Soft Glow Background */}
          <div className="absolute top-0 right-0 w-96 h-96 rounded-full blur-3xl -mr-20 -mt-20 opacity-30 pointer-events-none bg-blue-50" />
          
          <div className="relative z-10 flex flex-col md:flex-row md:items-start justify-between gap-6">
            <div className="flex items-start gap-5">
              <div className="relative flex-shrink-0">
                <div className={`w-16 h-16 rounded-[20px] flex items-center justify-center shadow-sm ${
                  isCompleted
                    ? 'bg-emerald-50 border border-emerald-100 text-emerald-600'
                    : isProcessing
                    ? 'bg-amber-50 border border-amber-100 text-amber-600'
                    : 'bg-rose-50 border border-rose-100 text-rose-600'
                }`}>
                  <Headphones className="w-8 h-8" strokeWidth={2} />
                </div>
                {isProcessing && (
                  <span className="absolute -bottom-1 -right-1 w-5 h-5 bg-amber-400 rounded-full border-2 border-white flex items-center justify-center">
                    <Loader2 className="w-3 h-3 text-white animate-spin" />
                  </span>
                )}
              </div>
              <div>
                <h1 className="text-2xl lg:text-3xl font-bold text-slate-800 tracking-tight">
                  {analysis.titulo || analysis.video_filename}
                </h1>
                {analysis.descripcion && (
                  <p className="text-slate-500 text-[15px] mt-1.5">{analysis.descripcion}</p>
                )}
                <div className="flex flex-wrap items-center gap-3 mt-4">
                  {analysis.video_duration > 0 && (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-100 bg-slate-50 text-slate-600 text-[12px] font-bold">
                      <Clock className="w-3.5 h-3.5" />
                      {audioAnalysisService.formatDuration(analysis.video_duration)}
                    </span>
                  )}
                  {analysis.video_size_mb > 0 && (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-100 bg-slate-50 text-slate-600 text-[12px] font-bold">
                      <HardDrive className="w-3.5 h-3.5" />
                      {analysis.video_size_mb.toFixed(1)} MB
                    </span>
                  )}
                  {analysis.total_segments > 0 && (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-100 bg-slate-50 text-slate-600 text-[12px] font-bold">
                      <BarChart3 className="w-3.5 h-3.5" />
                      {analysis.total_segments} segmentos
                    </span>
                  )}
                  {analysis.average_confidence > 0 && (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-emerald-100/60 bg-emerald-50 text-emerald-700 text-[12px] font-bold">
                      <Zap className="w-3.5 h-3.5" />
                      {(analysis.average_confidence * 100).toFixed(0)}% confianza
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 mt-4 md:mt-0 flex-shrink-0">
              {isCompleted && (
                <button
                  onClick={async () => {
                    try {
                      await audioAnalysisService.reprocesarAnalisis(analysisId!);
                      toast.success('Reprocesamiento iniciado con nuevo pipeline STT V2');
                      loadAnalysis();
                    } catch (e) {
                      toast.error('Error al reprocesar');
                    }
                  }}
                  className="px-5 py-2.5 bg-white border border-slate-200/60 text-slate-600 rounded-full text-[13px] font-semibold flex items-center gap-2 hover:bg-slate-50 shadow-sm transition-colors"
                >
                  <RotateCcw className="w-4 h-4" />
                  Reprocesar
                </button>
              )}
              <span className={`px-5 py-2.5 rounded-full text-[12px] font-bold uppercase tracking-wide flex items-center gap-2 border shadow-sm ${
                isCompleted ? 'bg-emerald-50 text-emerald-700 border-emerald-200/60' :
                isProcessing ? 'bg-amber-50 text-amber-700 border-amber-200/60' :
                analysis.estado === 'error' ? 'bg-rose-50 text-rose-700 border-rose-200/60' :
                'bg-slate-50 text-slate-600 border-slate-200/60'
              }`}>
                {isProcessing && <Loader2 className="w-4 h-4 animate-spin" />}
                {isCompleted && <CheckCircle className="w-4 h-4" />}
                {audioAnalysisService.getEstadoLabel(analysis.estado)}
              </span>
            </div>
          </div>

          {/* Progress bar */}
          {isProcessing && analysis.progress > 0 && (
            <div className="mt-5">
              <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                <span className="font-medium">{analysis.current_phase || 'Procesando...'}</span>
                <span className="font-semibold text-gray-700">{Math.round(analysis.progress)}%</span>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                <motion.div
                  className="h-full bg-gradient-to-r from-amber-400 to-tivit-red rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${analysis.progress}%` }}
                  transition={{ duration: 0.5, ease: 'easeOut' }}
                />
              </div>
            </div>
          )}

          {/* Error */}
          {analysis.estado === 'error' && (
            <div className="mt-5 p-4 bg-red-50 border border-red-200 rounded-xl flex items-center justify-between">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                <div className="text-sm">
                  <p className="font-semibold text-red-800">Error en el procesamiento</p>
                  <p className="text-red-600 mt-0.5">{analysis.error_message}</p>
                </div>
              </div>
              <button
                onClick={async () => {
                  try {
                    await audioAnalysisService.reprocesarAnalisis(analysisId!);
                    toast.success('Reprocesamiento iniciado');
                    loadAnalysis();
                  } catch (e) {
                    toast.error('Error al reprocesar');
                  }
                }}
                className="px-4 py-2 bg-orange-500 text-white rounded-xl text-sm font-medium flex items-center gap-1.5 hover:bg-orange-600 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reprocesar
              </button>
            </div>
          )}
        </motion.div>

        {/* Tabs (only when completed) */}
        {isCompleted && (
          <>
            {/* Tab selector */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="flex gap-2 mb-8 bg-slate-100/60 p-1.5 rounded-full shadow-inner border border-slate-200/60"
            >
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.key;
                return (
                  <button
                    key={tab.key}
                    onClick={() => {
                      setActiveTab(tab.key);
                      if (tab.key === 'transcription' && segments.length === 0) loadSegments(true);
                    }}
                    className={`relative flex-1 flex items-center justify-center gap-2 py-3 rounded-full font-semibold text-[15px] transition-all duration-300 ${
                      isActive
                        ? 'text-white'
                        : 'text-slate-500 hover:text-slate-800 hover:bg-white border hover:border-slate-200/60 shadow-sm border-transparent'
                    }`}
                  >
                    {isActive && (
                      <motion.div
                        layoutId="activeTab"
                        className="absolute inset-0 bg-slate-800 rounded-full shadow-md"
                        transition={{ type: 'spring', bounce: 0.2, duration: 0.5 }}
                      />
                    )}
                    <span className="relative flex items-center gap-2">
                      <Icon className="w-4 h-4" />
                      {tab.label}
                    </span>
                  </button>
                );
              })}
            </motion.div>

            {/* Tab content */}
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
              >
                {activeTab === 'query' && (
                  <ChatTab
                    chatMessages={chatMessages}
                    querying={querying}
                    queryInput={queryInput}
                    setQueryInput={setQueryInput}
                    onQuery={handleQuery}
                  />
                )}

                {activeTab === 'transcription' && (
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
                )}

                {activeTab === 'summary' && (
                  <SummaryTab analysis={analysis} />
                )}
              </motion.div>
            </AnimatePresence>
          </>
        )}

        {/* Audio player bottom bar */}
        {isCompleted && getPlayableAudioUrl() && (
          <motion.div
            initial={{ y: 100, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.5, type: 'spring', bounce: 0.2 }}
            className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 w-[min(900px,calc(100%-2rem))]"
          >
            <div className="bg-white/95 backdrop-blur-xl border border-gray-200 rounded-2xl shadow-xl p-4">
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-2.5 font-medium">
                <Radio className="w-3.5 h-3.5 text-tivit-red" />
                Reproductor del análisis
              </div>
              <audio ref={audioRef} controls preload="none" className="w-full" src={getPlayableAudioUrl() || undefined} />
            </div>
          </motion.div>
        )}

        {/* Processing state */}
        {isProcessing && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-sm border border-gray-100 p-10 text-center"
          >
            <div className="relative inline-block mb-5">
              <div className="w-20 h-20 rounded-full border-4 border-gray-100 border-t-tivit-red animate-spin" />
              <Headphones className="w-8 h-8 text-tivit-red absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
            </div>
            <h3 className="text-xl font-bold text-gray-800 mb-2">
              Procesando audio...
            </h3>
            <p className="text-gray-500 mb-5 max-w-md mx-auto">
              {analysis.current_phase || 'Extrayendo y transcribiendo el audio del video'}
            </p>
            {analysis.progress > 0 && (
              <div className="max-w-md mx-auto">
                <div className="w-full bg-gray-100 rounded-full h-3 overflow-hidden">
                  <motion.div
                    className="h-full bg-gradient-to-r from-amber-400 to-tivit-red rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${analysis.progress}%` }}
                    transition={{ duration: 0.5, ease: 'easeOut' }}
                  />
                </div>
                <p className="text-sm text-gray-500 mt-2 font-medium">{Math.round(analysis.progress)}% completado</p>
              </div>
            )}
            <p className="text-xs text-gray-400 mt-6 flex items-center justify-center gap-1.5">
              {streamConnected ? (
                <>
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  Estado en tiempo real conectado
                </>
              ) : (
                <>
                  <span className="w-2 h-2 rounded-full bg-gray-300" />
                  Actualización automática activa
                </>
              )}
            </p>
          </motion.div>
        )}
      </div>
    </div>
  );
}
