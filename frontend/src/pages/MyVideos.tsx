import { useEffect, useMemo, useState } from 'react';
import { Button, buttonVariants } from '../components/ui/button';
import { cn } from '../lib/utils';
import {
    Video,
    Plus,
    Clock,
    HelpCircle,
    ChevronLeft,
    ChevronRight,
    Search,
    CheckCircle,
    XCircle,
    AlertTriangle,
} from 'lucide-react';
import { Link } from '@tanstack/react-router';
import { authService } from '../services/auth';
import { VideoDetailsModal } from '../components/VideoDetailsModal';
import { AnalysisExplanationModal } from '../components/AnalysisExplanationModal';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../lib/api';
import { VideoTableRow } from '../components/workspaces/VideoTableRow';
import { toast } from 'sonner';

export default function MyVideos() {
    const [filter, setFilter] = useState('Todos');
    const [searchInput, setSearchInput] = useState('');
    const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
    const [selectedVideoIds, setSelectedVideoIds] = useState<Set<string>>(new Set());
    const [selectedVideo, setSelectedVideo] = useState<any | null>(null);
    const [isDetailsOpen, setIsDetailsOpen] = useState(false);
    const [isExplanationOpen, setIsExplanationOpen] = useState(false);

    // Pagination state
    const [currentPage, setCurrentPage] = useState(1);
    const [rowsPerPage, setRowsPerPage] = useState<number | 'all'>(10);

    const user = authService.getUser();
    const queryClient = useQueryClient();

    useEffect(() => {
        const timer = window.setTimeout(() => {
            setDebouncedSearchQuery(searchInput.trim().toLowerCase());
            setCurrentPage(1);
        }, 300);

        return () => window.clearTimeout(timer);
    }, [searchInput]);

    const { data: videos = [], isLoading: loading } = useQuery({
        queryKey: ['my-videos'],
        queryFn: async () => {
            const response = await apiRequest<{ success: boolean; videos: any[] }>(
                '/socio/mis-videos',
            );
            return response?.success ? response.videos : [];
        },
        enabled: authService.isAuthenticated(),
    });

    useEffect(() => {
        const PROCESSING_STATES = [
            'pendiente', 'procesando', 'en_progreso', 'en_revision',
            'uploading', 'uploaded', 'analyzing', 'classifying',
            'deep_analyzing', 'generating_report', 'motion_detecting', 'motion_detected'
        ];
        
        const hasProcessing = videos.some((v: any) => {
            const status = (v?.estado || v?.resultado_ia || '').toString().toLowerCase();
            return PROCESSING_STATES.includes(status);
        });

        if (hasProcessing) {
            const interval = setInterval(() => {
                queryClient.invalidateQueries({ queryKey: ['my-videos'] });
            }, 5000);
            return () => clearInterval(interval);
        }
    }, [videos, queryClient]);

    const deleteVideoMutation = useMutation({
        mutationFn: async (videoId: string) => {
            return apiRequest(`/socio/videos/${videoId}`, { method: 'DELETE' });
        },
        onSuccess: (_, deletedVideoId) => {
            // Optimistic update or refetch
            queryClient.setQueryData(['my-videos'], (old: any[]) =>
                old ? old.filter((v) => v.id !== deletedVideoId) : [],
            );
        },
    });

    const handleDelete = async (videoId: string) => {
        if (!confirm('¿Estás seguro de eliminar este video?')) return;

        try {
            await deleteVideoMutation.mutateAsync(videoId);
            setSelectedVideoIds((prev) => {
                const next = new Set(prev);
                next.delete(videoId);
                return next;
            });
            toast.success('Video eliminado');
        } catch (error) {
            console.error('Error deleting video:', error);
            toast.error('No se pudo eliminar el video');
        }
    };

    const handleBatchDelete = async () => {
        if (selectedVideoIds.size === 0) return;
        if (!confirm(`¿Eliminar ${selectedVideoIds.size} video(s) seleccionados?`)) return;

        const ids = Array.from(selectedVideoIds);
        const results = await Promise.allSettled(ids.map((id) => deleteVideoMutation.mutateAsync(id)));
        const failed = results.filter((r) => r.status === 'rejected').length;
        const success = results.length - failed;

        if (success > 0) {
            toast.success(`${success} video(s) eliminado(s)`);
        }
        if (failed > 0) {
            toast.error(`${failed} video(s) no se pudieron eliminar`);
        }

        setSelectedVideoIds(new Set());
    };

    // Filter Logic
    const filteredVideos = useMemo(() => {
        const statusFiltered = videos.filter((v) => {
            const status = v.estado?.toUpperCase();
            if (filter === 'Todos') return true;
            if (filter === 'Pendientes')
                return (
                    status === 'PENDIENTE' || status === 'PROCESANDO' || status === 'EN_REVISION'
                );
            if (filter === 'Aprobados') return status === 'APROBADO' || status === 'COMPLETADO';
            if (filter === 'Rechazados') return status === 'RECHAZADO' || status === 'ERROR';
            return true;
        });

        if (!debouncedSearchQuery) return statusFiltered;

        return statusFiltered.filter((v) => {
            const title = (v.titulo || v.nombre_archivo || '').toLowerCase();
            const project = (v.workspace_nombre || '').toLowerCase();
            const status = (v.estado || '').toLowerCase();
            return (
                title.includes(debouncedSearchQuery) ||
                project.includes(debouncedSearchQuery) ||
                status.includes(debouncedSearchQuery)
            );
        });
    }, [videos, filter, debouncedSearchQuery]);

    useEffect(() => {
        setSelectedVideoIds((prev) => {
            const filteredIdSet = new Set(filteredVideos.map((video) => video.id));
            const next = new Set(Array.from(prev).filter((id) => filteredIdSet.has(id)));
            return next;
        });
    }, [filteredVideos]);

    // Pagination Logic
    const totalPages =
        rowsPerPage === 'all' ? 1 : Math.ceil(filteredVideos.length / (rowsPerPage as number));
    const paginatedVideos = useMemo(() => {
        if (rowsPerPage === 'all') return filteredVideos;
        const start = (currentPage - 1) * (rowsPerPage as number);
        return filteredVideos.slice(start, start + (rowsPerPage as number));
    }, [filteredVideos, currentPage, rowsPerPage]);

    const handleVideoClick = (video: any) => {
        const status = (video?.resultado_ia || video?.estado || '').toString().toUpperCase();
        if (['PENDIENTE', 'PROCESANDO', 'EN_PROGRESO', 'EN_REVISION'].includes(status)) {
            toast.info('El detalle estará disponible cuando finalice el análisis.');
            return;
        }

        setSelectedVideo(video);
        setIsDetailsOpen(true);
    };

    const allVisibleSelected =
        paginatedVideos.length > 0 && paginatedVideos.every((video) => selectedVideoIds.has(video.id));

    const toggleSelectAllVisible = (checked: boolean) => {
        setSelectedVideoIds((prev) => {
            const next = new Set(prev);
            paginatedVideos.forEach((video) => {
                if (checked) next.add(video.id);
                else next.delete(video.id);
            });
            return next;
        });
    };

    const handleToggleVideoSelect = (videoId: string, selected: boolean) => {
        setSelectedVideoIds((prev) => {
            const next = new Set(prev);
            if (selected) next.add(videoId);
            else next.delete(videoId);
            return next;
        });
    };

    const getStatusBadge = (statusValue: string) => {
        const status = statusValue?.toUpperCase();
        const base = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-bold tracking-wide uppercase shadow-sm border';

        switch (status) {
            case 'APROBADO':
            case 'COMPLETADO':
                return (
                    <span className={`${base} bg-emerald-50 text-emerald-700 border-emerald-200/60`}>
                        <CheckCircle size={14} className="text-emerald-500" />
                        Aprobado
                    </span>
                );
            case 'RECHAZADO':
            case 'ERROR':
                return (
                    <span className={`${base} bg-rose-50 text-rose-700 border-rose-200/60`}>
                        <XCircle size={14} className="text-rose-500" />
                        Rechazado
                    </span>
                );
            case 'EN_REVISION':
                return (
                    <span className={`${base} bg-amber-50 text-amber-700 border-amber-200/60`}>
                        <AlertTriangle size={14} className="text-amber-500" />
                        En Revisión
                    </span>
                );
            default: // PENDIENTE, PROCESANDO
                return (
                    <span className={`${base} bg-sky-50 text-sky-700 border-sky-200/60 animate-pulse`}>
                        <Clock size={14} className="text-sky-500" />
                        Analizando
                    </span>
                );
        }
    };

    const TabButton = ({ name, active }: { name: string; active: boolean }) => (
        <button
            onClick={() => {
                setFilter(name);
                setCurrentPage(1);
            }}
            className={`px-5 py-2 text-sm font-semibold rounded-full transition-all duration-300 flex items-center gap-2 ${active
                    ? 'bg-slate-800 text-white shadow-md'
                    : 'text-slate-500 hover:text-slate-800 hover:bg-slate-100'
                }`}
        >
            {name}
        </button>
    );

    return (
        <div className="space-y-6 max-w-[1400px] mx-auto pb-20 animate-in fade-in duration-500">
            {/* Header */}
            <div className="relative bg-white rounded-3xl border border-slate-100 shadow-sm p-8 overflow-hidden mb-8">
                {/* Soft Glow Background */}
                <div className="absolute top-0 right-0 w-80 h-80 rounded-full blur-3xl -mr-20 -mt-20 opacity-30 pointer-events-none bg-blue-50" />
                <div className="absolute bottom-0 left-0 w-64 h-64 rounded-full blur-3xl -ml-20 -mb-20 pointer-events-none bg-indigo-50" />

                <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
                    <div className="flex items-center gap-5">
                        <div className="w-16 h-16 rounded-[20px] bg-indigo-50 border border-indigo-100 flex items-center justify-center shadow-sm">
                            <Video size={32} className="text-indigo-600" strokeWidth={2} />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold text-slate-800 tracking-tight">Mis Videos</h1>
                            <p className="text-slate-500 mt-1 text-[15px]">Gestiona y administra todos tus videos procesados y en espera.</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <Button
                            onClick={() => setIsExplanationOpen(true)}
                            variant="ghost"
                            className="rounded-full font-medium text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
                        >
                            <HelpCircle size={18} className="mr-2" />
                            ¿Cómo funciona la IA?
                        </Button>
                        <Link
                            to="/upload"
                            className="group flex items-center gap-2.5 px-6 py-3 bg-slate-800 text-white text-[15px] font-semibold rounded-full shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all duration-300 ring-1 ring-slate-900/5 hover:bg-slate-700"
                        >
                            <Plus size={18} className="text-slate-200" />
                            Nuevo Video
                        </Link>
                    </div>
                </div>
            </div>

            {/* Filters Bar */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div className="bg-slate-100/60 p-1.5 rounded-full inline-flex gap-1 overflow-x-auto max-w-full border border-slate-200/60">
                    {['Todos', 'Pendientes', 'Aprobados', 'Rechazados'].map((tab) => (
                        <TabButton key={tab} name={tab} active={filter === tab} />
                    ))}
                </div>

                {/* Search */}
                <div className="relative group">
                    <Search
                        className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-500 transition-colors"
                        size={18}
                    />
                    <input
                        type="text"
                        placeholder="Buscar por título, proyecto..."
                        value={searchInput}
                        onChange={(e) => setSearchInput(e.target.value)}
                        className="pl-11 pr-5 py-3 rounded-full border border-slate-200 text-[15px] font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 w-full sm:w-72 shadow-sm transition-all"
                    />
                </div>
            </div>

            {selectedVideoIds.size > 0 && (
                <div className="bg-blue-50/80 border border-blue-200/60 rounded-2xl px-6 py-4 flex items-center justify-between gap-4 shadow-sm animate-in zoom-in-95 duration-200">
                    <p className="text-[15px] text-blue-800 font-bold flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                        {selectedVideoIds.size} video(s) seleccionado(s)
                    </p>
                    <div className="flex items-center gap-3">
                        <Button
                            variant="ghost"
                            className="text-blue-600 hover:text-blue-800 hover:bg-blue-100 rounded-full font-medium"
                            onClick={() => setSelectedVideoIds(new Set())}
                        >
                            Deseleccionar
                        </Button>
                        <Button
                            variant="danger"
                            className="rounded-full shadow-sm"
                            onClick={handleBatchDelete}
                            disabled={deleteVideoMutation.isPending}
                        >
                            Eliminar seleccionados
                        </Button>
                    </div>
                </div>
            )}

            {/* Video List / Table */}
            <div className="bg-white rounded-3xl shadow-sm border border-slate-200/60 overflow-hidden flex flex-col min-h-[400px]">
                {/* Table Header */}
                <div className="grid grid-cols-12 gap-4 border-b border-slate-100 bg-slate-50/50 px-8 py-4 text-xs font-bold text-slate-400 uppercase tracking-widest">
                    <div className="col-span-1">
                        <input
                            type="checkbox"
                            checked={allVisibleSelected}
                            onChange={(e) => toggleSelectAllVisible(e.target.checked)}
                            aria-label="Seleccionar todos los videos visibles"
                            className="h-4 w-4 rounded-md border-slate-300 text-blue-600 focus:ring-blue-600/30 cursor-pointer"
                        />
                    </div>
                    <div className="col-span-2">Preview</div>
                    <div className="col-span-9 sm:col-span-3">Título del Archivo</div>
                    <div className="hidden sm:block sm:col-span-2">Proyecto</div>
                    <div className="hidden sm:block sm:col-span-2">Fecha</div>
                    <div className="hidden sm:block sm:col-span-1">Estado de IA</div>
                    <div className="hidden sm:block sm:col-span-1 min-w-[3rem]"></div>
                </div>

                {/* Table Body */}
                <div className="divide-y divide-gray-100 flex-1">
                    {loading ? (
                        <div className="flex items-center justify-center h-64">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-tivit-red"></div>
                        </div>
                    ) : paginatedVideos.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-64 text-gray-400">
                            <Video size={48} className="mb-4 opacity-20" />
                            <p>No se encontraron videos</p>
                        </div>
                    ) : (
                        paginatedVideos.map((video) => (
                            <VideoTableRow
                                key={video.id}
                                video={video}
                                onClick={handleVideoClick}
                                onDelete={handleDelete}
                                isSelected={selectedVideoIds.has(video.id)}
                                onToggleSelect={handleToggleVideoSelect}
                                statusBadge={getStatusBadge(video.resultado_ia)}
                            />
                        ))
                    )}
                </div>

                {/* Footer / Pagination */}
                <div className="border-t border-slate-100 bg-slate-50/30 px-8 py-5 flex flex-col sm:flex-row items-center justify-between gap-4 text-[13px] font-medium text-slate-500">
                    <div className="flex items-center gap-4">
                        <span>
                            Mostrando <span className="text-slate-800 font-bold">{Math.min(paginatedVideos.length, rowsPerPage === 'all' ? filteredVideos.length : rowsPerPage)}</span>{' '}
                            de <span className="text-slate-800 font-bold">{filteredVideos.length}</span> resultados
                        </span>

                        <div className="flex items-center gap-3 border-l border-slate-200 pl-4">
                            <span>Filas por página:</span>
                            <select
                                value={rowsPerPage}
                                onChange={(e) => {
                                    const val = e.target.value;
                                    setRowsPerPage(val === 'all' ? 'all' : Number(val));
                                    setCurrentPage(1);
                                }}
                                className="bg-white border border-slate-200 rounded-lg px-2 py-1 font-bold text-slate-800 focus:outline-none focus:border-blue-500 shadow-sm cursor-pointer"
                            >
                                <option value={10}>10</option>
                                <option value={50}>50</option>
                                <option value="all">Todos</option>
                            </select>
                        </div>
                    </div>

                    {rowsPerPage !== 'all' && (
                        <div className="flex items-center gap-3">
                            <button
                                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                                disabled={currentPage === 1}
                                className="p-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 hover:text-slate-900 hover:bg-slate-50 disabled:opacity-30 disabled:hover:bg-white shadow-sm transition-all"
                            >
                                <ChevronLeft size={16} strokeWidth={3} />
                            </button>
                            <span className="font-bold text-slate-800 px-2">
                                Página {currentPage} de {totalPages || 1}
                            </span>
                            <button
                                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                                disabled={currentPage === totalPages}
                                className="p-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 hover:text-slate-900 hover:bg-slate-50 disabled:opacity-30 disabled:hover:bg-white shadow-sm transition-all"
                            >
                                <ChevronRight size={16} strokeWidth={3} />
                            </button>
                        </div>
                    )}
                </div>
            </div>

            <VideoDetailsModal
                videoId={selectedVideo?.id || null}
                open={isDetailsOpen}
                onOpenChange={setIsDetailsOpen}
            />

            <AnalysisExplanationModal
                isOpen={isExplanationOpen}
                onClose={() => setIsExplanationOpen(false)}
            />
        </div>
    );
}
