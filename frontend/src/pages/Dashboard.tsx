import { useState, useEffect } from 'react';
import { Link } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import {
    Video,
    Clock,
    CheckCircle,
    XCircle,
    Play,
    PlaySquare,
    CheckCircle2,
    Timer,
    Sparkles,
    CloudUpload,
    FolderKanban,
    Shield,
    Activity,
    ArrowRight,
    TrendingUp,
    Eye,
    Plus,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { apiRequest } from '../lib/api';
import { VideoDetailsModal } from '../components/VideoDetailsModal';
import { DonutChart } from '../components/dashboard/DonutChart';
import { StatsCard } from '../components/dashboard/StatsCard';
import { toast } from 'sonner';

interface VideoData {
    id: string;
    titulo: string;
    descripcion: string;
    estado: string;
    fecha_subida?: string;
    resultado_ia?: string;
    thumbnail_url?: string;
}

type VideoUiState = 'uploading' | 'processing' | 'approved' | 'rejected';

interface DashboardVideo extends VideoData {
    uiState: VideoUiState;
}

interface Stats {
    total: number;
    aprobados: number;
    pendientes: number;
    rechazados: number;
}

export default function Dashboard() {
    const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [isTabVisible, setIsTabVisible] = useState(() => !document.hidden);
    const { user } = useAuth();

    const resolveVideoUiState = (video: VideoData): VideoUiState => {
        const unifiedStatus = `${video.resultado_ia || ''} ${video.estado || ''}`.toUpperCase();

        if (
            ['RECHAZADO', 'ERROR', 'FALLIDO', 'FAILED'].some((status) =>
                unifiedStatus.includes(status),
            )
        ) {
            return 'rejected';
        }

        if (
            ['APROBADO', 'COMPLETADO', 'FINALIZADO', 'DONE'].some((status) =>
                unifiedStatus.includes(status),
            )
        ) {
            return 'approved';
        }

        if (
            ['SUBIENDO', 'UPLOADING', 'UPLOAD'].some((status) => unifiedStatus.includes(status))
        ) {
            return 'uploading';
        }

        return 'processing';
    };

    useEffect(() => {
        const onVisibilityChange = () => setIsTabVisible(!document.hidden);
        document.addEventListener('visibilitychange', onVisibilityChange);
        return () => document.removeEventListener('visibilitychange', onVisibilityChange);
    }, []);

    // Fetch projects count
    const { data: projectCount = 0 } = useQuery({
        queryKey: ['dashboard-projects'],
        queryFn: async () => {
            const response = await apiRequest<{ success: boolean; workspaces: any[] }>(
                '/workspaces',
            );
            return response?.success ? response.workspaces.length : 0;
        },
    });

    // Fetch videos and stats with polling
    const {
        data: { videos, stats } = {
            videos: [] as DashboardVideo[],
            stats: { total: 0, aprobados: 0, pendientes: 0, rechazados: 0 },
        },
        isLoading,
    } = useQuery({
        queryKey: ['dashboard-videos'],
        queryFn: async () => {
            const response = await apiRequest<{ success: boolean; videos: VideoData[] }>(
                '/socio/mis-videos',
            );
            const videosData = response?.success ? response.videos : [];
            const dashboardVideos = videosData.map((video) => ({
                ...video,
                uiState: resolveVideoUiState(video),
            }));

            const total = dashboardVideos.length;
            const aprobados = dashboardVideos.filter((v) => v.uiState === 'approved').length;
            const pendientes = dashboardVideos.filter(
                (v) => v.uiState === 'processing' || v.uiState === 'uploading',
            ).length;
            const rechazados = dashboardVideos.filter((v) => v.uiState === 'rejected').length;

            return {
                videos: dashboardVideos,
                stats: { total, aprobados, pendientes, rechazados },
            };
        },
        enabled: true,
        refetchInterval: (query) => {
            if (!isTabVisible) return false;
            const hasPendingWork = query.state.data?.videos?.some(
                (video: DashboardVideo) =>
                    video.uiState === 'processing' || video.uiState === 'uploading',
            );
            return hasPendingWork ? 15000 : false;
        },
        refetchIntervalInBackground: false,
    });

    const isVideoFinalized = (video: DashboardVideo) =>
        video.uiState === 'approved' || video.uiState === 'rejected';

    const handleVideoClick = (video: DashboardVideo) => {
        if (!isVideoFinalized(video)) {
            toast.info('El detalle estará disponible cuando finalice el análisis.');
            return;
        }

        setSelectedVideoId(video.id);
        setIsModalOpen(true);
    };

    const getVideoTitle = (video: DashboardVideo) => {
        const t = video.titulo?.trim();
        if (t && !/^video\s*de\s*$/i.test(t) && t.length > 0) return t;
        const d = video.descripcion?.trim();
        if (d && d.length > 0) return d;
        if (video.id) return `Video #${video.id.slice(0, 6)}`;
        return 'Título no disponible';
    };

    const getVideoDate = (dateString?: string) => {
        if (!dateString) return 'Procesando...';
        try {
            const date = new Date(dateString);
            if (isNaN(date.getTime())) return 'Procesando...';
            return date.toLocaleDateString('es-ES', { day: 'numeric', month: 'short' });
        } catch {
            return 'Procesando...';
        }
    };

    const getVideoStatusColor = (video: DashboardVideo) => {
        if (video.uiState === 'approved') return 'emerald';
        if (video.uiState === 'rejected') return 'rose';
        if (video.uiState === 'uploading') return 'sky';
        return 'amber';
    };

    const getStatusBadge = (video: DashboardVideo) => {
        const base = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold tracking-wide shadow-sm border';
        switch (video.uiState) {
            case 'approved':
                return (
                    <span className={`${base} bg-emerald-50 text-emerald-700 border-emerald-200/60`}>
                        <CheckCircle size={14} /> Aprobado
                    </span>
                );
            case 'rejected':
                return (
                    <span className={`${base} bg-rose-50 text-rose-700 border-rose-200/60`}>
                        <XCircle size={14} /> Rechazado
                    </span>
                );
            case 'uploading':
                return (
                    <span className={`${base} bg-sky-50 text-sky-700 border-sky-200/60`}>
                        <CloudUpload size={14} /> Subiendo
                    </span>
                );
            default:
                return (
                    <span className={`${base} bg-amber-50 text-amber-700 border-amber-200/60 animate-pulse`}>
                        <Clock size={14} /> Analizando
                    </span>
                );
        }
    };

    if (isLoading) {
        return (
            <div className="flex flex-col justify-center items-center h-[60vh] gap-3">
                <div className="animate-spin rounded-full h-10 w-10 border-2 border-gray-200 border-t-tivit-red" />
                <span className="text-sm text-gray-400 font-medium">Cargando dashboard...</span>
            </div>
        );
    }

    const greeting = (() => {
        const h = new Date().getHours();
        if (h < 12) return { text: 'Buenos días', emoji: '☀️' };
        if (h < 18) return { text: 'Buenas tardes', emoji: '🌤️' };
        return { text: 'Buenas noches', emoji: '🌙' };
    })();

    const firstName = user?.nombre_completo?.split(' ')[0] || 'Usuario';

    return (
        <div className="space-y-8 max-w-7xl mx-auto">
            {/* Welcome Banner with integrated CTA */}
            <div className="relative bg-white rounded-3xl border border-slate-100 shadow-sm p-8 md:p-10 mb-6 overflow-hidden">
                {/* Soft Glow Background */}
                <div className="absolute top-0 right-0 w-80 h-80 rounded-full blur-3xl -mr-20 -mt-20 opacity-30 pointer-events-none bg-blue-50" />
                <div className="absolute bottom-0 left-0 w-64 h-64 rounded-full blur-3xl -ml-20 -mb-20 pointer-events-none bg-rose-50" />
                <div className="absolute top-4 right-8 opacity-[0.02] text-slate-900">
                    <Sparkles size={180} />
                </div>

                <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
                    <div>
                        <div className="flex items-center gap-3 mb-2">
                            <span className="text-3xl">{greeting.emoji}</span>
                            <span className="text-[13px] font-bold tracking-wide text-slate-500 uppercase bg-slate-50 px-3 py-1 rounded-full border border-slate-100 shadow-sm">
                                {new Date().toLocaleDateString('es-ES', {
                                    weekday: 'long',
                                    day: 'numeric',
                                    month: 'long',
                                })}
                            </span>
                        </div>
                        <h1 className="text-3xl md:text-3xl font-bold text-slate-800 mt-3 tracking-tight">
                            {greeting.text},{' '}
                            <span className="text-blue-600">
                                {firstName}
                            </span>
                        </h1>
                        <p className="text-slate-500 text-[15px] mt-2 max-w-xl leading-relaxed">
                            {stats.total > 0
                                ? `Tienes ${stats.total} video${stats.total !== 1 ? 's' : ''} en tu biblioteca. Sube más para análisis automáticos con Inteligencia Artificial.`
                                : 'Comienza subiendo tu primer video para análisis con IA.'}
                        </p>
                    </div>
                    {/* Primary CTA */}
                    <div className="flex items-center shrink-0 mt-4 md:mt-0">
                        <Link
                            to="/upload"
                            className="group flex items-center gap-2.5 px-6 py-3.5 bg-slate-800 text-white text-[15px] font-semibold rounded-full shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all duration-300 ring-1 ring-slate-900/5 hover:bg-slate-700"
                        >
                            <Plus size={18} className="text-slate-200" />
                            Subir Nuevo Video
                            <ArrowRight
                                size={16}
                                className="opacity-70 group-hover:opacity-100 group-hover:translate-x-1 transition-all"
                            />
                        </Link>
                    </div>
                </div>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
                <StatsCard
                    title="Total Videos"
                    total={stats.total}
                    value={stats.total}
                    icon={PlaySquare}
                    bgFrom="from-blue-500"
                    bgTo="to-cyan-400"
                    iconBg="bg-gradient-to-br from-blue-500 to-cyan-400"
                    delay={0}
                    hideProgress
                />
                <StatsCard
                    title="Proyectos"
                    total={projectCount}
                    value={projectCount}
                    icon={FolderKanban}
                    bgFrom="from-violet-500"
                    bgTo="to-purple-400"
                    iconBg="bg-gradient-to-br from-violet-500 to-purple-400"
                    delay={80}
                    hideProgress
                />
                <StatsCard
                    title="Aprobados"
                    total={stats.total}
                    value={stats.aprobados}
                    icon={CheckCircle2}
                    bgFrom="from-emerald-500"
                    bgTo="to-green-400"
                    iconBg="bg-gradient-to-br from-emerald-500 to-green-400"
                    delay={160}
                />
                <StatsCard
                    title="Pendientes"
                    total={stats.total}
                    value={stats.pendientes}
                    icon={Timer}
                    bgFrom="from-amber-500"
                    bgTo="to-yellow-400"
                    iconBg="bg-gradient-to-br from-amber-500 to-yellow-400"
                    delay={240}
                />
            </div>

            {/* Quick Actions - 3 items */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 md:gap-4">
                {[
                    {
                        to: '/proyectos',
                        icon: FolderKanban,
                        label: 'Proyectos',
                        desc: 'Organiza tu trabajo',
                        color: 'from-sky-500 to-blue-400',
                    },
                    {
                        to: '/security',
                        icon: Shield,
                        label: 'Análisis Seguridad',
                        desc: 'Detección de anomalías',
                        color: 'from-emerald-500 to-teal-400',
                    },
                    {
                        to: '/operational',
                        icon: Activity,
                        label: 'Análisis Operativo',
                        desc: 'Monitoreo en tiempo real',
                        color: 'from-orange-500 to-amber-400',
                    },
                ].map((action, i) => (
                    <Link
                        key={action.to}
                        to={action.to}
                        className="group relative flex items-center gap-4 p-5 rounded-3xl bg-white border border-slate-200/60 shadow-sm hover:border-slate-300 transition-all duration-300 hover:shadow-md hover:-translate-y-1 animate-in fade-in slide-in-from-bottom-4"
                        style={{ animationDelay: `${300 + i * 60}ms` }}
                    >
                        <div
                            className={`p-3 rounded-[1.25rem] bg-gradient-to-br ${action.color} shadow-sm shrink-0 bg-opacity-10`}
                        >
                            <action.icon size={20} className="text-white drop-shadow-sm" strokeWidth={2.5} />
                        </div>
                        <div className="min-w-0 flex-1">
                            <p className="text-[15px] font-bold text-slate-800 group-hover:text-blue-600 transition-colors truncate">
                                {action.label}
                            </p>
                            <p className="text-xs text-slate-500 font-medium truncate mt-0.5">{action.desc}</p>
                        </div>
                        <ArrowRight
                            size={18}
                            className="text-slate-300 group-hover:text-blue-500 group-hover:translate-x-1 transition-all shrink-0"
                        />
                    </Link>
                ))}
            </div>

            {/* Content Grid: Videos + Side Panel */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch">
                {/* Recent Videos - 2 cols */}
                <div className="lg:col-span-2 flex flex-col gap-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <h2 className="text-lg font-bold text-gray-900">Videos Recientes</h2>
                            <span className="text-[10px] text-gray-400 bg-gray-100 px-2.5 py-0.5 rounded-full font-semibold">
                                {videos.length}
                            </span>
                        </div>
                        {videos.length > 0 && (
                            <Link
                                to="/mis-videos"
                                className="flex items-center gap-1 text-xs font-semibold text-gray-400 hover:text-tivit-red transition-colors"
                            >
                                Ver todos <ArrowRight size={12} />
                            </Link>
                        )}
                    </div>

                    {videos.length === 0 ? (
                        <div className="relative overflow-hidden flex-1 rounded-2xl p-10 text-center bg-gradient-to-br from-gray-50 via-white to-gray-50 border border-gray-100 shadow-sm flex flex-col items-center justify-center">
                            <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(227,6,19,0.03),transparent_70%)]" />
                            <div className="relative">
                                <div className="mx-auto w-16 h-16 bg-gradient-to-br from-gray-100 to-gray-200 rounded-2xl flex items-center justify-center mb-4 shadow-inner">
                                    <Video size={28} className="text-gray-400" />
                                </div>
                                <h3 className="text-base font-bold text-gray-700 mb-1">
                                    No tienes videos aún
                                </h3>
                                <p className="text-sm text-gray-400 mb-4">
                                    Sube tu primer video para que nuestra IA lo analice
                                </p>
                                <Link
                                    to="/upload"
                                    className="inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-tivit-red to-rose-500 text-white text-sm font-semibold rounded-xl hover:shadow-lg hover:shadow-red-200 transition-all duration-200"
                                >
                                    <CloudUpload size={16} /> Subir Video
                                </Link>
                            </div>
                        </div>
                    ) : (
                        <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-3 content-start">
                            {videos.slice(0, 4).map((video, index) => (
                                <div
                                    key={video.id}
                                    className="group relative rounded-3xl overflow-hidden bg-white border border-slate-200/60 shadow-sm hover:shadow-md transition-all duration-300 hover:-translate-y-1 cursor-pointer animate-in fade-in slide-in-from-bottom-4"
                                    style={{ animationDelay: `${400 + index * 80}ms` }}
                                    onClick={() => handleVideoClick(video)}
                                >
                                    <div className="relative aspect-[16/10] bg-slate-100 overflow-hidden">
                                        <img
                                            crossOrigin="use-credentials"
                                            src={`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001'}/socio/thumbnail/${video.id}`}
                                            alt={getVideoTitle(video)}
                                            className="absolute inset-0 w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
                                            onError={(e) => {
                                                e.currentTarget.style.display = 'none';
                                            }}
                                        />
                                        {/* Status badge */}
                                        <div className="absolute top-4 right-4 z-20">
                                            {getStatusBadge(video)}
                                        </div>

                                        {/* Gradient overly for text readability */}
                                        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent z-10 transition-opacity duration-300 group-hover:from-black/90" />
                                        
                                        {/* Play button */}
                                        <div className="absolute inset-0 flex items-center justify-center z-[15]">
                                            <div className="w-14 h-14 bg-white/20 rounded-full flex items-center justify-center backdrop-blur-md opacity-0 group-hover:opacity-100 scale-75 group-hover:scale-100 transition-all duration-300 shadow-xl border border-white/30">
                                                <Play
                                                    size={24}
                                                    className="text-white ml-1"
                                                    fill="currentColor"
                                                />
                                            </div>
                                        </div>
                                        
                                        {/* Fallback icon */}
                                        <div className="absolute inset-0 flex items-center justify-center z-0">
                                            <Video size={32} className="text-slate-300" />
                                        </div>
                                        
                                        {/* Title area */}
                                        <div className="absolute bottom-0 left-0 right-0 p-5 z-20">
                                            <h3 className="font-bold text-white text-[15px] line-clamp-1 mb-1">
                                                {getVideoTitle(video)}
                                            </h3>
                                            <div className="flex items-center gap-1.5 text-xs font-medium text-slate-300">
                                                <Clock size={12} />
                                                <span>
                                                    {getVideoDate(video.fecha_subida)}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Side Panel */}
                <div className="flex flex-col gap-4">
                    <div className="bg-white rounded-3xl border border-slate-200/60 shadow-sm p-6 overflow-hidden relative">
                        <div className="absolute top-0 right-0 w-32 h-32 rounded-full blur-2xl -mr-10 -mt-10 opacity-30 pointer-events-none bg-blue-50" />
                        <div className="flex items-center gap-3 mb-6 relative z-10">
                            <TrendingUp size={18} className="text-blue-500" />
                            <h3 className="text-[15px] font-bold text-slate-800">Distribución de Videos</h3>
                        </div>
                        <div className="relative z-10">
                            <DonutChart stats={stats} />
                        </div>
                    </div>

                    {/* Activity timeline */}
                    <div className="bg-white rounded-3xl border border-slate-200/60 shadow-sm p-6 overflow-hidden relative">
                        <div className="absolute top-0 right-0 w-32 h-32 rounded-full blur-2xl -mr-10 -mt-10 opacity-30 pointer-events-none bg-rose-50" />
                        <div className="flex items-center gap-3 mb-4 relative z-10">
                            <Eye size={18} className="text-rose-500" />
                            <h3 className="text-[15px] font-bold text-slate-800">Actividad Reciente</h3>
                        </div>
                        {videos.length === 0 ? (
                            <p className="text-[13px] font-medium text-slate-400 text-center py-6 relative z-10">
                                Sin actividad reciente
                            </p>
                        ) : (
                            <div className="space-y-4 relative z-10 mt-2">
                                {videos.slice(0, 5).map((video, i) => {
                                    const color = getVideoStatusColor(video);
                                    const colorMap: Record<string, string> = {
                                        emerald: 'bg-emerald-400',
                                        rose: 'bg-rose-400',
                                        amber: 'bg-amber-400',
                                        sky: 'bg-sky-400',
                                    };
                                    const badgeMap: Record<string, string> = {
                                        emerald: 'text-emerald-700 bg-emerald-50 border border-emerald-200/60',
                                        rose: 'text-rose-700 bg-rose-50 border border-rose-200/60',
                                        amber: 'text-amber-700 bg-amber-50 border border-amber-200/60',
                                        sky: 'text-sky-700 bg-sky-50 border border-sky-200/60',
                                    };
                                    const labelMap: Record<string, string> = {
                                        emerald: 'Aprobado',
                                        rose: 'Rechazado',
                                        amber: 'Analizando',
                                        sky: 'Subiendo',
                                    };
                                    return (
                                        <div
                                            key={video.id}
                                            className="flex items-start gap-4 cursor-pointer hover:bg-slate-50 -mx-3 px-3 py-2.5 rounded-2xl transition-all duration-200"
                                            onClick={() => handleVideoClick(video)}
                                        >
                                            <div className="relative mt-1.5 flex flex-col items-center">
                                                <div
                                                    className={`w-2.5 h-2.5 rounded-full ${colorMap[color]} shadow-sm`}
                                                />
                                                {i < Math.min(5, videos.length) - 1 && (
                                                    <div className="absolute top-4 w-[1px] h-8 bg-slate-100" />
                                                )}
                                            </div>
                                            <div className="min-w-0 flex-1">
                                                <p className="text-[13px] font-semibold text-slate-800 line-clamp-1 mb-1.5">
                                                    {getVideoTitle(video)}
                                                </p>
                                                <div className="flex items-center flex-wrap gap-2">
                                                    <span
                                                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${badgeMap[color]}`}
                                                    >
                                                        {labelMap[color]}
                                                    </span>
                                                    <span className="text-[11px] font-medium text-slate-400">
                                                        {getVideoDate(video.fecha_subida)}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <VideoDetailsModal
                videoId={selectedVideoId}
                open={isModalOpen}
                onOpenChange={setIsModalOpen}
            />
        </div>
    );
}
