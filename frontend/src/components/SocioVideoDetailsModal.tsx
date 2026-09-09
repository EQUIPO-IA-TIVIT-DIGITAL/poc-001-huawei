import { useEffect, useState, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { videoService, Video } from '../services/video';
import {
    Loader2, AlertCircle, Type, Tag, CheckCircle2, XCircle, Clock,
    User, Calendar, Check, X, AlertTriangle, Eye,
    RotateCcw, Info, Timer, Hash, MessageSquare,
    Film, Sparkles, FileText, Volume2, VolumeX, Mic, AlertOctagon,
    Users, Image, Globe
} from 'lucide-react';
import { Button } from './ui/button';
import { getApiBaseUrl } from '../lib/backendUrl';

interface SocioVideoDetailsModalProps {
    video: Video | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

function resolveVideoUrl(url: string): string {
    return url.startsWith('/') ? `${getApiBaseUrl()}${url}` : url;
}

export function SocioVideoDetailsModal({ video, open, onOpenChange }: SocioVideoDetailsModalProps) {
    const [activeTab, setActiveTab] = useState<'resumen' | 'gemini' | 'audio'>('resumen');
    const videoRef = useRef<HTMLVideoElement>(null);
    const [videoUrl, setVideoUrl] = useState<string | null>(null);
    const [videoError, setVideoError] = useState(false);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (open && video) {
            setActiveTab('resumen');
            setVideoError(false);
            // Usar video_url de metadatos directamente si existe
            const metaUrl = video.metadatos_ia?.video_url || video.video_url;
            if (metaUrl) {
                setVideoUrl(resolveVideoUrl(metaUrl));
            } else {
                // Fallback: buscar URL firmada
                fetchSignedUrl(video.id);
            }
        } else {
            setVideoUrl(null);
        }
    }, [open, video]);

    const fetchSignedUrl = async (videoId: string) => {
        setLoading(true);
        try {
            const res = await videoService.getSignedUrl(videoId);
            if (res && res.signed_url) {
                setVideoUrl(resolveVideoUrl(res.signed_url));
            }
        } catch (e) {
            console.error('Error getting signed URL:', e);
        } finally {
            setLoading(false);
        }
    };

    if (!open || !video) return null;

    const metadatos = video.metadatos_ia || {};
    const geminiVision = metadatos.gemini_vision || {};
    const speechAnalysis = metadatos.speech_analysis || {};

    const getStatusBadge = () => {
        const estado = video.estado;
        const resultado = video.resultado_ia || metadatos.resultado_ia;

        if (estado === 'completado' || estado === 'aprobado' || resultado === 'APROBADO') {
            return { bg: 'bg-green-100', color: 'text-green-700', text: 'APROBADO', icon: CheckCircle2 };
        } else if (estado === 'rechazado' || resultado === 'RECHAZADO') {
            return { bg: 'bg-red-100', color: 'text-red-700', text: 'RECHAZADO', icon: XCircle };
        } else if (estado === 'en_revision' || resultado === 'REQUIERE_REVISION') {
            return { bg: 'bg-orange-100', color: 'text-orange-700', text: 'EN REVISIÓN', icon: AlertTriangle };
        } else if (estado === 'procesando') {
            return { bg: 'bg-blue-100', color: 'text-blue-700', text: 'PROCESANDO', icon: Loader2 };
        } else {
            return { bg: 'bg-gray-100', color: 'text-gray-700', text: estado?.toUpperCase() || 'PENDIENTE', icon: Clock };
        }
    };

    const status = getStatusBadge();
    const StatusIcon = status.icon;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-6xl h-[75vh] flex flex-col p-0 overflow-hidden bg-white text-gray-900 border-gray-200">

                {/* Header */}
                <DialogHeader className="px-6 py-3 bg-gray-50 border-b border-gray-200">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <DialogTitle className="text-lg font-bold text-gray-900">Detalles del Video</DialogTitle>
                            <span className={`px-2 py-1 rounded text-xs font-bold flex items-center gap-1 ${status.bg} ${status.color}`}>
                                <StatusIcon size={12} /> {status.text}
                            </span>
                        </div>
                        <DialogDescription className="text-xs text-gray-500 flex items-center gap-3">
                            <span><Hash size={10} className="inline" /> {video.id.slice(0, 8)}...</span>
                            <span><Calendar size={10} className="inline" /> {metadatos.fecha_subida ? new Date(metadatos.fecha_subida).toLocaleDateString() : 'N/A'}</span>
                        </DialogDescription>
                    </div>
                </DialogHeader>

                <div className="flex-1 flex overflow-hidden">

                    {/* LEFT: Video Player */}
                    <div className="w-3/5 flex flex-col bg-gray-100">
                        {/* Video Container - 16:9 aspect ratio */}
                        <div className="flex-1 flex items-center justify-center p-4">
                            <div className="w-full bg-gray-900 rounded-xl overflow-hidden shadow-lg" style={{ aspectRatio: '16/9' }}>
                                {loading ? (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400">
                                        <Loader2 size={48} className="animate-spin" />
                                    </div>
                                ) : !videoUrl ? (
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
                                    <div className="text-gray-900 font-medium">{metadatos.duracion_segundos || video.duracion_segundos || 0}s</div>
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
                                        className={`h-full rounded-full transition-all ${(metadatos.confianza_ia || 0) >= 0.7 ? 'bg-green-500' :
                                            (metadatos.confianza_ia || 0) >= 0.5 ? 'bg-yellow-500' : 'bg-red-500'
                                            }`}
                                        style={{ width: `${(metadatos.confianza_ia || 0) * 100}%` }}
                                    />
                                </div>
                                <span className="text-gray-900 font-bold text-sm">{Math.round((metadatos.confianza_ia || 0) * 100)}%</span>
                            </div>
                        </div>
                    </div>

                    {/* RIGHT: Tabs Panel */}
                    <div className="w-2/5 flex flex-col bg-gray-50 border-l border-gray-200">

                        {/* Tabs */}
                        <div className="flex border-b border-gray-200 bg-white">
                            {[
                                { id: 'resumen', label: 'Resumen', icon: Info },
                                { id: 'gemini', label: 'Análisis Visual', icon: Sparkles },
                                { id: 'audio', label: 'Audio', icon: Mic },
                            ].map((tab) => (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id as any)}
                                    className={`flex-1 py-2.5 text-xs font-medium flex items-center justify-center gap-1 border-b-2 transition-all ${activeTab === tab.id
                                        ? 'border-tivit-red text-tivit-red bg-red-50/50'
                                        : 'border-transparent text-gray-500 hover:text-gray-700'
                                        }`}
                                >
                                    <tab.icon size={12} />
                                    {tab.label}
                                </button>
                            ))}
                        </div>

                        {/* Content */}
                        <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-transparent hover:scrollbar-thumb-gray-400" style={{ scrollbarWidth: 'thin', scrollbarColor: '#d1d5db transparent' }}>

                            {activeTab === 'resumen' && (
                                <div className="space-y-3">
                                    {/* Resultado IA Principal */}
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
                                                    {metadatos.resultado_ia || 'PENDIENTE'}
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <div className="text-3xl font-bold text-gray-900">{Math.round((metadatos.confianza_ia || 0) * 100)}%</div>
                                                <div className="text-xs text-gray-400">Confianza</div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Título/Descripción */}
                                    <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                        <div className="text-xs text-gray-400 mb-2 flex items-center gap-1"><FileText size={10} /> Título</div>
                                        <p className="text-sm font-medium text-gray-900">{metadatos.titulo || video.descripcion || 'Sin título'}</p>
                                    </div>

                                    {/* Razón de Rechazo (si existe) */}
                                    {(metadatos.razon_rechazo || video.razon_rechazo) && (
                                        <div className="bg-red-50 rounded-xl p-4 border border-red-200">
                                            <div className="text-xs text-red-600 font-bold mb-2 flex items-center gap-1">
                                                <AlertOctagon size={12} /> Razón de Rechazo
                                            </div>
                                            <p className="text-sm text-red-800">{metadatos.razon_rechazo || video.razon_rechazo}</p>
                                        </div>
                                    )}

                                    {/* Razón de Decisión */}
                                    {metadatos.razon_decision && (
                                        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                            <div className="text-xs text-gray-400 mb-2 flex items-center gap-1"><MessageSquare size={10} /> Razón de la Decisión</div>
                                            <p className="text-sm text-gray-700">{metadatos.razon_decision}</p>
                                        </div>
                                    )}

                                    {/* Info Grid */}
                                    <div className="grid grid-cols-2 gap-2">
                                        <div className="bg-white rounded-lg p-3 shadow-sm border border-gray-100">
                                            <div className="text-xs text-gray-400">Estado</div>
                                            <div className="font-medium text-gray-900">{video.estado}</div>
                                        </div>
                                        <div className="bg-white rounded-lg p-3 shadow-sm border border-gray-100">
                                            <div className="text-xs text-gray-400">Duración</div>
                                            <div className="font-medium text-gray-900">{metadatos.duracion_segundos || video.duracion_segundos || 0}s</div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {activeTab === 'gemini' && (
                                <div className="space-y-3">
                                    {Object.keys(geminiVision).length === 0 ? (
                                        <div className="text-center py-8 text-gray-400">
                                            <Sparkles size={32} className="mx-auto mb-2 opacity-50" />
                                            <p>No hay análisis visual disponible</p>
                                        </div>
                                    ) : (
                                        <>
                                            {/* Recomendación y Score */}
                                            <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                                <div className="flex items-center justify-between mb-3">
                                                    <div className={`px-3 py-1 rounded-lg font-bold text-sm ${geminiVision.recomendacion === 'aprobar' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                                                        }`}>
                                                        {geminiVision.recomendacion?.toUpperCase() || 'N/A'}
                                                    </div>
                                                    <div className="text-right">
                                                        <div className="text-2xl font-bold text-gray-900">{geminiVision.confianza || 0}%</div>
                                                        <div className="text-xs text-gray-400">Confianza</div>
                                                    </div>
                                                </div>
                                                <div className="flex gap-3 text-sm">
                                                    <div className="flex-1 text-center p-2 bg-gray-50 rounded-lg">
                                                        <div className="text-xs text-gray-400">Seguridad</div>
                                                        <div className={`font-bold ${geminiVision.puntuacion_seguridad > 50 ? 'text-green-600' : 'text-red-600'}`}>
                                                            {geminiVision.puntuacion_seguridad || 0}%
                                                        </div>
                                                    </div>
                                                    <div className="flex-1 text-center p-2 bg-gray-50 rounded-lg">
                                                        <div className="text-xs text-gray-400">Calidad Visual</div>
                                                        <div className="font-bold text-gray-900 capitalize">{geminiVision.calidad_visual || 'N/A'}</div>
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Descripción del Contenido */}
                                            <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                                <div className="text-xs text-gray-400 mb-2">Descripción del Contenido</div>
                                                <p className="text-sm text-gray-700">{geminiVision.descripcion_contenido || 'N/A'}</p>
                                            </div>

                                            {/* Tipo y Escenario */}
                                            <div className="grid grid-cols-2 gap-3">
                                                <div className="bg-white rounded-xl p-3 shadow-sm border border-gray-100">
                                                    <div className="text-xs text-gray-400 mb-1">Tipo de Contenido</div>
                                                    <div className="font-medium text-gray-900 capitalize">{geminiVision.tipo_contenido || 'N/A'}</div>
                                                </div>
                                                <div className="bg-white rounded-xl p-3 shadow-sm border border-gray-100">
                                                    <div className="text-xs text-gray-400 mb-1">Escenario</div>
                                                    <div className="font-medium text-gray-900 text-sm">{geminiVision.escenario_principal || 'N/A'}</div>
                                                </div>
                                            </div>

                                            {/* Tags Sugeridos */}
                                            {geminiVision.tags_sugeridos?.length > 0 && (
                                                <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                                    <div className="text-xs text-gray-400 mb-2">Tags Sugeridos</div>
                                                    <div className="flex flex-wrap gap-2">
                                                        {geminiVision.tags_sugeridos.map((tag: string, i: number) => (
                                                            <span key={i} className="px-2 py-1 bg-purple-50 text-purple-700 border border-purple-200 rounded text-xs">{tag}</span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Elementos Detectados */}
                                            {geminiVision.elementos_detectados?.length > 0 && (
                                                <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                                    <div className="text-xs text-gray-400 mb-2">Elementos Detectados</div>
                                                    <div className="flex flex-wrap gap-2">
                                                        {geminiVision.elementos_detectados.map((elem: string, i: number) => (
                                                            <span key={i} className="px-2 py-1 bg-blue-50 text-blue-700 border border-blue-200 rounded text-xs">{elem}</span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </>
                                    )}
                                </div>
                            )}

                            {activeTab === 'audio' && (
                                <div className="space-y-3">
                                    {!speechAnalysis.success ? (
                                        <div className="text-center py-8 text-gray-400">
                                            <VolumeX size={32} className="mx-auto mb-2 opacity-50" />
                                            <p>No hay análisis de audio disponible</p>
                                        </div>
                                    ) : (
                                        <>
                                            {/* Audio Status */}
                                            <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                                <div className="grid grid-cols-3 gap-3 text-center">
                                                    <div className={`p-3 rounded-lg ${speechAnalysis.tiene_audio ? 'bg-green-50' : 'bg-gray-50'}`}>
                                                        <Volume2 size={20} className={`mx-auto mb-1 ${speechAnalysis.tiene_audio ? 'text-green-600' : 'text-gray-400'}`} />
                                                        <div className={`text-xs font-medium ${speechAnalysis.tiene_audio ? 'text-green-700' : 'text-gray-500'}`}>
                                                            {speechAnalysis.tiene_audio ? 'Con Audio' : 'Sin Audio'}
                                                        </div>
                                                    </div>
                                                    <div className={`p-3 rounded-lg ${speechAnalysis.tiene_voz ? 'bg-blue-50' : 'bg-gray-50'}`}>
                                                        <Mic size={20} className={`mx-auto mb-1 ${speechAnalysis.tiene_voz ? 'text-blue-600' : 'text-gray-400'}`} />
                                                        <div className={`text-xs font-medium ${speechAnalysis.tiene_voz ? 'text-blue-700' : 'text-gray-500'}`}>
                                                            {speechAnalysis.tiene_voz ? 'Con Voz' : 'Sin Voz'}
                                                        </div>
                                                    </div>
                                                    <div className="p-3 rounded-lg bg-gray-50">
                                                        <Timer size={20} className="mx-auto mb-1 text-gray-500" />
                                                        <div className="text-xs font-medium text-gray-700">
                                                            {speechAnalysis.duracion_audio || 0}s
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Transcripción */}
                                            {speechAnalysis.transcripcion && (
                                                <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                                    <div className="text-xs text-gray-400 mb-2 flex items-center justify-between">
                                                        <span>Transcripción</span>
                                                        <span className="text-green-600">{Math.round((speechAnalysis.confianza_transcripcion || 0) * 100)}% confianza</span>
                                                    </div>
                                                    <p className="text-sm text-gray-800 italic bg-gray-50 p-3 rounded-lg">"{speechAnalysis.transcripcion}"</p>
                                                </div>
                                            )}

                                            {/* Idiomas */}
                                            {speechAnalysis.idiomas_detectados?.length > 0 && (
                                                <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                                    <div className="text-xs text-gray-400 mb-2">Idiomas Detectados</div>
                                                    <div className="flex flex-wrap gap-2">
                                                        {speechAnalysis.idiomas_detectados.map((idioma: string, i: number) => (
                                                            <span key={i} className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium">{idioma}</span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Sentimiento */}
                                            {speechAnalysis.sentimiento && (
                                                <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                                                    <div className="text-xs text-gray-400 mb-2">Sentimiento</div>
                                                    <div className={`inline-flex px-3 py-1 rounded-lg font-medium text-sm ${speechAnalysis.sentimiento.interpretacion === 'positivo' ? 'bg-green-100 text-green-700' :
                                                        speechAnalysis.sentimiento.interpretacion === 'negativo' ? 'bg-red-100 text-red-700' :
                                                            'bg-gray-100 text-gray-700'
                                                        }`}>
                                                        {speechAnalysis.sentimiento.interpretacion || 'Neutral'}
                                                    </div>
                                                </div>
                                            )}
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
