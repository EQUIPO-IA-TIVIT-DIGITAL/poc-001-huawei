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
  ChevronLeft,
  ChevronRight,
  Loader2,
  User,
  ArrowRight,
  Package,
  RefreshCw,
  Download,
  AlertTriangle,
  XCircle,
  Ban,
} from 'lucide-react';

export default function OperationalVideoDetail() {
  const { analysisId } = useParams({ strict: false }) as { analysisId: string };
  const navigate = useNavigate();

  // Core state
  const [analysis, setAnalysis] = useState<OperationalAnalysis | null>(null);
  const [events, setEvents] = useState<OperationalEvent[]>([]);
  const [types, setTypes] = useState<Record<string, OperationalAnalysisType>>({});
  const [loading, setLoading] = useState(true);
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

  // ETA
  const [etaSeconds, setEtaSeconds] = useState<number | null>(null);

  // ═══════════════════════════════════════════════════
  // DATA LOADING
  // ═══════════════════════════════════════════════════

  useEffect(() => {
    if (analysisId) loadData();
    return () => {
      // Cleanup SSE on unmount
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (pollingCleanupRef.current) {
        pollingCleanupRef.current();
        pollingCleanupRef.current = null;
      }
    };
  }, [analysisId]);

  const loadData = async () => {
    try {
      setLoading(true);
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
    } catch (error: any) {
      toast.error(error.message || 'Error cargando análisis');
    } finally {
      setLoading(false);
    }
  };

  const loadEvents = async (page: number) => {
    try {
      const res: PaginatedEvents = await operationalVideoService.obtenerEventos(analysisId, page, PER_PAGE);
      setEvents(res.events);
      setCurrentPage(res.page);
      setTotalPages(res.total_pages);
      setTotalEvents(res.total);
    } catch (error: any) {
      console.error('Error loading events:', error);
    }
  };

  // ═══════════════════════════════════════════════════
  // SSE — REAL-TIME PROGRESS
  // ═══════════════════════════════════════════════════

  const startSSE = useCallback(() => {
    if (eventSourceRef.current) return; // Already connected

    try {
      const es = operationalVideoService.connectSSE(
        analysisId,
        (data: SSEProgressData) => {
          setSSEConnected(true);
          // Capture ETA
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
              toast.success('¡Análisis completado!');
              loadEvents(1);
              // Reload full analysis to get report URLs
              operationalVideoService.obtenerAnalisis(analysisId).then((a) => {
                setAnalysis(a);
              });
            } else if (data.status === 'cancelled') {
              toast.info('Análisis cancelado');
            } else if (data.status === 'error') {
              toast.error('El análisis falló');
            }
          }
        },
        () => {
          setSSEConnected(false);
          eventSourceRef.current = null;
          // Fallback to polling
          startPolling();
        }
      );
      eventSourceRef.current = es;
    } catch {
      // Fallback to polling if SSE not supported
      startPolling();
    }
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
          await loadEvents(1);          toast.success('¡Análisis completado!');
        } else if (updated.estado === 'error') {
          clearInterval(interval);
          pollingCleanupRef.current = null;
          toast.error('El análisis falló');
        }
      } catch { /* ignore polling errors */ }
    }, 8000);

    pollingCleanupRef.current = () => clearInterval(interval);
  }, [analysisId]);

  // ═══════════════════════════════════════════════════
  // ACTIONS
  // ═══════════════════════════════════════════════════

  const handleReprocess = async () => {
    if (!analysis || analysis.estado !== 'error') return;
    try {
      setReprocessing(true);
      const res = await operationalVideoService.reprocesarAnalisis(analysisId);
      toast.success(res.message || 'Reprocesamiento iniciado');
      // Reset state and start SSE
      setAnalysis((prev) => prev ? { ...prev, estado: 'pending', progress: 0, current_phase: '' } : prev);
      setEvents([]);
      startSSE();
    } catch (error: any) {
      toast.error(error.message || 'Error reprocesando');
    } finally {
      setReprocessing(false);
    }
  };

  const handleCancel = async () => {
    if (!analysis || !operationalVideoService.isCancellable(analysis.estado)) return;
    if (!confirm('¿Estás seguro de cancelar este análisis? No se podrá reanudar.')) return;
    try {
      setCancelling(true);
      await operationalVideoService.cancelarAnalisis(analysisId);
      toast.info('Análisis cancelado');
      setAnalysis((prev) => prev ? { ...prev, estado: 'cancelled' } : prev);
      setEtaSeconds(null);
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (pollingCleanupRef.current) {
        pollingCleanupRef.current();
        pollingCleanupRef.current = null;
      }
    } catch (error: any) {
      toast.error(error.message || 'Error cancelando');
    } finally {
      setCancelling(false);
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

  const formatDate = (isoDate: string) => {
    if (!isoDate) return 'N/A';
    return new Date(isoDate).toLocaleString('es-ES', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  };

  // ═══════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-12 h-12 animate-spin text-tivit-red mx-auto mb-4" />
          <p className="text-gray-600">Cargando análisis...</p>
        </div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600 mb-4">Análisis no encontrado</p>
          <button onClick={() => navigate({ to: '/operational' })} className="text-tivit-red hover:underline">
            Volver
          </button>
        </div>
      </div>
    );
  }

  const typeInfo = types[analysis.analysis_type] || { name: analysis.analysis_type, icon: '📊' };
  const isProcessing = operationalVideoService.isProcessing(analysis.estado);
  const isCancellable = operationalVideoService.isCancellable(analysis.estado);
  const isCancelled = analysis.estado === 'cancelled';
  const isError = analysis.estado === 'error';
  const isCompleted = analysis.estado === 'completed';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-gray-50 to-stone-100 py-8 px-4">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Back + Header */}
        <div className="mb-6">
          <button
            onClick={() => navigate({ to: '/operational' })}
            className="flex items-center gap-2 text-slate-500 hover:text-slate-800 font-bold mb-4 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
            Volver a Análisis Operativo
          </button>

          <div className="relative bg-white rounded-[32px] shadow-sm border border-slate-200/60 p-8 lg:p-10 overflow-hidden">
            {/* Subtle glow */}
            <div className="absolute top-0 right-0 w-[400px] h-[400px] rounded-full blur-3xl -mr-32 -mt-32 opacity-30 pointer-events-none bg-blue-50" />

            <div className="relative flex flex-col md:flex-row md:items-start justify-between gap-6">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-[12px] bg-red-50 border border-red-100/60 flex items-center justify-center shadow-sm">
                    <span className="text-[20px] leading-none">{typeInfo.icon}</span>
                  </div>
                  <span className="text-[13px] font-bold text-red-600 tracking-wide uppercase">
                    {typeInfo.name}
                  </span>
                  {sseConnected && (
                    <span className="text-[11px] font-bold bg-emerald-100 text-emerald-800 px-3 py-1 rounded-full uppercase tracking-widest animate-pulse border border-emerald-200">
                      En vivo
                    </span>
                  )}
                </div>
                <h1 className="text-3xl lg:text-4xl font-bold text-slate-800 tracking-tight mb-2 truncate">
                  {analysis.video_filename}
                </h1>
                {analysis.custom_context && (
                  <p className="text-[16px] font-medium text-slate-500 italic mt-2">
                    "{analysis.custom_context}"
                  </p>
                )}
                <div className="flex flex-wrap gap-4 mt-4 text-[13px] font-bold text-slate-500 uppercase tracking-wide">
                  {analysis.nombre_camara ? (
                    <span className="flex items-center gap-1.5"><Image className="w-4 h-4" /> {analysis.nombre_camara}</span>
                  ) : (
                    <span className="flex items-center gap-1.5"><Image className="w-4 h-4 text-slate-400" /> SIN CÁMARA</span>
                  )}
                  {analysis.ubicacion ? (
                    <span className="flex items-center gap-1.5 text-red-500"><AlertTriangle className="w-4 h-4" /> {analysis.ubicacion}</span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-slate-400"><XCircle className="w-4 h-4" /> Sin ubicación</span>
                  )}
                  {analysis.video_duration > 0 && (
                    <span className="flex items-center gap-1.5">
                      <Clock className="w-4 h-4" />
                      {operationalVideoService.formatDuration(analysis.video_duration)}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap md:flex-nowrap items-center gap-3 relative z-10 flex-shrink-0">
                {/* Action buttons */}
                {isCompleted && analysis.report_pdf_url && (
                  <a
                    href={analysis.report_pdf_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 px-6 py-3 bg-red-500 text-white rounded-full font-bold text-[14px] hover:bg-red-600 shadow-md transition-colors"
                  >
                    <Download className="w-4 h-4" />
                    Descargar Reporte
                  </a>
                )}

                {isCancellable && (
                  <button
                    onClick={handleCancel}
                    disabled={cancelling}
                    className="flex items-center gap-2 px-6 py-3 bg-slate-100 text-slate-700 rounded-full font-bold text-[14px] hover:bg-rose-50 hover:text-rose-700 disabled:opacity-50 transition-colors"
                  >
                    {cancelling ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <XCircle className="w-4 h-4" />
                    )}
                    Cancelar
                  </button>
                )}

                {isError && (
                  <button
                    onClick={handleReprocess}
                    disabled={reprocessing}
                    className="flex items-center gap-2 px-6 py-3 bg-amber-500 text-white rounded-full font-bold text-[14px] hover:bg-amber-600 shadow-md disabled:opacity-50 transition-colors"
                  >
                    {reprocessing ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <RefreshCw className="w-4 h-4" />
                    )}
                    Reprocesar
                  </button>
                )}

                <span
                  className={`px-5 py-3 rounded-full text-[13px] font-bold uppercase tracking-wide flex items-center gap-2 border shadow-sm ${
                    isProcessing ? 'bg-amber-50 text-amber-700 border-amber-200/60' :
                    isCompleted ? 'bg-emerald-500 text-white border-emerald-600 shadow-emerald-500/20' :
                    isError ? 'bg-rose-50 text-rose-700 border-rose-200/60' :
                    'bg-slate-50 text-slate-600 border-slate-200/60'
                  }`}
                >
                  {isProcessing && <Loader2 className="w-4 h-4 animate-spin" />}
                  {isError && <AlertTriangle className="w-4 h-4" />}
                  {isCancelled && <Ban className="w-4 h-4" />}
                  {operationalVideoService.getEstadoTexto(analysis.estado)}
                </span>
              </div>
            </div>

            {/* Progress bar */}
            {isProcessing && analysis.progress > 0 && (
              <div className="mt-8 bg-slate-50/50 p-5 rounded-2xl border border-slate-100">
                <div className="flex justify-between text-[13px] font-bold text-slate-500 mb-2 uppercase tracking-wide">
                  <span>{analysis.current_phase || 'Procesando...'}</span>
                  <div className="flex items-center gap-4">
                    {etaSeconds != null && etaSeconds > 0 && (
                      <span className="text-red-500 flex items-center gap-1.5">
                        <Clock className="w-4 h-4" />
                        ETA: {operationalVideoService.formatETA(etaSeconds)}
                      </span>
                    )}
                    <span className="text-slate-800">{Math.round(analysis.progress)}%</span>
                  </div>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-amber-400 to-red-500 rounded-full transition-all duration-500" style={{ width: `${analysis.progress}%` }} />
                </div>
              </div>
            )}

            {/* Cancelled state */}
            {isCancelled && (
              <div className="mt-6 p-4 bg-slate-50 border border-slate-200/60 rounded-xl">
                <p className="text-[14px] font-bold text-slate-600 flex items-center gap-2">
                  <Ban className="w-5 h-5 text-slate-400" />
                  Este análisis fue cancelado. Puedes eliminarlo o crear uno nuevo.
                </p>
              </div>
            )}

            {/* Error message */}
            {isError && analysis.error_message && (
              <div className="mt-6 p-4 bg-rose-50 border border-rose-200/60 rounded-xl">
                <p className="text-[14px] font-bold text-rose-700 flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5" />
                  {analysis.error_message}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Completed summary + video + heatmap */}
        {isCompleted && (
          <>
          </>
        )}

        {/* Events Timeline with Pagination */}
        {events.length > 0 ? (
          <div className="bg-white rounded-[32px] shadow-sm border border-slate-200/60 p-8 lg:p-10">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl lg:text-2xl font-bold text-slate-800 flex items-center gap-3">
                <Image className="w-6 h-6 text-red-500" />
                Eventos Detectados ({totalEvents})
              </h2>
              {/* Pagination controls */}
              {totalPages > 1 && (
                <div className="flex items-center gap-3 bg-slate-50 p-1.5 rounded-full border border-slate-200/60">
                  <button
                    onClick={() => loadEvents(currentPage - 1)}
                    disabled={currentPage <= 1}
                    className="p-1.5 rounded-full bg-white shadow-sm text-slate-500 hover:text-slate-800 disabled:opacity-30 transition-all font-bold"
                  >
                    <ChevronLeft className="w-5 h-5" />
                  </button>
                  <span className="text-[13px] font-bold text-slate-600 px-2 tracking-wide">
                    Página {currentPage} de {totalPages}
                  </span>
                  <button
                    onClick={() => loadEvents(currentPage + 1)}
                    disabled={currentPage >= totalPages}
                    className="p-1.5 rounded-full bg-white shadow-sm text-slate-500 hover:text-slate-800 disabled:opacity-30 transition-all font-bold"
                  >
                    <ChevronRight className="w-5 h-5" />
                  </button>
                </div>
              )}
            </div>

            <div className="space-y-4">
              {events.map((event, idx) => {
                const isExpanded = expandedEvent === event.id;
                const globalIdx = (currentPage - 1) * PER_PAGE + idx + 1;

                return (
                  <div key={event.id} className={`border rounded-[20px] overflow-hidden transition-all duration-300 ${isExpanded ? 'border-slate-300 shadow-sm bg-slate-50/30' : 'border-slate-200 hover:border-slate-300 hover:shadow-sm'}`}>
                    {/* Event header */}
                    <button
                      onClick={() => setExpandedEvent(isExpanded ? null : event.id)}
                      className="w-full p-5 lg:px-6 flex items-center justify-between transition-colors outline-none"
                    >
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="text-[12px] font-bold font-mono bg-slate-100 text-slate-500 px-3 py-1 rounded-full border border-slate-200/60 shadow-sm">
                          #{globalIdx}
                        </span>
                        <span className="text-[14px] font-bold text-slate-700 tracking-wide">
                          {formatTime(event.timestamp_start)} — {formatTime(event.timestamp_end)}
                        </span>
                        <span className="px-3 py-1 bg-red-50 text-red-600 border border-red-100/60 font-bold text-[11px] rounded-full uppercase tracking-wider shadow-sm">
                          {event.event_type.replace(/_/g, ' ')}
                        </span>
                        {event.direction && (
                          <span className="flex items-center gap-1.5 text-[11px] font-bold text-slate-500 uppercase tracking-widest ml-1">
                            <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                            {event.direction}
                          </span>
                        )}
                      </div>
                      <div className={`p-1.5 rounded-full transition-colors ${isExpanded ? 'bg-slate-200/60 text-slate-700' : 'bg-slate-100 text-slate-400 hover:bg-slate-200'}`}>
                        {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                      </div>
                    </button>

                    {/* Event detail */}
                    {isExpanded && (
                      <div className="p-5 lg:px-6 pt-0 border-t border-slate-100 mt-2">
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-4">
                          {/* Info */}
                          <div className="space-y-4">
                            {event.person_description && (
                              <div className="flex items-start gap-3 bg-white p-4 rounded-2xl border border-slate-100 shadow-sm">
                                <User className="w-5 h-5 text-red-400 mt-0.5" />
                                <div>
                                  <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-1">Persona</p>
                                  <p className="text-[14px] font-medium text-slate-700">{event.person_description}</p>
                                </div>
                              </div>
                            )}
                            {event.carried_objects && (
                              <div className="flex items-start gap-3 bg-white p-4 rounded-2xl border border-slate-100 shadow-sm">
                                <Package className="w-5 h-5 text-red-400 mt-0.5" />
                                <div>
                                  <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-1">Objetos</p>
                                  <p className="text-[14px] font-medium text-slate-700">{event.carried_objects}</p>
                                </div>
                              </div>
                            )}
                            {event.confidence && (
                              <p className="text-[12px] font-bold text-slate-500 tracking-wide uppercase px-1">Confianza: <span className="text-slate-800">{event.confidence}</span></p>
                            )}
                            {event.details && Object.keys(event.details).length > 0 && (
                              <details className="mt-4 p-4 bg-white rounded-2xl border border-slate-100 shadow-sm">
                                <summary className="text-[12px] font-bold text-slate-500 uppercase tracking-wide cursor-pointer hover:text-red-500 flex items-center gap-2">
                                  Ver meta-datos completos
                                </summary>
                                <pre className="mt-4 p-4 bg-slate-50 rounded-xl text-xs text-slate-600 overflow-auto max-h-48 border border-slate-100">
                                  {JSON.stringify(event.details, null, 2)}
                                </pre>
                              </details>
                            )}
                          </div>

                          {/* Frames */}
                          {event.frame_urls && event.frame_urls.length > 0 && (
                            <div className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm">
                              <p className="text-[11px] font-bold text-slate-500 mb-3 flex items-center gap-1.5 uppercase tracking-widest">
                                <Image className="w-4 h-4 text-slate-400" />
                                Capturas ({event.frame_urls.length})
                              </p>
                              <div className="grid grid-cols-2 gap-3">
                                {event.frame_urls.map((url, fIdx) => (
                                  <a key={fIdx} href={url} target="_blank" rel="noopener noreferrer" className="overflow-hidden rounded-xl border border-slate-200">
                                    <img
                                      src={url}
                                      alt={`Frame ${fIdx + 1}`}
                                      crossOrigin="use-credentials"
                                      className="w-full h-32 object-cover hover:scale-105 transition-transform duration-500"
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

            {/* Bottom pagination */}
            {totalPages > 1 && (
              <div className="flex justify-center items-center gap-4 mt-8 pt-6 border-t border-slate-100">
                <button
                  onClick={() => loadEvents(currentPage - 1)}
                  disabled={currentPage <= 1}
                  className="flex items-center gap-2 px-5 py-2.5 text-[14px] font-bold bg-white border border-slate-200/60 shadow-sm rounded-full text-slate-600 hover:text-slate-900 disabled:opacity-40 transition-all"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Anterior
                </button>
                <span className="text-[13px] font-bold text-slate-500 tracking-wide bg-slate-50 px-4 py-2 rounded-full border border-slate-200/60">
                  {currentPage} de {totalPages}
                </span>
                <button
                  onClick={() => loadEvents(currentPage + 1)}
                  disabled={currentPage >= totalPages}
                  className="flex items-center gap-2 px-5 py-2.5 text-[14px] font-bold bg-white border border-slate-200/60 shadow-sm rounded-full text-slate-600 hover:text-slate-900 disabled:opacity-40 transition-all"
                >
                  Siguiente
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        ) : isCompleted ? (
          <div className="bg-white rounded-[32px] shadow-sm border border-slate-200/60 p-12 text-center mb-6">
            <h3 className="text-2xl font-bold text-slate-800 mb-3 tracking-tight">Análisis Completado sin Eventos</h3>
            <p className="text-[16px] font-medium text-slate-500">La Inteligencia Artificial no ha detectado eventos o anomalías operativas que reportar en esta franja de video.</p>
          </div>
        ) : null}

        {/* Dates */}
        <div className="mt-8 text-center text-[12px] font-bold text-slate-400 tracking-wide uppercase">
          Creado: {formatDate(analysis.created_at)}
          {analysis.completed_at && <> &bull; Completado: {formatDate(analysis.completed_at)}</>}
          {analysis.tiempo_procesamiento_segundos > 0 && (
            <> &bull; Procesamiento: {operationalVideoService.formatDuration(analysis.tiempo_procesamiento_segundos)}</>
          )}
        </div>
      </div>
    </div>
  );
}
