import { ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Activity,
  Ban,
  CheckCircle,
  Clock,
  FileText,
  Filter,
  Loader2,
  Package,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
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
  OperationalAnalysis,
  OperationalAnalysisType,
  operationalVideoService,
} from '../services/operationalVideoService';

type ViewMode = 'cards' | 'table';

const CATEGORY_ICON_MAP: Record<string, ReactNode> = {
  ACCESS_CONTROL: <Shield className="w-5 h-5 text-tivit-red" />,
  OCCUPANCY: <Users className="w-5 h-5 text-tivit-red" />,
  PEOPLE_FLOW: <Activity className="w-5 h-5 text-tivit-red" />,
  MERCHANDISE_CONTROL: <Package className="w-5 h-5 text-tivit-red" />,
  PARKING: <Activity className="w-5 h-5 text-tivit-red" />,
  WORK_SUPERVISION: <CheckCircle className="w-5 h-5 text-tivit-red" />,
};

const QUICK_START_ORDER = [
  'ACCESS_CONTROL',
  'MERCHANDISE_CONTROL',
  'OCCUPANCY',
  'PARKING',
  'PEOPLE_FLOW',
  'WORK_SUPERVISION',
];

const itemVariants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0 },
};

export default function OperationalVideos() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [filtroTipo, setFiltroTipo] = useState<string>('');
  const [searchTerm, setSearchTerm] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('cards');

  const [compareA, setCompareA] = useState('');
  const [compareB, setCompareB] = useState('');
  const [comparison, setComparison] = useState<AnalysisComparison | null>(null);

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
      if (filtroTipo) params.analysis_type = filtroTipo;
      const response = await operationalVideoService.listarAnalisis(params);
      return response.analyses || [];
    },
    staleTime: 20 * 1000,
  });

  const deleteMutation = useMutation({
    mutationFn: async (analysisId: string) => operationalVideoService.eliminarAnalisis(analysisId),
    onSuccess: () => {
      toast.success('Analisis eliminado');
      queryClient.invalidateQueries({ queryKey: ['operational-analyses'] });
    },
    onError: (error: any) => {
      toast.error(error?.message || 'Error eliminando analisis');
    },
  });

  const reprocessMutation = useMutation({
    mutationFn: async (analysisId: string) => operationalVideoService.reprocesarAnalisis(analysisId),
    onSuccess: () => {
      toast.success('Analisis reencolado para reprocesamiento');
      queryClient.invalidateQueries({ queryKey: ['operational-analyses'] });
    },
    onError: (error: any) => {
      toast.error(error?.message || 'Error al reprocesar');
    },
  });

  const cancelMutation = useMutation({
    mutationFn: async (analysisId: string) => operationalVideoService.cancelarAnalisis(analysisId),
    onSuccess: () => {
      toast.info('Analisis cancelado');
      queryClient.invalidateQueries({ queryKey: ['operational-analyses'] });
    },
    onError: (error: any) => {
      toast.error(error?.message || 'Error cancelando analisis');
    },
  });

  const compareMutation = useMutation({
    mutationFn: async ({ a, b }: { a: string; b: string }) =>
      operationalVideoService.compararAnalisis(a, b),
    onSuccess: (result) => {
      setComparison(result);
      toast.success('Comparativa generada');
    },
    onError: (error: any) => {
      toast.error(error?.message || 'No se pudo generar la comparativa');
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
        toast.success(`Analisis completado: ${a.video_filename}`);
      }
      if (a.estado === 'cancelled' && prev && prev !== 'cancelled') {
        toast.info(`Analisis cancelado: ${a.video_filename}`);
      }
    });

    prevStatusRef.current = Object.fromEntries(analyses.map((a) => [a.id, a.estado]));
  }, [analyses, loading]);

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
    return CATEGORY_ICON_MAP[type] || <Activity className="w-5 h-5 text-tivit-red" />;
  };

  const handleCompare = async () => {
    if (!compareA || !compareB || compareA === compareB) {
      toast.error('Selecciona dos analisis distintos para comparar');
      return;
    }
    await compareMutation.mutateAsync({ a: compareA, b: compareB });
  };

  const handleDelete = async (analysisId: string) => {
    if (!confirm('Estas seguro de eliminar este analisis? Esta accion no se puede deshacer.')) return;
    await deleteMutation.mutateAsync(analysisId);
  };

  const handleReprocess = async (analysisId: string) => {
    await reprocessMutation.mutateAsync(analysisId);
  };

  const handleCancel = async (analysisId: string) => {
    if (!confirm('Cancelar este analisis? No se podra reanudar.')) return;
    await cancelMutation.mutateAsync(analysisId);
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
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-gray-50 to-stone-100 py-8 px-4">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Hero Section */}
        <div className="relative bg-white rounded-3xl border border-slate-200/60 shadow-sm p-8 lg:p-10 overflow-hidden">
          {/* Subtle Glow Background */}
          <div className="absolute top-0 right-0 w-96 h-96 rounded-full blur-3xl -mr-20 -mt-20 opacity-30 pointer-events-none bg-blue-50" />

          <div className="relative flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8">
            <div className="flex items-center gap-5 min-w-0">
              <div className="w-16 h-16 rounded-[20px] bg-red-50 border border-red-100/60 flex items-center justify-center flex-shrink-0 shadow-sm">
                <Activity className="w-8 h-8 text-red-500" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-4">
                  <h1 className="text-3xl font-bold text-slate-800 tracking-tight">Analisis Operativo</h1>
                  {readyCount > 0 && (
                    <span className="hidden sm:inline-flex items-center px-4 py-1.5 rounded-full text-[13px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-100/60 shadow-sm">
                      Reportes listos: {readyCount}
                    </span>
                  )}
                </div>
                <p className="text-slate-500 text-[15px] font-medium mt-1">
                  Analisis contextual de video con IA - define qué quieres saber
                </p>
              </div>
            </div>

            {analyses.length > 0 && (
              <button
                onClick={() => navigate({ to: '/operational/upload', search: { analysisType: undefined } })}
                className="hidden md:flex items-center gap-2 px-6 py-3 bg-white border border-slate-200/60 text-slate-700 rounded-full font-bold hover:bg-slate-50 transition-all shadow-sm flex-shrink-0"
              >
                <Plus className="w-5 h-5" />
                Nuevo Analisis
              </button>
            )}
          </div>
          <div className="flex flex-col lg:flex-row gap-4 lg:items-center lg:justify-between relative z-10 border-t border-slate-100 pt-6">
            <div className="flex gap-2 bg-slate-50/80 p-1.5 rounded-full border border-slate-200/60 w-fit">
              <button
                onClick={() => setViewMode('cards')}
                className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-[14px] font-bold transition-all duration-300 ${viewMode === 'cards'
                    ? 'bg-white shadow-sm text-red-600'
                    : 'text-slate-500 hover:text-slate-800 hover:bg-white/50'
                  }`}
                aria-label="Cambiar a vista de tarjetas"
              >
                <LayoutGrid className="w-4 h-4" />
                Cards
              </button>
              <button
                onClick={() => setViewMode('table')}
                className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-[14px] font-bold transition-all duration-300 ${viewMode === 'table'
                    ? 'bg-white shadow-sm text-red-600'
                    : 'text-slate-500 hover:text-slate-800 hover:bg-white/50'
                  }`}
                aria-label="Cambiar a vista de tabla"
              >
                <Table className="w-4 h-4" />
                Tabla
              </button>
            </div>

            <div className="flex flex-col lg:flex-row gap-3 lg:items-center">
              <div className="relative flex-1 lg:min-w-[360px]">
                <Search className="w-5 h-5 text-slate-400 absolute left-4 top-1/2 -translate-y-1/2" />
                <input
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Buscar por archivo, camara, contexto..."
                  className="w-full pl-11 pr-5 py-3.5 bg-slate-50/50 border border-slate-200/60 rounded-full focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none text-[15px] font-medium text-slate-800 shadow-sm transition-all"
                  aria-label="Buscar analisis operativos"
                />
              </div>

              <div className="flex items-center gap-3">
                <div className="relative">
                  <Filter className="w-4 h-4 text-slate-500 absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <select
                    value={filtroTipo}
                    onChange={(e) => setFiltroTipo(e.target.value)}
                    className="pl-10 pr-10 py-3.5 bg-white border border-slate-200/60 rounded-full focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none text-[14px] font-bold text-slate-700 shadow-sm appearance-none min-w-[160px] cursor-pointer"
                    aria-label="Filtrar por tipo de analisis"
                  >
                    <option value="">Todos los tipos</option>
                    {Object.entries(types).map(([key, info]) => (
                      <option key={key} value={key}>
                        {info.name}
                      </option>
                    ))}
                  </select>
                </div>

                <button
                  onClick={() => refetchAnalyses()}
                  className="flex items-center justify-center p-3.5 bg-white border border-slate-200/60 rounded-full hover:bg-slate-50 text-slate-500 hover:text-slate-800 transition-colors shadow-sm"
                  aria-label="Actualizar analisis"
                  title="Actualizar"
                >
                  <RefreshCw className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>

          {completedAnalyses.length >= 2 && (
            <div className="mt-4 border-t border-gray-100 pt-4">
              <p className="text-sm font-medium text-gray-700 mb-2">Comparar analisis completados</p>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
                <select
                  value={compareA}
                  onChange={(e) => setCompareA(e.target.value)}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
                >
                  <option value="">Analisis A</option>
                  {completedAnalyses.map((a) => (
                    <option key={`a-${a.id}`} value={a.id}>
                      {a.video_filename}
                    </option>
                  ))}
                </select>

                <select
                  value={compareB}
                  onChange={(e) => setCompareB(e.target.value)}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
                >
                  <option value="">Analisis B</option>
                  {completedAnalyses.map((a) => (
                    <option key={`b-${a.id}`} value={a.id}>
                      {a.video_filename}
                    </option>
                  ))}
                </select>

                <button
                  onClick={handleCompare}
                  disabled={compareMutation.isPending}
                  className="px-4 py-2 bg-tivit-red text-white rounded-lg hover:bg-tivit-red-dark disabled:opacity-50 text-sm"
                >
                  {compareMutation.isPending ? 'Comparando...' : 'Comparar'}
                </button>

                {comparison && (
                  <button
                    onClick={() => setComparison(null)}
                    className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
                  >
                    Limpiar
                  </button>
                )}
              </div>

              {comparison && (
                <div className="mt-3 bg-gray-50 border border-gray-200 rounded-lg p-3">
                  <p className="text-sm font-semibold text-gray-800 mb-2">Resultado</p>
                  <p className="text-xs text-gray-600 mb-2">
                    Eventos A: {comparison.analysis_a.total_events} - Eventos B: {comparison.analysis_b.total_events} - Delta: {comparison.event_count_delta}
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {Object.entries(comparison.deltas)
                      .slice(0, 8)
                      .map(([key, val]) => (
                        <div key={key} className="bg-white rounded p-2 border border-gray-100">
                          <p className="text-xs text-gray-500 uppercase">{key.replace(/_/g, ' ')}</p>
                          <p className="text-sm text-gray-800">
                            A: {val.analysis_a} - B: {val.analysis_b} - Delta: {val.delta} ({val.delta_pct}%)
                          </p>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {loading && (
          <div className="grid gap-4">
            {[0, 1, 2].map((idx) => (
              <div key={idx} className="bg-white rounded-lg shadow-md p-6 animate-pulse">
                <div className="h-5 w-52 bg-gray-200 rounded mb-3" />
                <div className="h-4 w-80 bg-gray-100 rounded mb-5" />
                <div className="grid grid-cols-3 gap-3 mb-4">
                  <div className="h-14 bg-gray-100 rounded" />
                  <div className="h-14 bg-gray-100 rounded" />
                  <div className="h-14 bg-gray-100 rounded" />
                </div>
                <div className="h-9 w-40 bg-gray-200 rounded" />
              </div>
            ))}
          </div>
        )}
        {!loading && analyses.length === 0 && (
          <div className="bg-white rounded-[32px] border border-slate-200/60 shadow-sm p-8 md:p-14 mb-8">
            <div className="border-2 border-dashed border-slate-200 rounded-[24px] bg-slate-50/50 p-12 text-center max-w-3xl mx-auto">
              <div className="w-20 h-20 rounded-[20px] bg-red-50 border border-red-100 flex items-center justify-center mx-auto mb-6 shadow-sm">
                <Activity className="w-10 h-10 text-red-500" />
              </div>
              <h3 className="text-2xl lg:text-3xl font-bold text-slate-800 mb-3 tracking-tight">No hay análisis operativos</h3>
              <p className="text-[16px] text-slate-500 mb-8 max-w-2xl mx-auto font-medium leading-relaxed">
                Sube un video para empezar a medir flujos, accesos y seguridad operacional con IA avanzada de forma automatizada.
              </p>

              <div className="flex flex-wrap gap-3 justify-center mb-10">
                {QUICK_START_ORDER.filter((key) => types[key]).map((key) => (
                  <button
                    key={key}
                    onClick={() => navigate({ to: '/operational/upload', search: { analysisType: key } })}
                    className="inline-flex items-center gap-2 px-5 py-2.5 bg-white border border-slate-200/80 shadow-sm rounded-full text-[14px] font-bold text-slate-700 hover:border-red-200 hover:bg-red-50 hover:text-red-700 transition-all"
                    aria-label={`Crear nuevo analisis tipo ${types[key].name}`}
                  >
                    {getTypeIcon(key)}
                    {types[key].name}
                  </button>
                ))}
              </div>

              <button
                onClick={() => navigate({ to: '/operational/upload', search: { analysisType: undefined } })}
                className="inline-flex items-center justify-center gap-2 bg-red-500 hover:bg-red-600 shadow-md text-white px-8 py-4 rounded-full font-bold text-[15px] transition-all"
              >
                <Plus className="w-5 h-5 ml-1" />
                Crear Nuevo Analisis
              </button>
            </div>
          </div>
        )}

        {!loading && visibleAnalyses.length > 0 && visibleAnalyses.length === 0 && (
          <div className="bg-white rounded-lg shadow-md p-8 text-center">
            <p className="text-gray-700 font-medium">No hay resultados con esos filtros</p>
            <p className="text-sm text-gray-500 mt-1">Ajusta la busqueda o limpia el filtro de tipo.</p>
          </div>
        )}

        {!loading && visibleAnalyses.length > 0 && viewMode === 'cards' && (
          <div className="grid gap-6">
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
                    className="bg-white rounded-[24px] shadow-sm border border-slate-200/60 overflow-hidden hover:shadow-md transition-shadow"
                  >
                    <div className="p-7">
                      <div className="flex items-start justify-between mb-5">
                        <div className="flex-1 min-w-0 pr-4">
                          <div className="flex items-center gap-2 mb-2">
                            {getTypeIcon(analysis.analysis_type)}
                            <span className="text-[13px] font-bold text-red-600 tracking-wide uppercase">{typeInfo.name}</span>
                          </div>
                          <h3 className="text-xl lg:text-2xl font-bold text-slate-800 mb-1.5 truncate">
                            {analysis.video_filename}
                          </h3>
                          {analysis.custom_context && (
                            <p className="text-[15px] text-slate-500 font-medium italic line-clamp-2 leading-relaxed">
                              "{analysis.custom_context}"
                            </p>
                          )}
                        </div>
                        <span
                          className={`px-4 py-2 rounded-full text-[12px] font-bold tracking-wide flex items-center gap-2 flex-shrink-0 border shadow-sm ${isProc ? 'bg-amber-50 text-amber-700 border-amber-200/60' :
                              analysis.estado === 'completed' ? 'bg-emerald-50 text-emerald-700 border-emerald-200/60' :
                                analysis.estado === 'error' ? 'bg-rose-50 text-rose-700 border-rose-200/60' :
                                  'bg-slate-50 text-slate-600 border-slate-200/60'
                            }`}
                        >
                          {isProc && <Loader2 className="w-4 h-4 animate-spin" />}
                          {analysis.estado === 'completed' && <CheckCircle className="w-4 h-4" />}
                          {operationalVideoService.getEstadoTexto(analysis.estado)}
                        </span>
                      </div>

                      {isProc && analysis.progress > 0 && (
                        <div className="mb-5 bg-slate-50/50 p-4 rounded-xl border border-slate-100">
                          <div className="flex justify-between text-[13px] font-bold text-slate-500 mb-1.5 uppercase tracking-wide">
                            <span>{analysis.current_phase || 'Procesando...'}</span>
                            <span className="text-slate-700 font-bold">{Math.round(analysis.progress)}%</span>
                          </div>
                          <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-amber-400 to-red-500 rounded-full transition-all duration-500 ease-out"
                              style={{ width: `${analysis.progress}%` }}
                            />
                          </div>
                        </div>
                      )}

                      {analysis.scan_stats && Object.keys(analysis.scan_stats).length > 0 && (
                        <div className="grid grid-cols-3 gap-3 mb-6 p-5 bg-slate-50 border border-slate-100/80 rounded-[20px]">
                          <div>
                            <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-1">Segmentos</p>
                            <p className="text-xl font-bold text-slate-800">
                              {analysis.scan_stats.segments_for_analysis || 0}
                            </p>
                          </div>
                          <div>
                            <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-1">Eventos detectados</p>
                            <p className="text-xl font-bold text-red-500 drop-shadow-sm">
                              {analysis.scan_stats.total_events ?? (analysis.scan_stats.detected_events || 0)}
                            </p>
                          </div>
                          <div>
                            <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-1">Duracion</p>
                            <p className="text-xl font-bold text-slate-800">
                              {analysis.video_duration > 0
                                ? operationalVideoService.formatDuration(analysis.video_duration)
                                : 'N/A'}
                            </p>
                          </div>
                        </div>
                      )}

                      <div className="flex gap-3 flex-wrap mt-2">
                        {analysis.estado === 'completed' && (
                          <button
                            onClick={() => navigate({ to: `/operational/${analysis.id}` })}
                            className="flex items-center gap-2 px-6 py-2.5 bg-red-500 text-white shadow-md rounded-full font-bold text-[14px] hover:bg-red-600 transition-colors"
                          >
                            <FileText className="w-4 h-4 ml-1" />
                            Ver Detalle
                          </button>
                        )}

                        {isProc && operationalVideoService.isCancellable(analysis.estado) && (
                          <button
                            onClick={() => handleCancel(analysis.id)}
                            className="flex items-center gap-2 px-6 py-2.5 text-slate-600 border border-slate-200/80 shadow-sm rounded-full font-bold text-[14px] hover:bg-rose-50 hover:text-rose-700 hover:border-rose-200 transition-colors"
                            title="Cancelar analisis"
                          >
                            <XCircle className="w-4 h-4" />
                            Cancelar
                          </button>
                        )}

                        {analysis.estado === 'error' && (
                          <button
                            onClick={() => handleReprocess(analysis.id)}
                            className="flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white shadow-md rounded-full font-bold text-[14px] hover:bg-amber-600 transition-colors"
                          >
                            <RotateCcw className="w-4 h-4" />
                            Reprocesar
                          </button>
                        )}

                        <button
                          onClick={() => handleDelete(analysis.id)}
                          className="ml-auto flex items-center gap-2 px-5 py-2.5 text-red-500 border border-red-100 shadow-sm rounded-full font-bold text-[14px] hover:bg-red-50 focus:ring-2 focus:ring-red-100 transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                          Eliminar
                        </button>
                      </div>

                      {analysis.created_at && (
                        <div className="mt-5 pt-4 border-t border-slate-100/60 flex items-center gap-2 text-[12px] font-bold text-slate-400">
                          <Clock className="w-3.5 h-3.5" />
                          <span>
                            Creado: {formatDate(analysis.created_at)}
                            {analysis.completed_at && <> &bull; Completado: {formatDate(analysis.completed_at)}</>}
                            {analysis.tiempo_procesamiento_segundos > 0 && (
                              <span className="hidden sm:inline"> &bull; Tiempo: {operationalVideoService.formatDuration(analysis.tiempo_procesamiento_segundos)}</span>
                            )}
                          </span>
                        </div>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        )}

        {!loading && visibleAnalyses.length > 0 && viewMode === 'table' && (
          <div className="bg-white rounded-lg shadow-md overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="text-left px-4 py-3 font-semibold">Tipo</th>
                    <th className="text-left px-4 py-3 font-semibold">Archivo</th>
                    <th className="text-left px-4 py-3 font-semibold">Estado</th>
                    <th className="text-left px-4 py-3 font-semibold">Creado</th>
                    <th className="text-right px-4 py-3 font-semibold">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleAnalyses.map((analysis) => {
                    const typeInfo = getTypeInfo(analysis.analysis_type);
                    const isProc = operationalVideoService.isProcessing(analysis.estado);

                    return (
                      <tr key={analysis.id} className="border-t border-gray-100 hover:bg-gray-50/70">
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center gap-2 text-tivit-red font-medium">
                            {getTypeIcon(analysis.analysis_type)}
                            {typeInfo.name}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-800 max-w-[340px] truncate">{analysis.video_filename}</td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center gap-2 px-2 py-1 rounded-full text-xs font-medium ${operationalVideoService.getEstadoColor(
                              analysis.estado,
                            )}`}
                          >
                            {isProc && <Loader2 className="w-3 h-3 animate-spin" />}
                            {operationalVideoService.getEstadoTexto(analysis.estado)}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-600">{formatDate(analysis.created_at)}</td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end gap-2">
                            {analysis.estado === 'completed' && (
                              <button
                                onClick={() => navigate({ to: `/operational/${analysis.id}` })}
                                className="px-3 py-1.5 rounded border border-tivit-red text-tivit-red hover:bg-red-50"
                              >
                                Detalle
                              </button>
                            )}
                            {analysis.estado === 'error' && (
                              <button
                                onClick={() => handleReprocess(analysis.id)}
                                className="px-3 py-1.5 rounded bg-orange-500 text-white hover:bg-orange-600"
                              >
                                Reprocesar
                              </button>
                            )}
                            {isProc && operationalVideoService.isCancellable(analysis.estado) && (
                              <button
                                onClick={() => handleCancel(analysis.id)}
                                className="px-3 py-1.5 rounded border border-gray-300 text-gray-700 hover:bg-red-50 hover:text-red-700"
                              >
                                Cancelar
                              </button>
                            )}
                            <button
                              onClick={() => handleDelete(analysis.id)}
                              className="px-3 py-1.5 rounded border border-red-300 text-red-600 hover:bg-red-50"
                            >
                              Eliminar
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
