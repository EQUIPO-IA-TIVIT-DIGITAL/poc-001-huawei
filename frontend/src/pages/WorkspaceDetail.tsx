import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { FolderOpen, ArrowLeft, Upload, Settings, Video, Clock, Play, CheckCircle, XCircle, AlertTriangle, Trash2 } from 'lucide-react';
import { workspaceService, type Workspace } from '../services/workspace';
import { videoService } from '../services/video';
import { toast } from 'sonner';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Breadcrumbs } from '../components/Breadcrumbs';
import { WorkspaceUploadModal } from '../components/WorkspaceUploadModal';
import { BatchNotification } from '../components/BatchNotification';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { VideoDetailsModal } from '../components/VideoDetailsModal';

export default function WorkspaceDetailPage() {
    const { id } = useParams({ strict: false }) as { id: string };
    const navigate = useNavigate();
    const [workspace, setWorkspace] = useState<Workspace | null>(null);
    const [videos, setVideos] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [showUploadModal, setShowUploadModal] = useState(false);

    // Estado para confirmación de eliminación de video
    const [videoToDelete, setVideoToDelete] = useState<{ id: string, nombre: string } | null>(null);
    const [deleting, setDeleting] = useState(false);

    // Estado para confirmación de eliminación del proyecto
    const [showDeleteProject, setShowDeleteProject] = useState(false);
    const [deletingProject, setDeletingProject] = useState(false);

    // Estado para batch upload
    const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
    const [showBatchNotification, setShowBatchNotification] = useState(false);
    const [isTabVisible, setIsTabVisible] = useState(() => !document.hidden);

    // Estado para detalles del video
    const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null);
    const [isDetailsOpen, setIsDetailsOpen] = useState(false);

    // Polling para auto-refresh cuando hay videos procesando
    const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const PROCESSING_STATES = [
        'pendiente', 'procesando', 'en_progreso', 'en_revision',
        'uploading', 'uploaded', 'analyzing', 'classifying',
        'deep_analyzing', 'generating_report', 'motion_detecting', 'motion_detected'
    ];

    const isVideoFinalized = (video: any) => {
        const status = (video?.resultado_ia || video?.estado || '').toString().toLowerCase();
        return !PROCESSING_STATES.includes(status);
    };

    const hasProcessingVideos = useCallback(
        (vids: any[]) => vids.some(v => PROCESSING_STATES.includes(v.estado?.toLowerCase())),
        []
    );

    useEffect(() => {
        const onVisibilityChange = () => setIsTabVisible(!document.hidden);
        document.addEventListener('visibilitychange', onVisibilityChange);
        return () => document.removeEventListener('visibilitychange', onVisibilityChange);
    }, []);

    useEffect(() => {
        if (id) {
            loadWorkspace();
        }
        return () => {
            if (pollingRef.current) clearInterval(pollingRef.current);
        };
    }, [id]);

    // Auto-polling: cuando hay videos procesando, refrescar cada 5s
    useEffect(() => {
        if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
        }

        if (isTabVisible && hasProcessingVideos(videos)) {
            pollingRef.current = setInterval(async () => {
                try {
                    const vids = await workspaceService.getWorkspaceVideos(id);
                    setVideos(vids);
                    // Si ya no hay videos procesando, parar el polling
                    if (!hasProcessingVideos(vids) && pollingRef.current) {
                        clearInterval(pollingRef.current);
                        pollingRef.current = null;
                    }
                } catch (e) {
                    console.error('Error polling videos:', e);
                }
            }, 5000);
        }

        return () => {
            if (pollingRef.current) clearInterval(pollingRef.current);
        };
    }, [videos, hasProcessingVideos, id, isTabVisible]);

    const loadWorkspace = async () => {
        try {
            setLoading(true);
            const [ws, vids] = await Promise.all([
                workspaceService.getWorkspace(id),
                workspaceService.getWorkspaceVideos(id),
            ]);
            setWorkspace(ws);
            setVideos(vids);
        } catch (error) {
            console.error('Error loading workspace:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleUploadClick = () => {
        setShowUploadModal(true);
    };

    const handleBatchUploadSuccess = (batchId: string, _videoIds: string[]) => {
        setShowUploadModal(false);
        setActiveBatchId(batchId);
        setShowBatchNotification(true);
        toast.info('Videos cargados. El análisis continúa en segundo plano.');
        loadWorkspace();
    };

    const handleBatchComplete = () => {
        setShowBatchNotification(false);
        setActiveBatchId(null);
        loadWorkspace();
    };

    const handleDeleteVideo = async () => {
        if (!videoToDelete) return;

        setDeleting(true);
        try {
            const result = await videoService.deleteVideo(videoToDelete.id);
            if (result?.success) {
                loadWorkspace();
            } else {
                console.error('Error eliminando video');
            }
        } catch (error) {
            console.error('Error eliminando video:', error);
        } finally {
            setDeleting(false);
            setVideoToDelete(null);
        }
    };

    const handleDeleteProject = async () => {
        if (!workspace) return;
        setDeletingProject(true);
        try {
            await workspaceService.deleteWorkspace(workspace.id, 'mover_general');
            navigate({ to: '/proyectos' });
        } catch (error) {
            console.error('Error eliminando proyecto:', error);
            toast.error('Error al eliminar el proyecto');
        } finally {
            setDeletingProject(false);
            setShowDeleteProject(false);
        }
    };

    const handleVideoClick = (video: any) => {
        if (!isVideoFinalized(video)) {
            toast.info('El detalle estará disponible cuando finalice el análisis.');
            return;
        }

        setSelectedVideoId(video.id);
        setIsDetailsOpen(true);
    };

    const getStatusBadge = (status: string) => {
        const statusUpper = status?.toUpperCase();
        switch (statusUpper) {
            case 'APROBADO':
            case 'COMPLETADO':
                return (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold tracking-wide bg-emerald-50 text-emerald-700 border border-emerald-200/60 shadow-sm">
                        <CheckCircle size={14} /> Aprobado
                    </span>
                );
            case 'RECHAZADO':
            case 'ERROR':
                return (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold tracking-wide bg-rose-50 text-rose-700 border border-rose-200/60 shadow-sm">
                        <XCircle size={14} /> Rechazado
                    </span>
                );
            case 'PROCESANDO':
            case 'PENDIENTE':
            case 'EN_PROGRESO':
                return (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold tracking-wide bg-amber-50 text-amber-700 border border-amber-200/60 shadow-sm animate-pulse">
                        <AlertTriangle size={14} /> Procesando
                    </span>
                );
            default:
                return (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold tracking-wide bg-slate-50 text-slate-600 border border-slate-200/60 shadow-sm">
                        {status || 'Desconocido'}
                    </span>
                );
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen  flex items-center justify-center">
                <div className="text-center">
                    <span className="loader"></span>
                    <p className="mt-4 text-gray-600">Cargando proyecto...</p>
                </div>
            </div>
        );
    }

    if (!workspace) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="text-center">
                    <h2 className="text-2xl font-bold text-gray-800 mb-4">Proyecto no encontrado</h2>
                    <Button onClick={() => navigate({ to: '/proyectos' })} className="bg-blue-600 text-white">
                        Volver a Proyectos
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen p-8 animate-in fade-in duration-500">
            <div className="max-w-[1400px] mx-auto">
                {/* Breadcrumbs */}
                <div className="mb-6">
                    <Breadcrumbs
                        items={[
                            { label: 'Proyectos', to: '/proyectos' },
                            { label: workspace.nombre }
                        ]}
                    />
                </div>

                {/* Header Container */}
                <div className="relative bg-white rounded-3xl border border-slate-100 shadow-sm p-8 mb-10 overflow-hidden">
                    {/* Soft Glow Background */}
                    <div className="absolute top-0 right-0 w-64 h-64 rounded-full blur-3xl -mr-20 -mt-20 opacity-[0.04] pointer-events-none" 
                         style={{ backgroundColor: workspace.color }} />
                    <div className="absolute bottom-0 left-0 w-40 h-40 bg-slate-50 rounded-full blur-2xl -ml-10 -mb-10 pointer-events-none" />

                    <div className="relative z-10 flex flex-col gap-6">
                        {/* Title block */}
                        <div className="flex items-start justify-between">
                            <div className="flex items-center gap-5">
                                <div
                                    className="w-16 h-16 rounded-[20px] flex items-center justify-center overflow-hidden shadow-sm"
                                    style={{ backgroundColor: workspace.color + '15', border: `1px solid ${workspace.color}30` }}
                                >
                                    {workspace.icono_url ? (
                                        <img 
                                            src={workspace.icono_url} 
                                            alt={workspace.nombre}
                                            className="w-full h-full object-cover"
                                        />
                                    ) : (
                                        <FolderOpen size={32} style={{ color: workspace.color }} />
                                    )}
                                </div>
                                <div>
                                    <h1 className="text-3xl font-bold text-slate-800 tracking-tight">{workspace.nombre}</h1>
                                    {workspace.descripcion && (
                                        <p className="text-slate-500 mt-1 text-[15px] max-w-2xl">{workspace.descripcion}</p>
                                    )}
                                </div>
                            </div>
                            {!workspace.es_general && (
                                <button
                                    onClick={() => setShowDeleteProject(true)}
                                    className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-rose-600 border border-rose-200 hover:bg-rose-50 hover:border-rose-300 rounded-full transition-all shadow-sm"
                                    title="Eliminar proyecto"
                                >
                                    <Trash2 size={15} />
                                    Eliminar proyecto
                                </button>
                            )}
                        </div>

                        {/* Context Block */}
                        {workspace.contexto && (
                            <div className="bg-slate-50/50 rounded-2xl p-5 border border-slate-200/60 max-w-4xl shadow-sm">
                                <h3 className="flex items-center gap-2 font-semibold text-slate-700 mb-2">
                                    <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                                    Contexto del Proyecto
                                </h3>
                                <p className="text-slate-600 text-sm leading-relaxed">{workspace.contexto}</p>
                            </div>
                        )}

                        {/* Stats Strip */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
                            <div className="bg-white border border-slate-200/60 shadow-sm rounded-2xl p-5 flex items-center gap-4 transition-all hover:shadow-md hover:-translate-y-0.5">
                                <div className="p-3 bg-slate-50 text-slate-600 rounded-xl">
                                    <Video size={20} />
                                </div>
                                <div>
                                    <div className="text-2xl font-bold text-slate-800 leading-none mb-1">
                                        {videos.length}
                                    </div>
                                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-widest">Total Videos</div>
                                </div>
                            </div>

                            <div className="bg-white border border-slate-200/60 shadow-sm rounded-2xl p-5 flex items-center gap-4 transition-all hover:shadow-md hover:-translate-y-0.5">
                                <div className="p-3 bg-emerald-50 text-emerald-600 rounded-xl">
                                    <CheckCircle size={20} />
                                </div>
                                <div>
                                    <div className="text-2xl font-bold text-slate-800 leading-none mb-1">
                                        {videos.filter(v => ['aprobado', 'completado'].includes(v.estado?.toLowerCase())).length}
                                    </div>
                                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-widest">Aprobados</div>
                                </div>
                            </div>

                            <div className="bg-white border border-slate-200/60 shadow-sm rounded-2xl p-5 flex items-center gap-4 transition-all hover:shadow-md hover:-translate-y-0.5">
                                <div className="p-3 bg-rose-50 text-rose-600 rounded-xl">
                                    <XCircle size={20} />
                                </div>
                                <div>
                                    <div className="text-2xl font-bold text-slate-800 leading-none mb-1">
                                        {videos.filter(v => ['rechazado', 'error'].includes(v.estado?.toLowerCase())).length}
                                    </div>
                                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-widest">Rechazados</div>
                                </div>
                            </div>

                            <div className="bg-white border border-slate-200/60 shadow-sm rounded-2xl p-5 flex items-center gap-4 transition-all hover:shadow-md hover:-translate-y-0.5">
                                <div className="p-3 bg-amber-50 text-amber-600 rounded-xl">
                                    <Clock size={20} />
                                </div>
                                <div>
                                    <div className="text-2xl font-bold text-slate-800 leading-none mb-1">
                                        {videos.filter(v => ['en_revision', 'procesando', 'pendiente', 'en_progreso'].includes(v.estado?.toLowerCase())).length}
                                    </div>
                                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-widest">En Revisión</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Videos Section */}
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-2xl font-bold text-slate-800">Videos del Proyecto</h2>
                    <Button
                        onClick={handleUploadClick}
                        className="bg-slate-800 hover:bg-slate-700 text-white px-5 py-2.5 rounded-full font-medium flex items-center gap-2 shadow-sm transition-all hover:shadow-md hover:-translate-y-0.5 text-sm"
                    >
                        <Upload size={16} />
                        Subir Video
                    </Button>
                </div>

                {hasProcessingVideos(videos) && (
                    <div className="mb-6 bg-blue-50/80 border border-blue-200/60 rounded-2xl px-5 py-4 flex items-center gap-3 shadow-sm animate-in fade-in slide-in-from-top-2">
                        <span className="loader scale-75"></span>
                        <p className="text-sm text-blue-800 font-semibold animate-pulse">
                            Analizando videos con IA en segundo plano...
                        </p>
                    </div>
                )}

                {videos.length === 0 ? (
                    <div className="bg-white rounded-3xl border border-slate-200/60 shadow-sm p-24 text-center animate-in zoom-in-95 duration-500">
                        <div className="p-5 rounded-full bg-slate-50 inline-block mb-6 relative group cursor-pointer transition-transform hover:scale-105 duration-300">
                            <Video size={48} className="text-slate-300 relative z-10 group-hover:text-blue-500 transition-colors duration-300" />
                        </div>
                        <h3 className="text-xl font-bold text-slate-800 mb-2">
                            Aún no hay videos en este proyecto
                        </h3>
                        <p className="text-slate-500 text-[15px] mb-8 max-w-sm mx-auto leading-relaxed">Sube tu primer video para que la Inteligencia Artificial analice su contenido basándose en el contexto del proyecto.</p>
                        <Button
                            onClick={handleUploadClick}
                            className="bg-slate-800 hover:bg-slate-700 text-white px-8 py-3 rounded-full font-semibold shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all text-[15px]"
                        >
                            <Upload size={18} className="mr-2" /> Comenzar a Subir
                        </Button>
                    </div>
                ) : (
                    <div className="bg-white rounded-3xl border border-slate-200/60 shadow-sm overflow-hidden mb-8">
                        {/* Header de la tabla */}
                        <div className="grid grid-cols-12 gap-4 items-center px-8 py-4 bg-slate-50/50 border-b border-slate-200/60 text-xs font-bold text-slate-500 uppercase tracking-wider">
                            <div className="col-span-2">Preview</div>
                            <div className="col-span-6">Título del Archivo</div>
                            <div className="col-span-3">Estado de IA</div>
                            <div className="col-span-1 text-center">Acciones</div>
                        </div>

                        {/* Lista de videos */}
                        <div className="divide-y divide-slate-100">
                            {videos.map((video) => (
                                <div
                                    key={video.id}
                                    onClick={() => handleVideoClick(video)}
                                    className="grid grid-cols-12 gap-4 items-center px-8 py-5 bg-white transition-all cursor-pointer group hover:bg-slate-50/80"
                                >
                                    {/* Preview con thumbnail */}
                                    <div className="col-span-2">
                                        <div className="h-16 w-28 bg-slate-100 rounded-xl flex items-center justify-center overflow-hidden relative shadow-sm border border-slate-200/60 transition-transform duration-300 group-hover:scale-105 group-hover:shadow-md">
                                            {/* Placeholder/Fallback always rendered behind */}
                                            <Video className="text-slate-300 absolute" size={24} />

                                            {/* Image overlay */}
                                            <img
                                                crossOrigin="use-credentials"
                                                src={`${(import.meta as any).env.VITE_API_BASE_URL || 'http://localhost:5001'}/socio/thumbnail/${video.id}`}
                                                alt={video.nombre_archivo}
                                                className="absolute inset-0 w-full h-full object-cover bg-slate-100 transition-transform duration-500 group-hover:scale-110"
                                                onError={(e) => {
                                                    // Si falla la carga, ocultamos la imagen para mostrar el icono de fondo
                                                    (e.target as HTMLImageElement).style.opacity = '0';
                                                }}
                                            />

                                            <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/10 transition-colors z-10" />
                                        </div>
                                    </div>

                                    {/* Título */}
                                    <div className="col-span-6 pr-6">
                                        <span className="font-semibold text-[15px] text-slate-800 block truncate group-hover:text-slate-900 transition-colors">
                                            {video.nombre_archivo}
                                        </span>
                                    </div>

                                    {/* Estado */}
                                    <div className="col-span-3">
                                        {getStatusBadge(video.estado)}
                                    </div>

                                    {/* Acciones */}
                                    <div className="col-span-1 flex justify-center">
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                setVideoToDelete({ id: video.id, nombre: video.nombre_archivo });
                                            }}
                                            className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-all opacity-0 group-hover:opacity-100 focus:opacity-100"
                                            title="Eliminar video"
                                        >
                                            <Trash2 size={18} />
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* Modal de upload */}
            {workspace && (
                <WorkspaceUploadModal
                    open={showUploadModal}
                    onOpenChange={setShowUploadModal}
                    workspaceId={workspace.id}
                    workspaceName={workspace.nombre}
                    onBatchUploadSuccess={handleBatchUploadSuccess}
                />
            )}

            {/* Modal de detalles del video */}
            <VideoDetailsModal
                videoId={selectedVideoId}
                open={isDetailsOpen}
                onOpenChange={setIsDetailsOpen}
            />

            {/* Notificación de batch */}
            {activeBatchId && showBatchNotification && (
                <BatchNotification
                    batchId={activeBatchId}
                    onClose={() => setShowBatchNotification(false)}
                    onComplete={handleBatchComplete}
                />
            )}

            {/* Diálogo de confirmación para eliminar video */}
            <ConfirmDialog
                open={!!videoToDelete}
                onOpenChange={(open) => !open && setVideoToDelete(null)}
                title="Eliminar Video"
                description={`¿Estás seguro de que deseas eliminar "${videoToDelete?.nombre}"? Esta acción no se puede deshacer.`}
                confirmText={deleting ? "Eliminando..." : "Eliminar"}
                cancelText="Cancelar"
                onConfirm={handleDeleteVideo}
                variant="danger"
                loading={deleting}
            />

            {/* Diálogo de confirmación para eliminar proyecto */}
            <ConfirmDialog
                open={showDeleteProject}
                onOpenChange={(open) => !open && setShowDeleteProject(false)}
                title="Eliminar Proyecto"
                description={`¿Estás seguro de que deseas eliminar el proyecto "${workspace?.nombre}"? Los videos se moverán al proyecto General.`}
                confirmText={deletingProject ? "Eliminando..." : "Eliminar proyecto"}
                cancelText="Cancelar"
                onConfirm={handleDeleteProject}
                variant="danger"
                loading={deletingProject}
            />
        </div>
    );
}
