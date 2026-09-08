import { useState, useEffect, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { securityVideoService, SecurityVideo } from '../services/securityVideoService';
import { toast } from 'sonner';
import {
  Video,
  Plus,
  Clock,
  AlertTriangle,
  FileText,
  Trash2,
  RefreshCw,
  Loader2,
  CheckCircle,
  RotateCcw
} from 'lucide-react';

export default function SecurityVideos() {
  const navigate = useNavigate();
  const [videos, setVideos] = useState<SecurityVideo[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtroEstado, setFiltroEstado] = useState<string>('');
  const prevStatusRef = useRef<Record<string, { estado: string; hasReport: boolean }>>({});
  const hasLoadedOnceRef = useRef(false);

  useEffect(() => {
    cargarVideos();
  }, [filtroEstado]);

  // Auto-refresh cada 10 segundos si hay videos en procesamiento
  useEffect(() => {
    const hasProcessingVideos = videos.some(v => 
      ['uploading', 'uploaded', 'motion_detecting', 'motion_detected', 'analyzing', 'classifying', 'deep_analyzing', 'generating_report'].includes(v.estado)
    );

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
      const params: any = { limit: 50 };
      if (filtroEstado) {
        params.estado = filtroEstado;
      }

      const response = await securityVideoService.listarVideos(params);
      const nextVideos = response.videos;
      const prevMap = prevStatusRef.current;

      if (hasLoadedOnceRef.current) {
        nextVideos.forEach((video) => {
          const hasReport = Boolean(video.reporte_pdf_url || video.reporte_txt_url);
          const prev = prevMap[video.id];
          if (video.estado === 'completed' && hasReport && (!prev || prev.estado !== 'completed' || !prev.hasReport)) {
            toast.success(`Reporte listo: ${getVideoLabel(video)}`);
          }
        });
      }

      prevStatusRef.current = Object.fromEntries(
        nextVideos.map((video) => [
          video.id,
          { estado: video.estado, hasReport: Boolean(video.reporte_pdf_url || video.reporte_txt_url) }
        ])
      );

      hasLoadedOnceRef.current = true;
      setVideos(nextVideos);
    } catch (error: any) {
      toast.error(error.message || 'Error cargando videos');
    } finally {
      setLoading(false);
    }
  };

  const getEstadoIcon = (estado: string) => {
    const estadosEnProgreso = ['uploading', 'uploaded', 'motion_detecting', 'motion_detected', 'analyzing', 'classifying', 'deep_analyzing', 'generating_report'];
    if (estadosEnProgreso.includes(estado)) {
      return <Loader2 className="w-4 h-4 animate-spin" />;
    }
    if (estado === 'completed') {
      return <CheckCircle className="w-4 h-4" />;
    }
    return null;
  };

  const handleReintentar = async (videoId: string) => {
    try {
      const res = await securityVideoService.reintentarAnalisis(videoId);
      if (res.success) {
        toast.success(res.message || 'Análisis reiniciado correctamente');
        cargarVideos();
      }
    } catch (error: any) {
      toast.error(error.message || 'Error reintentando análisis');
    }
  };

  const handleEliminar = async (videoId: string) => {
    if (!confirm('¿Estás seguro de eliminar este video? Esta acción no se puede deshacer.')) {
      return;
    }

    try {
      await securityVideoService.eliminarVideo(videoId);
      toast.success('Video eliminado correctamente');
      cargarVideos();
    } catch (error: any) {
      toast.error(error.message || 'Error eliminando video');
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
    (video) => video.estado === 'completed' && (video.reporte_pdf_url || video.reporte_txt_url)
  ).length;

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 py-8 px-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Video className="w-8 h-8 text-blue-600" />
              <div className="flex items-center gap-4">
                <div>
                  <h1 className="text-3xl font-bold text-gray-800">
                    Videos de Seguridad
                  </h1>
                  <p className="text-gray-600">
                    Sube un video y recibe el reporte cuando este listo
                  </p>
                </div>
                {readyCount > 0 && (
                  <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold bg-green-100 text-green-800">
                    Reportes listos: {readyCount}
                  </span>
                )}
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => navigate({ to: '/security/upload' })}
                className="flex items-center gap-2 bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 transition-colors"
              >
                <Plus className="w-5 h-5" />
                Subir Video
              </button>
            </div>
          </div>

          {/* Filtros */}
          <div className="flex gap-4 items-center">
            <label className="text-sm font-medium text-gray-700">Estado:</label>
            <select
              value={filtroEstado}
              onChange={(e) => setFiltroEstado(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">Todos</option>
              <option value="uploading">Subiendo al servidor</option>
              <option value="uploaded">Listo para analizar</option>
              <option value="motion_detecting">Detectando movimiento</option>
              <option value="classifying">Clasificando eventos</option>
              <option value="deep_analyzing">Análisis profundo</option>
              <option value="generating_report">Generando reporte</option>
              <option value="completed">Completado</option>
              <option value="error">Error</option>
            </select>
            <button
              onClick={cargarVideos}
              className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Actualizar
            </button>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="bg-white rounded-lg shadow-md p-12 text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4" />
            <p className="text-gray-600">Cargando videos...</p>
          </div>
        )}

        {/* Empty State */}
        {!loading && videos.length === 0 && (
          <div className="bg-white rounded-lg shadow-md p-12 text-center">
            <Video className="w-16 h-16 text-gray-400 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-gray-700 mb-2">
              No hay videos de seguridad
            </h3>
            <p className="text-gray-600 mb-6">
              Sube tu primer video de cámara de seguridad para comenzar el análisis
            </p>
            <button
              onClick={() => navigate({ to: '/security/upload' })}
              className="inline-flex items-center gap-2 bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 transition-colors"
            >
              <Plus className="w-5 h-5" />
              Subir Video
            </button>
          </div>
        )}

        {/* Lista de videos */}
        {!loading && videos.length > 0 && (
          <div className="grid gap-6">
            {videos.map((video) => (
              <div
                key={video.id}
                className="bg-white rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow"
              >
                <div className="p-6">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-1">
                      <h3 className="text-xl font-semibold text-gray-800 mb-2">
                        {getVideoLabel(video)}
                      </h3>
                      <div className="flex flex-wrap gap-4 text-sm text-gray-600">
                        {video.duracion_segundos > 0 && (
                          <div className="flex items-center gap-1">
                            <Clock className="w-4 h-4" />
                            {securityVideoService.formatDuration(video.duracion_segundos)}
                          </div>
                        )}
                      </div>
                    </div>
                    <span
                      className={`px-3 py-1 rounded-full text-sm font-medium flex items-center gap-2 ${securityVideoService.getEstadoColor(
                        video.estado
                      )}`}
                    >
                      {getEstadoIcon(video.estado)}
                      {securityVideoService.getEstadoTexto(video.estado)}
                    </span>
                  </div>

                  {/* Estadísticas */}
                  {video.estadisticas && Object.keys(video.estadisticas).length > 0 && (
                    <div className="grid grid-cols-4 gap-3 mb-4 p-4 bg-gray-50 rounded-lg">
                      <div>
                        <p className="text-xs text-gray-600">Total Eventos</p>
                        <p className="text-lg font-semibold text-gray-800">
                          {video.eventos_count || video.estadisticas.total_eventos || 0}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-600">Críticos</p>
                        <p className="text-lg font-semibold text-red-600">
                          {video.estadisticas.eventos_por_riesgo?.CRITICO || 0}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-600">Alto Riesgo</p>
                        <p className="text-lg font-semibold text-orange-600">
                          {video.estadisticas.eventos_por_riesgo?.ALTO || 0}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-600">Medio / Bajo</p>
                        <p className="text-lg font-semibold text-yellow-600">
                          {(video.estadisticas.eventos_por_riesgo?.MEDIO || 0) + (video.estadisticas.eventos_por_riesgo?.BAJO || 0)}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Alerta de eventos críticos o de alto riesgo */}
                  {video.estadisticas?.eventos_por_riesgo && (video.estadisticas.eventos_por_riesgo.CRITICO > 0 || video.estadisticas.eventos_por_riesgo.ALTO > 0) && (
                    <div className="flex items-center gap-2 p-3 bg-orange-50 border border-orange-200 rounded-lg mb-4">
                      <AlertTriangle className="w-5 h-5 text-orange-600" />
                      <span className="text-sm font-medium text-orange-800">
                        Este video tiene eventos de riesgo alto/crítico que requieren atención
                      </span>
                    </div>
                  )}

                  {/* Acciones */}
                  <div className="flex gap-3">
                    {video.estado === 'uploading' && (
                      <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg flex-1">
                        <Loader2 className="w-4 h-4 text-blue-600 animate-spin flex-shrink-0" />
                        <div className="text-sm">
                          <p className="font-medium text-blue-900">Subiendo</p>
                          <p className="text-blue-700">El archivo se esta cargando. Espera unos momentos...</p>
                        </div>
                      </div>
                    )}
                    {video.estado === 'completed' && (
                      <>
                        <button
                          onClick={() => navigate({ to: `/security/${video.id}` })}
                          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                        >
                          <FileText className="w-4 h-4" />
                          Ver Reporte
                        </button>
                        {video.reporte_pdf_url && (
                          <a
                            href={video.reporte_pdf_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                          >
                            <FileText className="w-4 h-4" />
                            Descargar PDF
                          </a>
                        )}
                      </>
                    )}
                    {video.estado === 'uploaded' && (
                      <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                        <Loader2 className="w-4 h-4 text-blue-600 animate-spin flex-shrink-0" />
                        <div className="text-sm">
                          <p className="font-medium text-blue-900">Analisis en cola</p>
                          <p className="text-blue-700">Tu video entrara a analisis automaticamente.</p>
                        </div>
                      </div>
                    )}
                    {['motion_detecting', 'motion_detected', 'analyzing', 'classifying', 'deep_analyzing', 'generating_report'].includes(
                      video.estado
                    ) && (
                        <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                          <Loader2 className="w-4 h-4 text-blue-600 animate-spin flex-shrink-0" />
                          <div className="text-sm">
                            <p className="font-medium text-blue-900">Analisis en progreso</p>
                            <p className="text-blue-700">Este proceso puede tardar 35-45 minutos. Te avisamos en la app al finalizar.</p>
                          </div>
                        </div>
                      )}
                    {video.estado === 'error' && (
                      <>
                        <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg flex-1">
                          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
                          <div className="text-sm">
                            <p className="font-medium text-red-900">Error en el análisis</p>
                            <p className="text-red-700">
                              {video.metadata_tecnico?.error || 'Ocurrió un error durante el procesamiento'}
                            </p>
                          </div>
                        </div>
                        <button
                          onClick={() => handleReintentar(video.id)}
                          className="flex items-center gap-2 px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors"
                        >
                          <RotateCcw className="w-4 h-4" />
                          Reintentar Análisis
                        </button>
                      </>
                    )}
                    <button
                      onClick={() => handleEliminar(video.id)}
                      className="ml-auto flex items-center gap-2 px-4 py-2 text-red-600 border border-red-300 rounded-lg hover:bg-red-50 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                      Eliminar
                    </button>
                  </div>

                  {/* Metadata adicional */}
                  {video.fecha_creacion && (
                    <div className="mt-4 pt-4 border-t border-gray-200 text-xs text-gray-500">
                      Creado: {formatDate(video.fecha_creacion)}
                      {video.fecha_procesamiento && (
                        <> • Procesado: {formatDate(video.fecha_procesamiento)}</>
                      )}
                      {video.tiempo_procesamiento_segundos && (
                        <> • Tiempo: {securityVideoService.formatDuration(video.tiempo_procesamiento_segundos)}</>
                      )}
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
