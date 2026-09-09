import { useEffect, useState, useRef } from 'react';
import { useParams, Link } from '@tanstack/react-router';
import { apiRequest } from '../lib/api';
import { Loader2, AlertCircle, Video, Type, Tag, CheckCircle2, XCircle, Clock, ChevronLeft } from 'lucide-react';
import { Button } from '../components/ui/button';

interface Shot {
    start_time: number;
    end_time: number;
    start_formatted: string;
    end_formatted: string;
    shot_number: number;
}

interface VideoDetails {
    id: string;
    titulo: string;
    descripcion: string;
    estado: string;
    video_url?: string;
    fecha_carga?: string;
    fecha_procesamiento?: string;
    resultado_ia?: string;
    confianza?: number;
    razon?: string;
    analisis?: string;
    shots: Shot[];
    texto_detectado: string[];
    labels: any[];
}

export default function VideoDetailsPage() {
    const { videoId } = useParams({ from: '/app/video/$videoId' });
    const [loading, setLoading] = useState(true);
    const [details, setDetails] = useState<VideoDetails | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'summary' | 'shots' | 'text' | 'labels'>('summary');
    const videoRef = useRef<HTMLVideoElement>(null);

    useEffect(() => {
        if (videoId) {
            fetchDetails(videoId);
        }
    }, [videoId]);

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

    const jumpToTime = (time: number) => {
        if (videoRef.current) {
            videoRef.current.currentTime = time;
            videoRef.current.play();
        }
    };

    const getStatusBadge = () => {
        if (!details) return null;
        const status = details.resultado_ia || details.estado;

        if (status === 'APROBADO' || status === 'aprobado') {
            return <div className="flex items-center gap-1 bg-green-100 text-green-700 px-3 py-1 rounded-full text-xs font-bold"><CheckCircle2 size={14} /> APROBADO</div>;
        } else if (status === 'RECHAZADO' || status === 'rechazado') {
            return <div className="flex items-center gap-1 bg-red-100 text-red-700 px-3 py-1 rounded-full text-xs font-bold"><XCircle size={14} /> RECHAZADO</div>;
        } else {
            return <div className="flex items-center gap-1 bg-amber-100 text-amber-700 px-3 py-1 rounded-full text-xs font-bold"><Clock size={14} /> {status}</div>;
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-screen bg-gray-50">
                <span className="loader"></span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center h-screen bg-gray-50 text-red-500 gap-4">
                <AlertCircle size={48} />
                <p className="text-lg font-medium">{error}</p>
                <Link to="/mis-videos">
                    <Button variant="outline">Volver a mis videos</Button>
                </Link>
            </div>
        );
    }

    if (!details) return null;

    return (
        <div className="flex flex-col h-[calc(100vh-64px)] overflow-hidden bg-white text-gray-900">
            {/* Sticky Header */}
            <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-4 bg-white z-10 shrink-0">
                <Link to="/mis-videos" className="p-2 hover:bg-gray-100 rounded-full transition-colors text-gray-500 hover:text-gray-900">
                    <ChevronLeft size={24} />
                </Link>
                <div>
                    <h1 className="text-xl font-bold flex items-center gap-3">
                        {details.titulo || 'Detalles del Video'}
                        {getStatusBadge()}
                    </h1>
                    <p className="text-xs text-gray-500 mt-1">
                        ID: {videoId}
                    </p>
                </div>
            </div>

            <div className="flex-1 flex flex-col md:flex-row overflow-hidden">

                {/* LEFT: Player */}
                <div className="w-full md:w-3/5 bg-black flex flex-col relative group items-center justify-center">
                    {details.video_url ? (
                        <video
                            ref={videoRef}
                            src={details.video_url}
                            className="w-full h-full object-contain max-h-full"
                            controls
                            playsInline
                        />
                    ) : (
                        <div className="flex flex-col items-center gap-3 px-6 text-center text-gray-300">
                            <Video size={48} />
                            <p className="font-medium text-white">
                                {details.estado?.toLowerCase() === 'procesando'
                                    ? 'El video sigue procesándose.'
                                    : 'El video no está disponible.'}
                            </p>
                            <p className="text-sm text-gray-400">
                                Intenta nuevamente cuando el procesamiento haya finalizado.
                            </p>
                        </div>
                    )}
                </div>

                {/* RIGHT: Data Panels */}
                <div className="w-full md:w-2/5 flex flex-col bg-gray-50 border-l border-gray-200">

                    {/* Tabs Navigation */}
                    <div className="flex border-b border-gray-200 bg-white shrink-0">
                        <button
                            onClick={() => setActiveTab('summary')}
                            className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'summary' ? 'border-tivit-red text-tivit-red' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                        >
                            Resumen
                        </button>
                        <button
                            onClick={() => setActiveTab('shots')}
                            className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'shots' ? 'border-tivit-red text-tivit-red' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                        >
                            Tomas
                        </button>
                        <button
                            onClick={() => setActiveTab('text')}
                            className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'text' ? 'border-tivit-red text-tivit-red' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                        >
                            Texto
                        </button>
                        <button
                            onClick={() => setActiveTab('labels')}
                            className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'labels' ? 'border-tivit-red text-tivit-red' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                        >
                            Objetos
                        </button>
                    </div>

                    {/* Content Area */}
                    <div className="flex-1 overflow-y-auto p-4 space-y-4">

                        {activeTab === 'summary' && (
                            <div className="space-y-6 animate-in fade-in duration-300">

                                <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-100">
                                    <h4 className="text-xs font-bold text-gray-400 uppercase mb-2">Decisión Automatizada</h4>
                                    <p className="font-medium text-gray-900 leading-relaxed">
                                        {details.razon || "No se ha registrado una razón específica."}
                                    </p>
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div className="bg-white p-3 rounded-xl shadow-sm border border-gray-100">
                                        <p className="text-xs text-gray-400 mb-1">Confianza IA</p>
                                        <div className="flex items-end gap-1">
                                            <span className="text-2xl font-bold text-tivit-red">
                                                {Math.round((details.confianza || 0) * 100)}%
                                            </span>
                                        </div>
                                    </div>
                                    <div className="bg-white p-3 rounded-xl shadow-sm border border-gray-100">
                                        <p className="text-xs text-gray-400 mb-1">Fecha Procesamiento</p>
                                        <p className="text-sm font-bold text-gray-800">
                                            {details.fecha_procesamiento ? new Date(details.fecha_procesamiento).toLocaleDateString() : 'N/A'}
                                        </p>
                                    </div>
                                </div>

                                {details.analisis && (
                                    <div>
                                        <h4 className="text-xs font-bold text-gray-400 uppercase mb-2">Análisis Técnico</h4>
                                        <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-100 text-xs font-mono text-gray-600 leading-relaxed whitespace-pre-wrap">
                                            {details.analisis}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {activeTab === 'shots' && (
                            <div className="space-y-2 animate-in fade-in duration-300">
                                <p className="text-xs text-gray-500 mb-4 px-1">
                                    Se detectaron {details.shots?.length || 0} cambios de escena. Haz clic para navegar.
                                </p>
                                {details.shots?.map((shot, idx) => (
                                    <button
                                        key={idx}
                                        onClick={() => jumpToTime(shot.start_time)}
                                        className="w-full flex items-center justify-between p-3 bg-white hover:bg-red-50 hover:border-red-100 border border-gray-100 rounded-lg group transition-all"
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className="w-8 h-8 rounded-full bg-gray-100 text-gray-500 flex items-center justify-center font-bold text-xs group-hover:bg-red-100 group-hover:text-tivit-red transition-colors">
                                                {idx + 1}
                                            </div>
                                            <div className="flex flex-col items-start">
                                                <span className="text-sm font-bold text-gray-700 group-hover:text-tivit-red">
                                                    Escena {idx + 1}
                                                </span>
                                                <span className="text-xs text-gray-400">
                                                    Duración: {(shot.end_time - shot.start_time).toFixed(1)}s
                                                </span>
                                            </div>
                                        </div>
                                        <div className="text-xs font-mono font-medium text-gray-500 bg-gray-50 px-2 py-1 rounded">
                                            {shot.start_formatted} - {shot.end_formatted}
                                        </div>
                                    </button>
                                ))}
                                {(!details.shots || details.shots.length === 0) && (
                                    <div className="text-center py-10 text-gray-400">
                                        <Video size={32} className="mx-auto mb-2 opacity-50" />
                                        <p>No se detectaron escenas separadas.</p>
                                    </div>
                                )}
                            </div>
                        )}

                        {activeTab === 'text' && (
                            <div className="space-y-3 animate-in fade-in duration-300">
                                <p className="text-xs text-gray-500 mb-2 px-1">
                                    Texto identificado en pantalla (OCR).
                                </p>
                                {details.texto_detectado?.length > 0 ? (
                                    <div className="flex flex-wrap gap-2">
                                        {details.texto_detectado.map((txt, i) => (
                                            <div key={i} className="px-3 py-1.5 bg-white border border-gray-200 rounded-lg shadow-sm text-sm text-gray-700 flex items-center gap-2">
                                                <Type size={12} className="text-gray-400" />
                                                {txt}
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="text-center py-10 text-gray-400">
                                        <Type size={32} className="mx-auto mb-2 opacity-50" />
                                        <p>No se detectó texto en el video.</p>
                                    </div>
                                )}
                            </div>
                        )}

                        {activeTab === 'labels' && (
                            <div className="space-y-3 animate-in fade-in duration-300">
                                <p className="text-xs text-gray-500 mb-2 px-1">
                                    Objetos y etiquetas detectadas por IA.
                                </p>
                                {details.labels?.length > 0 ? (
                                    <div className="flex flex-wrap gap-2">
                                        {details.labels.map((label: any, i) => {
                                            const labelName = typeof label === 'string' ? label : label.entity?.description || label.description || 'Objeto';
                                            const confidence = typeof label === 'object' && label.confidence ? `(${Math.round(label.confidence * 100)}%)` : '';

                                            return (
                                                <div key={i} className="px-3 py-1.5 bg-blue-50 border border-blue-100 rounded-lg text-sm text-blue-700 flex items-center gap-2">
                                                    <Tag size={12} className="text-blue-400" />
                                                    {labelName} <span className="text-[10px] opacity-70">{confidence}</span>
                                                </div>
                                            );
                                        })}
                                    </div>
                                ) : (
                                    <div className="text-center py-10 text-gray-400">
                                        <Tag size={32} className="mx-auto mb-2 opacity-50" />
                                        <p>No se detectaron etiquetas específicas.</p>
                                    </div>
                                )}
                            </div>
                        )}

                    </div>
                </div>
            </div>
        </div>
    );
}
