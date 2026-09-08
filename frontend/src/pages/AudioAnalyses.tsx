import { useState, useEffect, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { audioAnalysisService, AudioAnalysis } from '../services/audioAnalysisService';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus,
  Clock,
  FileText,
  Trash2,
  RefreshCw,
  Loader2,
  CheckCircle,
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
} from 'lucide-react';
import { EmptyStateCard } from '../components/EmptyStateCard';

export default function AudioAnalyses() {
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
  }, []);

  // Auto-refresh cada 10s si hay análisis en curso
  useEffect(() => {
    const hasProcessing = analyses.some(a => audioAnalysisService.isProcessing(a.estado));
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
        nextAnalyses.forEach(a => {
          const prev = prevStatusRef.current[a.id];
          if (a.estado === 'completed' && prev && prev !== 'completed') {
            toast.success(`Transcripción completada: ${a.titulo || a.video_filename}`);
          }
        });
      }

      prevStatusRef.current = Object.fromEntries(nextAnalyses.map(a => [a.id, a.estado]));
      hasLoadedOnceRef.current = true;
      setAnalyses(nextAnalyses);
    } catch (error: any) {
      toast.error(error.response?.data?.error || 'Error cargando análisis');
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
      toast.success('Análisis eliminado');
      setDeleteTarget(null);
      cargarAnalisis();
    } catch (error: any) {
      toast.error(error.response?.data?.error || 'Error eliminando análisis');
    } finally {
      setDeleting(false);
    }
  };

  const handleReprocesar = async (analysisId: string) => {
    try {
      await audioAnalysisService.reprocesarAnalisis(analysisId);
      toast.success('Análisis reencolado para reprocesamiento');
      cargarAnalisis();
    } catch (error: any) {
      toast.error(error.response?.data?.error || 'Error al reprocesar');
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
    if (!isoDate) return 'Sin fecha';
    const date = new Date(isoDate);
    if (Number.isNaN(date.getTime())) return 'Sin fecha';
    return dateFormatter.format(date);
  };

  const getFriendlyTitle = (analysis: AudioAnalysis): string => {
    const raw = (analysis.titulo || analysis.video_filename || '').trim();
    if (!raw) return 'Análisis sin título';

    let cleaned = raw
      .replace(/\.[a-z0-9]{2,4}$/i, '')
      .replace(/[_-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    if (/^whatsapp ptt/i.test(cleaned)) {
      cleaned = cleaned.replace(/^whatsapp ptt\s*/i, 'Audio de WhatsApp ');
    }

    return cleaned || 'Análisis sin título';
  };

  const getContextSnippet = (analysis: AudioAnalysis): string => {
    const snippet = (analysis.full_transcription || analysis.descripcion || '').trim();
    return snippet.length > 0 ? snippet : 'Sin contexto adicional disponible';
  };

  const readyCount = analyses.filter(a => a.estado === 'completed').length;
  const processingCount = analyses.filter(a => audioAnalysisService.isProcessing(a.estado)).length;
  const isEmpty = !loading && analyses.length === 0;

  const getStatusConfig = (estado: string) => {
    const configs: Record<string, { bg: string; text: string; border: string; dot: string }> = {
      pending: { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200/60', dot: 'bg-amber-400' },
      uploading: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200/60', dot: 'bg-blue-400' },
      extracting_audio: { bg: 'bg-sky-50', text: 'text-sky-700', border: 'border-sky-200/60', dot: 'bg-sky-400' },
      audio_ready: { bg: 'bg-cyan-50', text: 'text-cyan-700', border: 'border-cyan-200/60', dot: 'bg-cyan-400' },
      transcribing: { bg: 'bg-indigo-50', text: 'text-indigo-700', border: 'border-indigo-200/60', dot: 'bg-indigo-400' },
      transcribed: { bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-200/60', dot: 'bg-purple-400' },
      indexing: { bg: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200/60', dot: 'bg-violet-400' },
      completed: { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200/60', dot: 'bg-emerald-400' },
      cancelled: { bg: 'bg-slate-50', text: 'text-slate-600', border: 'border-slate-200/60', dot: 'bg-slate-400' },
      error: { bg: 'bg-rose-50', text: 'text-rose-700', border: 'border-rose-200/60', dot: 'bg-rose-400' },
    };
    return configs[estado] || configs.pending;
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-gradient-to-br from-slate-50 via-slate-50/50 to-stone-50/50">
      {/* Decorative top bar */}
      <div className="h-1 bg-gradient-to-r from-red-500 via-rose-500 to-pink-500" />

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-in fade-in duration-500">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-8"
        >
          <div className="relative bg-white rounded-3xl border border-slate-100 shadow-sm p-8 overflow-hidden">
            {/* Soft Glow Background */}
            <div className="absolute top-0 right-0 w-80 h-80 rounded-full blur-3xl -mr-20 -mt-20 opacity-30 pointer-events-none bg-rose-50" />
            
            <div className="relative z-10 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
              <div className="flex items-center gap-5">
                <div className="relative">
                  <div className="w-16 h-16 rounded-[20px] bg-red-50 border border-red-100 flex items-center justify-center shadow-sm">
                    <Headphones className="w-8 h-8 text-tivit-red" strokeWidth={2} />
                  </div>
                  {processingCount > 0 && (
                    <span className="absolute -top-1 -right-1 w-5 h-5 bg-amber-400 rounded-full flex items-center justify-center text-[10px] font-bold text-white animate-pulse">
                      {processingCount}
                    </span>
                  )}
                </div>
                <div>
                  <h1 className="text-3xl font-bold text-slate-800 tracking-tight">
                    Análisis de Audio
                  </h1>
                  <p className="text-slate-500 text-[15px] mt-1">
                    Sube audio o video (máximo 2 horas), transcribimos y consulta lo que necesites saber
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                {analyses.length > 0 && (
                  <button
                    onClick={cargarAnalisis}
                    className="flex items-center gap-2 px-5 py-2.5 text-[14px] font-semibold text-slate-600 bg-white border border-slate-200/60 rounded-full hover:bg-slate-50 hover:text-slate-900 transition-all duration-300 shadow-sm"
                  >
                    <RefreshCw className="w-4 h-4" />
                    Actualizar
                  </button>
                )}
                {!isEmpty && (
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => navigate({ to: '/audio/upload' })}
                    className="group flex items-center gap-2.5 px-6 py-3 bg-red-600 text-white text-[15px] font-semibold rounded-full shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all duration-300 hover:bg-red-700"
                  >
                    <Plus className="w-5 h-5 text-white/90" />
                    Nuevo Análisis
                  </motion.button>
                )}
              </div>
            </div>

            {/* Stats bar */}
            {analyses.length > 0 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="flex flex-wrap gap-3 mt-6 pt-6 border-t border-slate-100/60 relative z-10"
              >
                <div className="flex items-center gap-2 px-4 py-2 bg-slate-50 border border-slate-100/60 rounded-full text-sm font-semibold text-slate-600">
                  <AudioWaveform className="w-4 h-4 text-slate-400" />
                  <span>Total:</span>
                  <span className="text-slate-800">{analyses.length}</span>
                </div>
                <div className="flex items-center gap-2 px-4 py-2 bg-emerald-50 border border-emerald-100/60 rounded-full text-sm font-semibold text-emerald-700">
                  <CheckCircle className="w-4 h-4 text-emerald-500" />
                  <span>Completados:</span>
                  <span>{readyCount}</span>
                </div>
                {processingCount > 0 && (
                  <div className="flex items-center gap-2 px-4 py-2 bg-amber-50 border border-amber-100/60 rounded-full text-sm font-semibold text-amber-700">
                    <Loader2 className="w-4 h-4 text-amber-500 animate-spin" />
                    <span>En proceso:</span>
                    <span>{processingCount}</span>
                  </div>
                )}
              </motion.div>
            )}
          </div>
        </motion.div>

        {/* Loading */}
        <AnimatePresence>
          {loading && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="bg-white/60 backdrop-blur-sm rounded-2xl border border-gray-100 p-16 text-center"
            >
              <div className="relative inline-block mb-5">
                <div className="w-16 h-16 rounded-full border-4 border-gray-100 border-t-tivit-red animate-spin" />
                <Headphones className="w-6 h-6 text-tivit-red absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
              </div>
              <p className="text-gray-500 font-medium">Cargando análisis...</p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Empty State */}
        {!loading && analyses.length === 0 && (
          <EmptyStateCard
            icon={<Headphones className="w-16 h-16 text-gray-400" />}
            title="No hay análisis de audio"
            description="Sube un archivo de audio o video (máximo 2 horas), transcribimos el contenido y te mostramos los momentos exactos para consultar con IA."
            primaryActionLabel="Nuevo Análisis"
            primaryActionIcon={<Plus className="w-5 h-5" />}
            onPrimaryAction={() => navigate({ to: '/audio/upload' })}
            features={[
              { icon: <Mic className="w-3.5 h-3.5 text-tivit-red" />, label: 'Transcripción completa' },
              { icon: <Timer className="w-3.5 h-3.5 text-tivit-red" />, label: 'Timestamps precisos' },
              { icon: <MessageSquare className="w-3.5 h-3.5 text-tivit-red" />, label: 'Consultas con IA' },
              { icon: <Sparkles className="w-3.5 h-3.5 text-tivit-red" />, label: 'Resumen automático' },
            ]}
          />
        )}

        {/* Lista de análisis */}
        {!loading && analyses.length > 0 && (
          <div className="grid gap-5">
            <AnimatePresence>
              {analyses.map((analysis, index) => {
                const isProc = audioAnalysisService.isProcessing(analysis.estado);
                const friendlyTitle = getFriendlyTitle(analysis);
                const contextSnippet = getContextSnippet(analysis);
                const canPlayInline = Boolean(analysis.audio_gcs_url && analysis.audio_gcs_url.startsWith('http'));
                const showPlayer = Boolean(expandedPlayerById[analysis.id]) && canPlayInline;
                const statusConfig = getStatusConfig(analysis.estado);

                return (
                  <motion.article
                    key={analysis.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3, delay: index * 0.05 }}
                    className="group bg-white rounded-3xl border border-slate-200/60 shadow-sm hover:shadow-md transition-all duration-300 overflow-hidden hover:-translate-y-0.5"
                  >
                    {/* Color accent stripe */}
                    <div className={`h-0.5 ${
                      isProc ? 'bg-amber-400 animate-pulse' :
                      analysis.estado === 'completed' ? 'bg-emerald-400' :
                      analysis.estado === 'error' ? 'bg-rose-400' :
                      analysis.estado === 'cancelled' ? 'bg-slate-300' :
                      'bg-slate-200'
                    }`} />

                    <div className="p-6 lg:p-7">
                      <div className="flex items-start justify-between gap-4 mb-4">
                        <div className="flex-1 min-w-0">
                          {/* Title row */}
                          <div className="flex items-center gap-4 mb-2">
                            <div className={`w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0 ${
                              analysis.estado === 'completed' ? 'bg-emerald-50 text-emerald-600' :
                              isProc ? 'bg-amber-50 text-amber-600' :
                              'bg-slate-50 text-slate-500'
                            }`}>
                              <Headphones className="w-5 h-5" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <h3 className="text-[17px] font-bold text-slate-800 truncate" title={friendlyTitle}>
                                {friendlyTitle}
                              </h3>
                            </div>
                            <button
                              onClick={() => {
                                if (canPlayInline) {
                                  setExpandedPlayerById((prev) => ({ ...prev, [analysis.id]: !prev[analysis.id] }));
                                } else {
                                  navigate({ to: `/audio/${analysis.id}` });
                                }
                              }}
                              title={canPlayInline ? 'Reproducir audio' : 'Abrir detalle para escuchar'}
                              className="inline-flex items-center gap-1.5 px-4 py-2 bg-white text-slate-600 border border-slate-200/60 rounded-full text-[13px] font-semibold hover:bg-slate-50 hover:text-slate-900 transition-all duration-200 shadow-sm"
                            >
                              <Play className="w-3.5 h-3.5" />
                              Escuchar
                            </button>
                            
                            {/* Status badge moved to title row area */}
                            <span className={`px-4 py-1.5 rounded-full text-[11px] font-bold uppercase tracking-wide flex items-center gap-1.5 border ${statusConfig.bg} ${statusConfig.text} ${statusConfig.border} flex-shrink-0 shadow-sm`}>
                              {isProc ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : analysis.estado === 'completed' ? (
                                <CheckCircle className="w-3.5 h-3.5" />
                              ) : (
                                <span className={`w-2 h-2 rounded-full ${statusConfig.dot}`} />
                              )}
                              {audioAnalysisService.getEstadoLabel(analysis.estado)}
                            </span>
                          </div>
                          <p className="text-[14px] text-slate-500 truncate pl-14 font-medium" title={contextSnippet}>
                            {contextSnippet}
                          </p>
                        </div>
                      </div>

                      {/* Inline player */}
                      <AnimatePresence>
                        {showPlayer && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="mb-4 ml-12 overflow-hidden"
                          >
                            <div className="p-3 bg-gray-50 border border-gray-200 rounded-xl">
                              <audio controls preload="none" className="w-full" src={analysis.audio_gcs_url} />
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>

                      {/* Progress bar */}
                      {isProc && analysis.progress > 0 && (
                        <div className="mb-4 ml-12">
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

                      {/* Stats chips */}
                      {analysis.estado === 'completed' && (
                        <div className="mb-4 ml-14 flex flex-wrap items-center gap-2">
                          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-100 bg-slate-50 text-slate-600 text-[12px] font-bold">
                            <BarChart3 className="w-3.5 h-3.5 text-slate-400" />
                            {analysis.total_segments} segmentos
                          </span>
                          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-emerald-100/60 bg-emerald-50 text-emerald-700 text-[12px] font-bold">
                            <Zap className="w-3.5 h-3.5" />
                            {(analysis.average_confidence * 100).toFixed(0)}% confianza
                          </span>
                          {analysis.video_duration > 0 && (
                            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-blue-100/60 bg-blue-50 text-blue-700 text-[12px] font-bold">
                              <Clock className="w-3.5 h-3.5" />
                              {audioAnalysisService.formatDuration(analysis.video_duration)}
                            </span>
                          )}
                          {analysis.video_size_mb > 0 && (
                            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-purple-100/60 bg-purple-50 text-purple-700 text-[12px] font-bold">
                              <HardDrive className="w-3.5 h-3.5" />
                              {analysis.video_size_mb.toFixed(1)} MB
                            </span>
                          )}
                        </div>
                      )}

                      {/* Actions area */}
                      <div className="flex items-center justify-between gap-3 ml-14">
                        <button
                          onClick={() => handleEliminar(analysis.id, analysis.titulo)}
                          className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-all duration-200"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          Eliminar
                        </button>

                        <div className="flex gap-2 items-center">
                          {analysis.estado === 'completed' && (
                            <>
                              <button
                                onClick={() => navigate({ to: `/audio/${analysis.id}` })}
                                className="flex items-center gap-1.5 px-4 py-2 text-[13px] font-semibold text-slate-600 bg-white border border-slate-200/60 rounded-lg hover:bg-slate-50 transition-all duration-200 shadow-sm"
                              >
                                <FileText className="w-3.5 h-3.5 text-slate-400" />
                                Transcripción
                              </button>
                              <motion.button
                                whileHover={{ scale: 1.02 }}
                                whileTap={{ scale: 0.97 }}
                                onClick={() => navigate({ to: `/audio/${analysis.id}` })}
                                className="flex items-center gap-1.5 px-5 py-2 text-[13px] font-semibold bg-red-600 text-white rounded-lg shadow-sm hover:shadow-md hover:bg-red-700 transition-all duration-200"
                              >
                                <MessageSquare className="w-3.5 h-3.5" />
                                Consultar IA
                              </motion.button>
                            </>
                          )}

                          {isProc && (
                            <div className="flex items-center gap-2 px-3.5 py-2 bg-amber-50 border border-amber-200 rounded-lg">
                              <Loader2 className="w-3.5 h-3.5 text-amber-600 animate-spin flex-shrink-0" />
                              <div className="text-xs">
                                <p className="font-semibold text-amber-800">Procesando</p>
                                <p className="text-amber-600">
                                  {analysis.current_phase || 'Extrayendo y transcribiendo...'}
                                </p>
                              </div>
                            </div>
                          )}

                          {analysis.estado === 'cancelled' && (
                            <div className="flex items-center gap-2 px-3.5 py-2 bg-gray-50 border border-gray-200 rounded-lg">
                              <Ban className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                              <span className="text-xs font-medium text-gray-500">Cancelado</span>
                            </div>
                          )}

                          {analysis.estado === 'error' && (
                            <>
                              <div className="flex items-center gap-2 px-3.5 py-2 bg-red-50 border border-red-200 rounded-lg">
                                <div className="text-xs">
                                  <p className="font-semibold text-red-800">Error</p>
                                  <p className="text-red-600 max-w-[200px] truncate">{analysis.error_message || 'Error desconocido'}</p>
                                </div>
                              </div>
                              <button
                                onClick={() => handleReprocesar(analysis.id)}
                                className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-all duration-200"
                              >
                                <RotateCcw className="w-3.5 h-3.5" />
                                Reprocesar
                              </button>
                            </>
                          )}
                        </div>
                      </div>

                      {/* Metadata footer */}
                      {analysis.created_at && (
                        <div className="mt-4 pt-3 ml-12 border-t border-gray-50">
                          <span className="flex items-center gap-1.5 text-[11px] text-gray-400">
                            <Clock className="w-3 h-3" />
                            Creado: {formatDate(analysis.created_at)}
                            {analysis.completed_at && <> • Completado: {formatDate(analysis.completed_at)}</>}
                            {analysis.tiempo_procesamiento_segundos > 0 && (
                              <> • Tiempo: {audioAnalysisService.formatDuration(analysis.tiempo_procesamiento_segundos)}</>
                            )}
                          </span>
                        </div>
                      )}
                    </div>
                  </motion.article>
                );
              })}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* ── Modal de confirmación de eliminación ── */}
      <AnimatePresence>
        {deleteTarget && (
          <motion.div
            key="delete-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
            onClick={() => !deleting && setDeleteTarget(null)}
          >
            <motion.div
              key="delete-modal"
              initial={{ opacity: 0, scale: 0.95, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 8 }}
              transition={{ type: 'spring', duration: 0.3 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6"
            >
              {/* Icono */}
              <div className="flex justify-center mb-4">
                <div className="w-14 h-14 rounded-full bg-red-50 flex items-center justify-center">
                  <Trash2 className="w-7 h-7 text-red-500" />
                </div>
              </div>

              {/* Texto */}
              <h3 className="text-lg font-bold text-gray-900 text-center mb-1">
                Eliminar análisis
              </h3>
              <p className="text-sm text-gray-500 text-center mb-1">
                ¿Estás seguro de que deseas eliminar
              </p>
              <p className="text-sm font-semibold text-gray-800 text-center mb-5 truncate px-4">
                &ldquo;{deleteTarget.title}&rdquo;
              </p>
              <p className="text-xs text-gray-400 text-center mb-6">
                Esta acción eliminará permanentemente la transcripción y todos los segmentos. No se puede deshacer.
              </p>

              {/* Botones */}
              <div className="flex gap-3">
                <button
                  onClick={() => setDeleteTarget(null)}
                  disabled={deleting}
                  className="flex-1 px-4 py-2.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-xl transition-colors disabled:opacity-50"
                >
                  Cancelar
                </button>
                <button
                  onClick={confirmEliminar}
                  disabled={deleting}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 rounded-xl transition-colors disabled:opacity-60"
                >
                  {deleting ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Eliminando...</>
                  ) : (
                    <><Trash2 className="w-4 h-4" /> Eliminar</>  
                  )}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
