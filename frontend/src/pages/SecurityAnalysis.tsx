import { useState, useEffect } from 'react';
import {
    securityVideoService,
    SecurityVideo,
    ContextualAnalysis,
    EstadoSecurityVideo
} from '../services/securityVideoService';
import { toast } from 'sonner';
import {
    Search,
    Video,
    FileText,
    Download,
    RefreshCw,
    Clock,
    CheckCircle,
    AlertCircle,
    Loader2,
    ChevronDown,
    Sparkles,
    Zap
} from 'lucide-react';

export default function SecurityAnalysis() {
    // Estados
    const [videos, setVideos] = useState<SecurityVideo[]>([]);
    const [analyses, setAnalyses] = useState<ContextualAnalysis[]>([]);
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [refreshing, setRefreshing] = useState(false);

    // Formulario
    const [selectedVideoId, setSelectedVideoId] = useState('');
    const [contexto, setContexto] = useState('');
    const [modo, setModo] = useState<'ESTANDAR' | 'PROFUNDO'>('ESTANDAR');

    // Cargar datos iniciales
    useEffect(() => {
        cargarDatos();
    }, []);

    const cargarDatos = async () => {
        try {
            setLoading(true);

            // Cargar videos completados
            const videosRes = await securityVideoService.listarVideos({
                estado: EstadoSecurityVideo.COMPLETED
            });
            setVideos(videosRes.videos);

            // Cargar análisis existentes
            try {
                const analysisRes = await securityVideoService.listarAnalisis();
                setAnalyses(analysisRes.analyses || []);
            } catch {
                // Si falla, puede que no haya análisis aún
                setAnalyses([]);
            }

        } catch (error: any) {
            toast.error('Error cargando datos');
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const refrescarAnalisis = async () => {
        try {
            setRefreshing(true);
            const res = await securityVideoService.listarAnalisis();
            setAnalyses(res.analyses || []);
            toast.success('Lista actualizada');
        } catch (error) {
            toast.error('Error refrescando análisis');
        } finally {
            setRefreshing(false);
        }
    };

    const iniciarAnalisis = async () => {
        if (!selectedVideoId) {
            toast.error('Selecciona un video');
            return;
        }
        if (!contexto.trim()) {
            toast.error('Escribe qué deseas analizar');
            return;
        }

        try {
            setSubmitting(true);
            const res = await securityVideoService.iniciarAnalisisContextual(
                selectedVideoId,
                contexto,
                modo
            );

            if (res.success) {
                toast.success('Análisis iniciado correctamente');
                setContexto('');
                setSelectedVideoId('');

                // Refrescar lista
                await refrescarAnalisis();
            }
        } catch (error: any) {
            toast.error(error.message || 'Error iniciando análisis');
        } finally {
            setSubmitting(false);
        }
    };

    const descargarReporte = async (analysisId: string, formato: 'pdf' | 'json' | 'txt') => {
        try {
            const blob = await securityVideoService.descargarReporte(analysisId, formato);

            // Crear URL y descargar
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `reporte_${analysisId}.${formato}`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);

            toast.success(`Descargando reporte ${formato.toUpperCase()}`);
        } catch (error) {
            toast.error('Error descargando reporte');
        }
    };

    const formatFecha = (isoDate: string) => {
        const date = new Date(isoDate);
        return date.toLocaleDateString('es-PE', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    const getVideoNombre = (videoId: string) => {
        const video = videos.find(v => v.id === videoId);
        return video ? `${video.nombre_camara} - ${video.ubicacion}` : videoId;
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[400px]">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            </div>
        );
    }

    return (
        <div className="container mx-auto px-4 py-8 max-w-5xl">
            {/* Header */}
            <div className="mb-8">
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
                    <Search className="w-8 h-8 text-blue-500" />
                    Análisis Contextual de Seguridad
                </h1>
                <p className="text-gray-600 dark:text-gray-400 mt-2">
                    Analiza videos de seguridad con preguntas específicas usando IA
                </p>
            </div>

            {/* Formulario de nuevo análisis */}
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6 mb-8 border border-gray-200 dark:border-gray-700">
                <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-yellow-500" />
                    Nuevo Análisis
                </h2>

                {/* Selector de video */}
                <div className="mb-4">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Video de seguridad
                    </label>
                    <div className="relative">
                        <select
                            value={selectedVideoId}
                            onChange={(e) => setSelectedVideoId(e.target.value)}
                            className="w-full px-4 py-3 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white appearance-none cursor-pointer focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        >
                            <option value="">Seleccionar video...</option>
                            {videos.map((video) => (
                                <option key={video.id} value={video.id}>
                                    {video.nombre_camara} - {video.ubicacion} ({securityVideoService.formatDuration(video.duracion_segundos)})
                                </option>
                            ))}
                        </select>
                        <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400 pointer-events-none" />
                    </div>
                    {videos.length === 0 && (
                        <p className="text-sm text-yellow-600 mt-2">
                            No hay videos procesados. Primero sube y procesa un video de seguridad.
                        </p>
                    )}
                </div>

                {/* Campo de contexto */}
                <div className="mb-4">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        ¿Qué deseas analizar?
                    </label>
                    <textarea
                        value={contexto}
                        onChange={(e) => setContexto(e.target.value)}
                        placeholder="Ej: Cuántas personas pasaron por el pasillo, ¿hubo alguna actividad sospechosa?, ¿cuántos vehículos entraron?"
                        rows={3}
                        className="w-full px-4 py-3 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                    />
                </div>

                {/* Selector de modo */}
                <div className="mb-6">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Modo de análisis
                    </label>
                    <div className="flex gap-4">
                        <label className={`flex-1 flex items-center gap-3 p-4 rounded-xl border-2 cursor-pointer transition-all ${modo === 'ESTANDAR'
                                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                                : 'border-gray-300 dark:border-gray-600 hover:border-gray-400'
                            }`}>
                            <input
                                type="radio"
                                name="modo"
                                value="ESTANDAR"
                                checked={modo === 'ESTANDAR'}
                                onChange={() => setModo('ESTANDAR')}
                                className="sr-only"
                            />
                            <Zap className={`w-5 h-5 ${modo === 'ESTANDAR' ? 'text-blue-500' : 'text-gray-400'}`} />
                            <div>
                                <div className="font-medium text-gray-900 dark:text-white">Estándar</div>
                                <div className="text-sm text-gray-500">Análisis rápido con Gemini AI</div>
                            </div>
                        </label>

                        <label className={`flex-1 flex items-center gap-3 p-4 rounded-xl border-2 cursor-pointer transition-all ${modo === 'PROFUNDO'
                                ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20'
                                : 'border-gray-300 dark:border-gray-600 hover:border-gray-400'
                            }`}>
                            <input
                                type="radio"
                                name="modo"
                                value="PROFUNDO"
                                checked={modo === 'PROFUNDO'}
                                onChange={() => setModo('PROFUNDO')}
                                className="sr-only"
                            />
                            <Sparkles className={`w-5 h-5 ${modo === 'PROFUNDO' ? 'text-purple-500' : 'text-gray-400'}`} />
                            <div>
                                <div className="font-medium text-gray-900 dark:text-white">Profundo</div>
                                <div className="text-sm text-gray-500">+ Video Intelligence API</div>
                            </div>
                        </label>
                    </div>
                </div>

                {/* Botón de envío */}
                <button
                    onClick={iniciarAnalisis}
                    disabled={submitting || !selectedVideoId || !contexto.trim()}
                    className="w-full py-3 px-6 bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-xl"
                >
                    {submitting ? (
                        <>
                            <Loader2 className="w-5 h-5 animate-spin" />
                            Iniciando análisis...
                        </>
                    ) : (
                        <>
                            <Search className="w-5 h-5" />
                            Iniciar Análisis
                        </>
                    )}
                </button>
            </div>

            {/* Lista de análisis */}
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6 border border-gray-200 dark:border-gray-700">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-semibold flex items-center gap-2">
                        <FileText className="w-5 h-5 text-green-500" />
                        Mis Análisis
                    </h2>
                    <button
                        onClick={refrescarAnalisis}
                        disabled={refreshing}
                        className="p-2 text-gray-500 hover:text-blue-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                    >
                        <RefreshCw className={`w-5 h-5 ${refreshing ? 'animate-spin' : ''}`} />
                    </button>
                </div>

                {analyses.length === 0 ? (
                    <div className="text-center py-12 text-gray-500">
                        <Search className="w-12 h-12 mx-auto mb-4 opacity-50" />
                        <p>No hay análisis todavía</p>
                        <p className="text-sm">Inicia tu primer análisis contextual</p>
                    </div>
                ) : (
                    <div className="space-y-4">
                        {analyses.map((analysis) => (
                            <div
                                key={analysis.id}
                                className="p-4 rounded-xl border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
                            >
                                <div className="flex items-start justify-between">
                                    <div className="flex-1">
                                        {/* Contexto */}
                                        <div className="font-medium text-gray-900 dark:text-white mb-1 flex items-center gap-2">
                                            <span className="text-lg">"{analysis.contexto}"</span>
                                            <span className={`px-2 py-0.5 text-xs rounded-full ${securityVideoService.getAnalysisEstadoColor(analysis.estado)}`}>
                                                {securityVideoService.getAnalysisEstadoTexto(analysis.estado)}
                                            </span>
                                        </div>

                                        {/* Meta info */}
                                        <div className="flex items-center gap-4 text-sm text-gray-500">
                                            <span className="flex items-center gap-1">
                                                <Video className="w-4 h-4" />
                                                {getVideoNombre(analysis.video_id)}
                                            </span>
                                            <span className="flex items-center gap-1">
                                                <Clock className="w-4 h-4" />
                                                {formatFecha(analysis.fecha_creacion)}
                                            </span>
                                            <span className={`px-2 py-0.5 rounded text-xs ${analysis.modo === 'PROFUNDO'
                                                    ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300'
                                                    : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                                                }`}>
                                                {analysis.modo}
                                            </span>
                                        </div>

                                        {/* Resultado (si está completado) */}
                                        {analysis.estado === 'completed' && analysis.resultado && (
                                            <div className="mt-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                                                <p className="text-sm text-gray-700 dark:text-gray-300">
                                                    {analysis.resultado.respuesta_consulta}
                                                </p>
                                                {analysis.resultado.estadisticas && (
                                                    <div className="flex gap-4 mt-2 text-xs text-gray-500">
                                                        <span>📊 {analysis.resultado.estadisticas.total_movimientos} movimientos</span>
                                                        <span>🎯 {analysis.resultado.estadisticas.relevantes_contexto} relevantes</span>
                                                        <span>📈 {analysis.resultado.estadisticas.porcentaje_relevancia}% relevancia</span>
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {/* Error */}
                                        {analysis.estado === 'error' && analysis.error && (
                                            <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg flex items-center gap-2 text-red-600">
                                                <AlertCircle className="w-4 h-4" />
                                                <span className="text-sm">{analysis.error}</span>
                                            </div>
                                        )}

                                        {/* Procesando */}
                                        {analysis.estado === 'processing' && (
                                            <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg flex items-center gap-2 text-blue-600">
                                                <Loader2 className="w-4 h-4 animate-spin" />
                                                <span className="text-sm">Analizando video...</span>
                                            </div>
                                        )}
                                    </div>

                                    {/* Botones de descarga */}
                                    {analysis.estado === 'completed' && (
                                        <div className="flex items-center gap-2 ml-4">
                                            <button
                                                onClick={() => descargarReporte(analysis.id, 'pdf')}
                                                className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                                                title="Descargar PDF"
                                            >
                                                <Download className="w-5 h-5" />
                                            </button>
                                            <button
                                                onClick={() => descargarReporte(analysis.id, 'json')}
                                                className="p-2 text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                                                title="Descargar JSON"
                                            >
                                                <FileText className="w-5 h-5" />
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
