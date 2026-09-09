import { useEffect, useState, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { apiRequest } from '../lib/api';
import { getApiBaseUrl } from '../lib/backendUrl';
import {
    Loader2, AlertCircle, Video, Type, Tag, CheckCircle2, XCircle, Clock,
    RotateCcw, Info, Timer, Hash, MessageSquare, Film, Sparkles, FileText,
    Volume2, AlertTriangle, Mic, Calendar, Image, Eye, Shield, Zap,
    Users, Globe, VolumeX, AlertOctagon
} from 'lucide-react';
import { Button } from './ui/button';

interface VideoDetailsModalProps {
    videoId: string | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

interface VideoShot {
    start_time?: string;
    end_time?: string;
    startTimeOffset?: string;
    endTimeOffset?: string;
    start_formatted?: string;
    end_formatted?: string;
}

interface VideoLabel {
    entity?: string;
    categoria?: string;
    confianza?: number;
    description?: string;
    categoryEntities?: Array<{ description?: string }>;
    segments?: Array<{ segment?: { startTimeOffset?: string; endTimeOffset?: string }; confidence?: number }>;
}

interface VideoLogo {
    entity?: string;
    description?: string;
    confianza?: number;
    tracks?: Array<{
        segment?: { startTimeOffset?: string; endTimeOffset?: string };
        confidence?: number;
    }>;
}

interface ExplicitContent {
    pornographyLikelihood?: string;
    frames?: Array<{
        timeOffset?: string;
        pornographyLikelihood?: string;
    }>;
}

interface VideoDetails {
    id: string;
    titulo: string;
    descripcion: string;
    estado: string;
    fecha_carga?: string;
    fecha_procesamiento?: string;
    resultado_ia?: string;
    confianza?: number;
    razon?: string;
    razon_rechazo?: string;
    analisis?: string;
    video_url?: string;
    duracion_segundos?: number;
    shots: VideoShot[];
    texto_detectado: string[];
    labels: VideoLabel[];
    metadatos_ia?: {
        titulo?: string;
        nombre_archivo?: string;
        duracion_segundos?: number;
        storage_uri?: string;
        video_url?: string;
        thumbnail_generado?: boolean;
        fecha_subida?: string;
        resultado_ia?: string;
        confianza_ia?: number;
        razon_decision?: string;
        razon_rechazo?: string;
        analisis_ia?: string;
        gemini_vision?: {
            recomendacion?: string;
            confianza?: number;
            puntuacion_seguridad?: number;
            personas_detectadas?: number;
            descripcion_contenido?: string;
            razon_recomendacion?: string;
            alertas_criticas?: string[];
            banderas_rojas?: string[];
            elementos_detectados?: string[];
            tags_sugeridos?: string[];
            tipo_contenido?: string;
            escenario_principal?: string;
            calidad_visual?: string;
            autenticidad?: number;
        };
        speech_analysis?: {
            success?: boolean;
            tiene_audio?: boolean;
            tiene_voz?: boolean;
            transcripcion?: string;
            confianza_transcripcion?: number;
            duracion_audio?: number;
            idiomas_detectados?: string[];
            palabras_prohibidas?: string[];
            sentimiento?: {
                interpretacion?: string;
                score?: number;
                magnitud?: number;
            };
        };
        decision_deepseek?: {
            aprobado?: boolean;
            confianza?: number;
            razon?: string;
            analisis?: string;
            factores_decision?: string[];
        };
        video_intelligence?: {
            labels?: VideoLabel[];
            shots?: VideoShot[];
            text?: string[];
            logos?: VideoLogo[];
            explicit_content?: ExplicitContent;
        };
    };
}

export function VideoDetailsModal({ videoId, open, onOpenChange }: VideoDetailsModalProps) {
    const [loading, setLoading] = useState(true);
    const [details, setDetails] = useState<VideoDetails | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'resumen'>('resumen');
    const videoRef = useRef<HTMLVideoElement>(null);
    const [videoError, setVideoError] = useState(false);

    useEffect(() => {
        if (open && videoId) {
            fetchDetails(videoId);
            setActiveTab('resumen');
            setVideoError(false);
        } else {
            setDetails(null);
            setLoading(true);
        }
    }, [open, videoId]);

    const fetchDetails = async (id: string) => {
        setLoading(true);
        setError(null);
        try {
            const response = await apiRequest<{ success: boolean; video: VideoDetails }>(`/socio/video/${id}/details`);
            if (response?.success) {
                setDetails(response.video);
            } else {
                setError('No se pudieron cargar los detalles del video.');
            }
        } catch (e) {
            console.error(e);
            if (e instanceof Error && e.message) {
                setError(e.message);
            } else {
                setError('Error de conexión al obtener detalles.');
            }
        } finally {
            setLoading(false);
        }
    };

    const getStatusBadge = () => {
        if (!details) return { bg: 'bg-gray-100', color: 'text-gray-700', text: 'PENDIENTE', icon: Clock };
        const status = details.resultado_ia || details.estado;

        if (status === 'APROBADO' || status === 'aprobado' || status === 'completado') {
            return { bg: 'bg-green-100', color: 'text-green-700', text: 'APROBADO', icon: CheckCircle2 };
        } else if (status === 'RECHAZADO' || status === 'rechazado') {
            return { bg: 'bg-red-100', color: 'text-red-700', text: 'RECHAZADO', icon: XCircle };
        } else if (status === 'en_revision' || status === 'REQUIERE_REVISION') {
            return { bg: 'bg-orange-100', color: 'text-orange-700', text: 'EN REVISIÓN', icon: AlertTriangle };
        } else if (status === 'procesando') {
            return { bg: 'bg-blue-100', color: 'text-blue-700', text: 'PROCESANDO', icon: Loader2 };
        } else {
            return { bg: 'bg-gray-100', color: 'text-gray-700', text: status?.toUpperCase() || 'PENDIENTE', icon: Clock };
        }
    };

    if (!open) return null;

    const status = getStatusBadge();
    const StatusIcon = status.icon;
    const metadatos = details?.metadatos_ia || {};
    const geminiVision = metadatos.gemini_vision || {};
    const speechAnalysis = metadatos.speech_analysis || {};
    const _rawVideoUrl = metadatos.video_url || details?.video_url;
    const _apiBase = getApiBaseUrl();
    const videoUrl = _rawVideoUrl
        ? (_rawVideoUrl.startsWith('/') ? `${_apiBase}${_rawVideoUrl}` : _rawVideoUrl)
        : null;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-6xl h-[75vh] flex flex-col p-0 overflow-hidden bg-white text-gray-900 border-gray-200">

                {/* Header */}
                <DialogHeader className="px-6 py-3 bg-gray-50 border-b border-gray-200">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <DialogTitle className="text-lg font-bold text-gray-900">
                                {loading ? 'Cargando...' : 'Detalles del Video'}
                            </DialogTitle>
                            {!loading && details && (
                                <span className={`px-2 py-1 rounded text-xs font-bold flex items-center gap-1 ${status.bg} ${status.color}`}>
                                    <StatusIcon size={12} /> {status.text}
                                </span>
                            )}
                        </div>
                        <DialogDescription className="text-xs text-gray-500 flex items-center gap-3 pr-6">
                            <span><Hash size={10} className="inline" /> {videoId?.slice(0, 8)}...</span>
                        </DialogDescription>
                    </div>
                </DialogHeader>

                {loading ? (
                    <div className="flex-1 flex items-center justify-center bg-gray-50">
                        <span className="loader"></span>
                    </div>
                ) : error ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-red-500 gap-3 bg-gray-50">
                        <AlertCircle size={48} />
                        <p className="font-medium">{error}</p>
                        <Button variant="outline" onClick={() => fetchDetails(videoId!)}>
                            <RotateCcw size={14} className="mr-2" /> Reintentar
                        </Button>
                    </div>
                ) : details ? (
                    <div className="flex-1 flex overflow-hidden">

                        {/* LEFT: Video Player */}
                        <div className="w-3/5 flex flex-col bg-gray-100">
                            {/* Video Container - 16:9 aspect ratio */}
                            <div className="flex-1 flex items-center justify-center p-4">
                                <div className="w-full bg-gray-900 rounded-xl overflow-hidden shadow-lg" style={{ aspectRatio: '16/9' }}>
                                    {!videoUrl ? (
                                        <div className="w-full h-full flex items-center justify-center text-gray-400">
                                            <div className="text-center">
                                                <AlertCircle size={48} className="mx-auto mb-2" />
                                                <p>Video no disponible</p>
                                            </div>
                                        </div>
                                    ) : videoError ? (
                                        <div className="w-full h-full flex items-center justify-center text-gray-400">
                                            <div className="text-center">
                                                <AlertCircle size={48} className="mx-auto mb-2 text-red-500" />
                                                <p>Error al cargar video</p>
                                                <Button variant="outline" size="sm" className="mt-2" onClick={() => setVideoError(false)}>
                                                    <RotateCcw size={14} className="mr-1" /> Reintentar
                                                </Button>
                                            </div>
                                        </div>
                                    ) : (
                                        <video
                                            ref={videoRef}
                                            src={videoUrl}
                                            className="w-full h-full object-contain bg-black"
                                            controls
                                            playsInline
                                            crossOrigin="use-credentials"
                                            onError={() => setVideoError(true)}
                                        />
                                    )}
                                </div>
                            </div>

                            {/* Video Properties Bar */}
                            <div className="bg-white border-t border-gray-200 p-3">
                                <div className="grid grid-cols-4 gap-3 text-xs">
                                    <div className="bg-gray-50 rounded-lg p-2 border border-gray-100">
                                        <div className="text-gray-400 flex items-center gap-1 mb-1"><Film size={10} /> Archivo</div>
                                        <div className="text-gray-900 font-medium truncate">{metadatos.nombre_archivo || 'N/A'}</div>
                                    </div>
                                    <div className="bg-gray-50 rounded-lg p-2 border border-gray-100">
                                        <div className="text-gray-400 flex items-center gap-1 mb-1"><Timer size={10} /> Duración</div>
                                        <div className="text-gray-900 font-medium">{metadatos.duracion_segundos || details.duracion_segundos || 0}s</div>
                                    </div>
                                    <div className="bg-gray-50 rounded-lg p-2 border border-gray-100">
                                        <div className="text-gray-400 flex items-center gap-1 mb-1"><Image size={10} /> Thumbnail</div>
                                        <div className={`font-medium ${metadatos.thumbnail_generado ? 'text-green-600' : 'text-red-500'}`}>
                                            {metadatos.thumbnail_generado ? 'Generado' : 'No'}
                                        </div>
                                    </div>
                                    <div className="bg-gray-50 rounded-lg p-2 border border-gray-100">
                                        <div className="text-gray-400 flex items-center gap-1 mb-1"><Volume2 size={10} /> Audio</div>
                                        <div className={`font-medium ${speechAnalysis.tiene_audio ? 'text-green-600' : 'text-gray-500'}`}>
                                            {speechAnalysis.tiene_audio ? (speechAnalysis.tiene_voz ? 'Con voz' : 'Sin voz') : 'Sin audio'}
                                        </div>
                                    </div>
                                </div>

                                {/* Confidence Bar */}
                                <div className="mt-3 flex items-center gap-3">
                                    <span className="text-xs text-gray-500">Confianza IA:</span>
                                    <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                                        <div
                                            className={`h-full rounded-full transition-all ${(metadatos.confianza_ia || details.confianza || 0) >= 0.7 ? 'bg-green-500' :
                                                (metadatos.confianza_ia || details.confianza || 0) >= 0.5 ? 'bg-yellow-500' : 'bg-red-500'
                                                }`}
                                            style={{ width: `${(metadatos.confianza_ia || details.confianza || 0) * 100}%` }}
                                        />
                                    </div>
                                    <span className="text-gray-900 font-bold text-sm">{Math.round((metadatos.confianza_ia || details.confianza || 0) * 100)}%</span>
                                </div>
                            </div>
                        </div>

                        {/* RIGHT: Tabs Panel */}
                        <div className="w-2/5 flex flex-col bg-gray-50 border-l border-gray-200">



                            {/* Content */}
                            <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-transparent hover:scrollbar-thumb-gray-400" style={{ scrollbarWidth: 'thin', scrollbarColor: '#d1d5db transparent' }}>

                                {activeTab === 'resumen' && (
                                    <div className="space-y-3">
                                        {/* Resultado Principal */}
                                        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                            <div className="flex items-center justify-between">
                                                <div>
                                                    <div className="text-xs text-gray-400 mb-1">Resultado del Análisis</div>
                                                    <div className={`inline-flex items-center gap-1 px-3 py-1 rounded-lg font-bold ${metadatos.resultado_ia === 'APROBADO' ? 'bg-green-100 text-green-700' :
                                                        metadatos.resultado_ia === 'RECHAZADO' ? 'bg-red-100 text-red-700' :
                                                            'bg-orange-100 text-orange-700'
                                                        }`}>
                                                        {metadatos.resultado_ia === 'APROBADO' ? <CheckCircle2 size={14} /> :
                                                            metadatos.resultado_ia === 'RECHAZADO' ? <XCircle size={14} /> :
                                                                <AlertTriangle size={14} />}
                                                        {metadatos.resultado_ia || status.text}
                                                    </div>
                                                </div>
                                                <div className="text-right">
                                                    <div className="text-3xl font-bold text-gray-900">{Math.round((metadatos.confianza_ia || details.confianza || 0) * 100)}%</div>
                                                    <div className="text-xs text-gray-400">Confianza</div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Título */}
                                        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                            <div className="text-xs text-gray-400 mb-2 flex items-center gap-1"><FileText size={10} /> Título</div>
                                            <p className="text-sm font-medium text-gray-900">{details.titulo || 'Sin título'}</p>
                                        </div>

                                        {/* Razón de Rechazo (si existe) */}
                                        {(metadatos.razon_rechazo || details.razon_rechazo) && (
                                            <div className="bg-red-50 rounded-xl p-4 border border-red-200">
                                                <div className="text-xs text-red-600 font-bold mb-2 flex items-center gap-1">
                                                    <AlertOctagon size={12} /> Razón de Rechazo
                                                </div>
                                                <p className="text-sm text-red-800">{metadatos.razon_rechazo || details.razon_rechazo}</p>
                                            </div>
                                        )}

                                        {/* Razón de Decisión */}
                                        {metadatos.razon_decision && (
                                            <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                                <div className="text-xs text-gray-400 mb-2 flex items-center gap-1"><MessageSquare size={10} /> Decisión</div>
                                                <p className="text-sm text-gray-700">{metadatos.razon_decision}</p>
                                            </div>
                                        )}

                                        {/* Info Grid */}
                                        <div className="grid grid-cols-2 gap-2">
                                            <div className="bg-white rounded-lg p-3 shadow-sm border border-gray-100">
                                                <div className="text-xs text-gray-400">Estado</div>
                                                <div className="font-medium text-gray-900 capitalize">{details.estado}</div>
                                            </div>
                                            <div className="bg-white rounded-lg p-3 shadow-sm border border-gray-100">
                                                <div className="text-xs text-gray-400">Duración</div>
                                                <div className="font-medium text-gray-900">{metadatos.duracion_segundos || details.duracion_segundos || 0}s</div>
                                            </div>
                                        </div>
                                    </div>
                                )}


                            </div>
                        </div>
                    </div>
                ) : null}
            </DialogContent>
        </Dialog>
    );
}
