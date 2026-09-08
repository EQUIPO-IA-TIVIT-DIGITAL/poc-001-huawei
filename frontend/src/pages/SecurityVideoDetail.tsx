import { useEffect, useState } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { toast } from 'sonner';
import { 
  obtenerVideo, 
  obtenerEventosVideo,
  SecurityVideo, 
  EventoSeguridad,
  EstadoSecurityVideo
} from '../services/securityVideoService';

export default function SecurityVideoDetail() {
  const params = useParams({ strict: false });
  const videoId = params.videoId as string;
  const navigate = useNavigate();
  
  const [video, setVideo] = useState<SecurityVideo | null>(null);
  const [eventos, setEventos] = useState<EventoSeguridad[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtroClasificacion, setFiltroClasificacion] = useState<string>('TODOS');

  useEffect(() => {
    cargarDatos();
  }, [videoId]);

  const cargarDatos = async () => {
    try {
      setLoading(true);
      const [videoData, eventosData] = await Promise.all([
        obtenerVideo(videoId),
        obtenerEventosVideo(videoId)
      ]);
      setVideo(videoData);
      setEventos(eventosData);
    } catch (error) {
      console.error('Error cargando datos:', error);
      toast.error('Error al cargar el video');
    } finally {
      setLoading(false);
    }
  };

  const getNivelRiesgo = (evento: EventoSeguridad): string => {
    return evento.nivel_riesgo || evento.analisis_detallado?.gemini_video?.nivel_riesgo || 'BAJO';
  };

  const eventosFiltrados = filtroClasificacion === 'TODOS'
    ? eventos
    : eventos.filter(e => getNivelRiesgo(e) === filtroClasificacion);

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hours > 0) return `${hours}h ${minutes}min`;
    if (minutes > 0) return `${minutes}min ${secs}s`;
    return `${secs}s`;
  };

  const formatTimestamp = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const getEstadoBadge = (estado: EstadoSecurityVideo) => {
    const badges: Record<EstadoSecurityVideo, { text: string; color: string }> = {
      [EstadoSecurityVideo.UPLOADING]: { text: 'Subiendo', color: 'bg-sky-100 text-sky-800' },
      [EstadoSecurityVideo.UPLOADED]: { text: 'Subido', color: 'bg-blue-100 text-blue-800' },
      [EstadoSecurityVideo.PROCESSING]: { text: 'Procesando', color: 'bg-yellow-100 text-yellow-800' },
      [EstadoSecurityVideo.ANALYZING]: { text: 'Analizando', color: 'bg-indigo-100 text-indigo-800' },
      [EstadoSecurityVideo.COMPLETED]: { text: 'Completado', color: 'bg-green-100 text-green-800' },
      [EstadoSecurityVideo.ERROR]: { text: 'Error', color: 'bg-red-100 text-red-800' },
      [EstadoSecurityVideo.DETECTING_MOTION]: { text: 'Detectando movimiento', color: 'bg-purple-100 text-purple-800' },
      [EstadoSecurityVideo.MOTION_DETECTED]: { text: 'Movimiento detectado', color: 'bg-purple-100 text-purple-800' },
      [EstadoSecurityVideo.CLASSIFYING]: { text: 'Clasificando', color: 'bg-indigo-100 text-indigo-800' },
      [EstadoSecurityVideo.CLASSIFIED]: { text: 'Clasificado', color: 'bg-violet-100 text-violet-800' },
      [EstadoSecurityVideo.DEEP_ANALYZING]: { text: 'Análisis profundo', color: 'bg-pink-100 text-pink-800' },
      [EstadoSecurityVideo.GENERATING_REPORT]: { text: 'Generando reporte', color: 'bg-orange-100 text-orange-800' },
    };
    const badge = badges[estado];
    return <span className={`px-3 py-1 rounded-full text-sm font-medium ${badge.color}`}>{badge.text}</span>;
  };

  const getRiesgoBadge = (nivel: string) => {
    const badges: Record<string, { text: string; color: string; icon: string }> = {
      'BAJO': { text: 'Bajo', color: 'bg-green-100 text-green-800', icon: '✓' },
      'MEDIO': { text: 'Medio', color: 'bg-yellow-100 text-yellow-800', icon: '⚡' },
      'ALTO': { text: 'Alto', color: 'bg-orange-100 text-orange-800', icon: '⚠️' },
      'CRITICO': { text: 'Crítico', color: 'bg-red-100 text-red-800', icon: '🚨' },
    };
    const badge = badges[nivel] || badges['BAJO'];
    return (
      <span className={`px-3 py-1 rounded-full text-sm font-medium ${badge.color} inline-flex items-center gap-1`}>
        <span>{badge.icon}</span> {badge.text}
      </span>
    );
  };

  const getVideoLabel = (videoData: SecurityVideo) => {
    return videoData.metadata_tecnico?.filename_original || `Video ${videoData.id}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Cargando detalles del video...</p>
        </div>
      </div>
    );
  }

  if (!video) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="text-center">
          <p className="text-gray-600">Video no encontrado</p>
          <button
            onClick={() => navigate({ to: '/security' })}
            className="mt-4 text-blue-600 hover:text-blue-800"
          >
            ← Volver al listado
          </button>
        </div>
      </div>
    );
  }

  const stats = video.estadisticas || {};
  const eventosPorRiesgo = stats.eventos_por_riesgo || {};
  const riesgoCounts = {
    critico: eventosPorRiesgo['CRITICO'] || eventos.filter(e => getNivelRiesgo(e) === 'CRITICO').length,
    alto: eventosPorRiesgo['ALTO'] || eventos.filter(e => getNivelRiesgo(e) === 'ALTO').length,
    medio: eventosPorRiesgo['MEDIO'] || eventos.filter(e => getNivelRiesgo(e) === 'MEDIO').length,
    bajo: eventosPorRiesgo['BAJO'] || eventos.filter(e => getNivelRiesgo(e) === 'BAJO').length,
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Header con navegación */}
      <div className="mb-6">
        <button
          onClick={() => navigate({ to: '/security' })}
          className="text-blue-600 hover:text-blue-800 mb-4 inline-flex items-center gap-2"
        >
          ← Volver al listado
        </button>
        <h1 className="text-3xl font-bold text-gray-900">Detalle de Video de Seguridad</h1>
      </div>

      {/* Información general del video */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-2xl font-semibold text-gray-900">{getVideoLabel(video)}</h2>
            <p className="text-gray-600">Video de seguridad</p>
          </div>
          {getEstadoBadge(video.estado)}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
          <div className="bg-gray-50 p-4 rounded-lg">
            <p className="text-sm text-gray-600">Archivo</p>
            <p className="text-lg font-semibold text-gray-900">{getVideoLabel(video)}</p>
          </div>
          <div className="bg-gray-50 p-4 rounded-lg">
            <p className="text-sm text-gray-600">Duración</p>
            <p className="text-lg font-semibold text-gray-900">{formatDuration(video.duracion_segundos)}</p>
          </div>
          {video.tiempo_procesamiento_segundos && (
            <div className="bg-gray-50 p-4 rounded-lg">
              <p className="text-sm text-gray-600">Tiempo de procesamiento</p>
              <p className="text-lg font-semibold text-gray-900">{formatDuration(video.tiempo_procesamiento_segundos)}</p>
            </div>
          )}
        </div>

        {/* Reportes */}
        {(video.reporte_txt_url || video.reporte_pdf_url) && (
          <div className="mt-6 pt-6 border-t border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900 mb-3">📄 Reportes Generados</h3>
            <div className="flex gap-3">
              {video.reporte_txt_url && (
                <a
                  href={video.reporte_txt_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                  📝 Descargar TXT
                </a>
              )}
              {video.reporte_pdf_url && (
                <a
                  href={video.reporte_pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                >
                  📄 Descargar PDF
                </a>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Estadísticas */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
        <div className="bg-white rounded-lg shadow-md p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Total Eventos</p>
              <p className="text-3xl font-bold text-blue-600">{stats.total_eventos ?? eventos.length}</p>
            </div>
            <span className="text-4xl">📊</span>
          </div>
        </div>
        <div className="bg-white rounded-lg shadow-md p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Riesgo Crítico/Alto</p>
              <p className="text-3xl font-bold text-red-600">{riesgoCounts.critico + riesgoCounts.alto}</p>
            </div>
            <span className="text-4xl">🚨</span>
          </div>
        </div>
        <div className="bg-white rounded-lg shadow-md p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Riesgo Medio</p>
              <p className="text-3xl font-bold text-yellow-600">{riesgoCounts.medio}</p>
            </div>
            <span className="text-4xl">⚡</span>
          </div>
        </div>
        <div className="bg-white rounded-lg shadow-md p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Riesgo Bajo</p>
              <p className="text-3xl font-bold text-green-600">{riesgoCounts.bajo}</p>
            </div>
            <span className="text-4xl">✓</span>
          </div>
        </div>
      </div>

      {/* Resumen ejecutivo */}
      {stats.resumen_ejecutivo && (
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-2">📋 Resumen Ejecutivo</h3>
          <p className="text-gray-700">{stats.resumen_ejecutivo}</p>
          {stats.nivel_riesgo_global && (
            <div className="mt-3 flex items-center gap-2">
              <span className="text-sm font-medium text-gray-600">Nivel de riesgo global:</span>
              {getRiesgoBadge(stats.nivel_riesgo_global)}
            </div>
          )}
          {stats.total_personas_detectadas > 0 && (
            <p className="text-sm text-gray-500 mt-2">
              👤 {stats.total_personas_detectadas} personas detectadas • 🚗 {stats.total_vehiculos_detectados || 0} vehículos detectados
            </p>
          )}
        </div>
      )}

      {/* Lista de eventos */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-semibold text-gray-900">
            Timeline de Eventos ({eventosFiltrados.length})
          </h3>
          <select
            value={filtroClasificacion}
            onChange={(e) => setFiltroClasificacion(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="TODOS">Todos los eventos</option>
            <option value="CRITICO">Riesgo Crítico</option>
            <option value="ALTO">Riesgo Alto</option>
            <option value="MEDIO">Riesgo Medio</option>
            <option value="BAJO">Riesgo Bajo</option>
          </select>
        </div>

        {eventosFiltrados.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-500">No hay eventos para mostrar</p>
          </div>
        ) : (
          <div className="space-y-4">
            {eventosFiltrados.map((evento) => (
              <div
                key={evento.id}
                className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      {getRiesgoBadge(getNivelRiesgo(evento))}
                      <span className="text-sm text-gray-600">
                        {formatTimestamp(evento.timestamp_inicio)} - {formatTimestamp(evento.timestamp_fin)}
                      </span>
                      <span className="text-sm text-gray-500">
                        ({evento.duracion.toFixed(1)}s)
                      </span>
                    </div>
                    <p className="text-gray-900">{evento.descripcion || evento.descripcion_gemini}</p>
                    {evento.confianza && (
                      <p className="text-sm text-gray-600 mt-1">
                        Confianza: {(evento.confianza * 100).toFixed(1)}%
                      </p>
                    )}
                    {(evento.personas_count > 0 || evento.vehiculos_count > 0) && (
                      <div className="flex gap-3 mt-1">
                        {evento.personas_count > 0 && (
                          <span className="text-xs text-gray-500">👤 {evento.personas_count} persona(s)</span>
                        )}
                        {evento.vehiculos_count > 0 && (
                          <span className="text-xs text-gray-500">🚗 {evento.vehiculos_count} vehículo(s)</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Análisis detallado */}
                {evento.analisis_detallado && Object.keys(evento.analisis_detallado).length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-200">
                    <p className="text-sm font-semibold text-gray-700 mb-2">🔍 Análisis Detallado:</p>
                    <div className="bg-gray-50 p-3 rounded text-sm text-gray-700">
                      <pre className="whitespace-pre-wrap font-mono text-xs">
                        {JSON.stringify(evento.analisis_detallado, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}
                {/* Fallback: análisis profundo (legacy) */}
                {!evento.analisis_detallado && evento.analisis_profundo && Object.keys(evento.analisis_profundo).length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-200">
                    <p className="text-sm font-semibold text-gray-700 mb-2">🔍 Análisis Profundo:</p>
                    <div className="bg-gray-50 p-3 rounded text-sm text-gray-700">
                      <pre className="whitespace-pre-wrap font-mono text-xs">
                        {JSON.stringify(evento.analisis_profundo, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}

                {/* Clip */}
                {evento.clip_url && (
                  <div className="mt-3">
                    <a
                      href={evento.clip_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-600 hover:text-blue-800 inline-flex items-center gap-1"
                    >
                      🎬 Ver clip del evento →
                    </a>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
