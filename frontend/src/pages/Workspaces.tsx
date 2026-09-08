import { useState, useEffect, useRef } from 'react';
import { FolderOpen, Plus, Trash2, Copy, Video, Search, SortAsc, MoreVertical, Layers, ArrowRight } from 'lucide-react';
import { useNavigate } from '@tanstack/react-router';
import { workspaceService, type Workspace } from '../services/workspace';
import { Button } from '../components/ui/button';
import { CreateWorkspaceModal } from '../components/CreateWorkspaceModal';
import { WorkspaceChatButton } from '../components/WorkspaceChatButton';

export default function WorkspacesPage() {
    const navigate = useNavigate();
    const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
    const [filteredWorkspaces, setFilteredWorkspaces] = useState<Workspace[]>([]);
    const [loading, setLoading] = useState(true);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [sortBy, setSortBy] = useState<'alfabetico' | 'fecha_creacion' | 'actividad' | 'num_videos'>('alfabetico');
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);
    const menuRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        loadWorkspaces();
    }, [sortBy]);

    // Close kebab menu on outside click
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setOpenMenuId(null);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    useEffect(() => {
        // Filter workspaces based on search query
        if (searchQuery.trim() === '') {
            setFilteredWorkspaces(workspaces);
        } else {
            const query = searchQuery.toLowerCase();
            const filtered = workspaces.filter(
                (ws) =>
                    ws.nombre.toLowerCase().includes(query) ||
                    ws.descripcion.toLowerCase().includes(query) ||
                    ws.contexto.toLowerCase().includes(query)
            );
            setFilteredWorkspaces(filtered);
        }
    }, [searchQuery, workspaces]);

    const loadWorkspaces = async () => {
        try {
            setLoading(true);
            const ws = await workspaceService.listWorkspaces(sortBy);
            setWorkspaces(ws);
            setFilteredWorkspaces(ws);
        } catch (error) {
            console.error('Error loading workspaces:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (id: string, nombre: string) => {
        if (!confirm(`¿Eliminar proyecto "${nombre}"? Los videos se moverán a General.`)) {
            return;
        }
        try {
            await workspaceService.deleteWorkspace(id, 'mover_general');
            loadWorkspaces();
        } catch (error) {
            console.error('Error deleting workspace:', error);
            alert('Error al eliminar proyecto');
        }
    };

    const handleDuplicate = async (id: string, nombre: string) => {
        const nuevoNombre = prompt(`Nombre para la copia de "${nombre}":`, `${nombre} (Copia)`);
        if (!nuevoNombre) return;

        try {
            await workspaceService.duplicateWorkspace(id, nuevoNombre);
            loadWorkspaces();
        } catch (error: any) {
            console.error('Error duplicating workspace:', error);
            alert(error.message || 'Error al duplicar proyecto');
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="text-center">
                    <span className="loader"></span>
                    <p className="mt-4 text-gray-600">Cargando proyectos...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-[1400px] mx-auto space-y-8 animate-in fade-in duration-500">
            {/* ── Hero Banner ── */}
            <div className="relative rounded-3xl overflow-hidden bg-white border border-slate-100 shadow-sm p-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
                {/* Decorative background element */}
                <div className="absolute top-0 right-0 w-64 h-64 bg-slate-50 rounded-full blur-3xl -mr-20 -mt-20 opacity-60 pointer-events-none" />
                <div className="absolute bottom-0 left-0 w-40 h-40 bg-blue-50/50 rounded-full blur-2xl -ml-10 -mb-10 pointer-events-none" />

                <div className="relative">
                    <div className="flex items-center gap-3 mb-2">
                        <div className="p-2.5 bg-slate-800 rounded-xl shadow-sm">
                            <Layers size={22} className="text-white" />
                        </div>
                        <h1 className="text-3xl font-bold text-slate-800 tracking-tight">Mis Proyectos</h1>
                    </div>
                    <p className="text-slate-500 text-sm ml-[54px]">
                        Organiza tus videos en proyectos con contexto compartido
                    </p>
                </div>
                <Button
                    onClick={() => setShowCreateModal(true)}
                    className="relative bg-slate-800 text-white hover:bg-slate-700 px-6 py-2.5 rounded-full font-medium flex items-center gap-2 shadow-sm transition-all hover:shadow-md hover:-translate-y-0.5 whitespace-nowrap"
                >
                    <Plus size={18} />
                    Nuevo Proyecto
                </Button>
            </div>

            {/* ── Filter Bar & Stats ── */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div className="flex flex-wrap items-center gap-3">
                    {/* Compact Search */}
                    <div className="relative group">
                        <Search className="absolute left-3.5 top-1/2 transform -translate-y-1/2 text-slate-400 group-within:text-slate-600 transition-colors" size={16} />
                        <input
                            type="text"
                            placeholder="Buscar proyectos..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full md:w-64 pl-10 pr-4 py-2.5 bg-white border border-slate-200 rounded-full text-sm focus:ring-2 focus:ring-slate-100 focus:border-slate-300 shadow-sm transition-all focus:md:w-72"
                        />
                    </div>
                    
                    {/* Compact Sort */}
                    <div className="relative">
                        <SortAsc className="absolute left-3.5 top-1/2 transform -translate-y-1/2 text-slate-400" size={16} />
                        <select
                            value={sortBy}
                            onChange={(e) => setSortBy(e.target.value as any)}
                            className="pl-10 pr-9 py-2.5 border border-slate-200 rounded-full bg-white text-sm focus:ring-2 focus:ring-slate-100 focus:border-slate-300 appearance-none cursor-pointer shadow-sm text-slate-600 font-medium"
                        >
                            <option value="alfabetico">Alfabético</option>
                            <option value="fecha_creacion">Más recientes</option>
                            <option value="actividad">Última actividad</option>
                            <option value="num_videos">Más videos</option>
                        </select>
                    </div>
                </div>

                {/* Compact Stats */}
                {filteredWorkspaces.length > 0 && (
                    <div className="flex items-center gap-4 px-5 py-2.5 bg-white rounded-full text-xs font-semibold text-slate-500 border border-slate-200 shadow-sm">
                        <span className="flex items-center gap-1.5" title="Proyectos Totales">
                            <FolderOpen size={14} className="text-slate-400"/> {filteredWorkspaces.length}
                        </span>
                        <div className="w-1 h-1 rounded-full bg-slate-300" />
                        <span className="flex items-center gap-1.5" title="Videos Totales">
                            <Video size={14} className="text-slate-400"/> {filteredWorkspaces.reduce((sum, ws) => sum + (ws.estadisticas?.total_videos || 0), 0)}
                        </span>
                        {(filteredWorkspaces.reduce((sum, ws) => sum + (ws.estadisticas?.aprobados || 0), 0) > 0 || filteredWorkspaces.reduce((sum, ws) => sum + (ws.estadisticas?.rechazados || 0), 0) > 0) && (
                            <>
                                <div className="w-1 h-1 rounded-full bg-slate-300" />
                                <div className="flex items-center gap-3">
                                     <span className="text-emerald-600 flex items-center gap-1" title="Videos Aprobados">
                                        ✓ {filteredWorkspaces.reduce((sum, ws) => sum + (ws.estadisticas?.aprobados || 0), 0)}
                                    </span>
                                    {filteredWorkspaces.reduce((sum, ws) => sum + (ws.estadisticas?.rechazados || 0), 0) > 0 && (
                                        <span className="text-rose-500 flex items-center gap-1" title="Videos Rechazados">
                                            ✗ {filteredWorkspaces.reduce((sum, ws) => sum + (ws.estadisticas?.rechazados || 0), 0)}
                                        </span>
                                    )}
                                </div>
                            </>
                        )}
                    </div>
                )}
            </div>

            {/* ── Workspaces Grid ── */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {filteredWorkspaces.map((workspace) => (
                    <div
                        key={workspace.id}
                        className="group relative bg-white rounded-[24px] border border-slate-200/60 shadow-sm hover:shadow-xl hover:shadow-slate-200/50 hover:-translate-y-1 transition-all duration-300 cursor-pointer overflow-hidden flex flex-col"
                        onClick={() => navigate({ to: `/proyecto/${workspace.id}` })}
                    >
                        {/* Soft Glow Background Top */}
                        <div className="absolute top-0 left-0 w-full h-32 opacity-[0.03] transition-opacity duration-500 group-hover:opacity-[0.08]" 
                             style={{ background: `linear-gradient(to bottom, ${workspace.color}, transparent)` }} />

                        <div className="p-6 flex-1 flex flex-col relative z-10">
                            {/* Header */}
                            <div className="flex items-start justify-between mb-4">
                                <div className="flex items-center gap-4">
                                    <div
                                        className="w-12 h-12 rounded-2xl flex items-center justify-center overflow-hidden shrink-0 shadow-sm transition-transform duration-300 group-hover:scale-105 group-hover:rotate-1"
                                        style={{ backgroundColor: `${workspace.color}15`, border: `1px solid ${workspace.color}30` }}
                                    >
                                        {workspace.icono_url ? (
                                            <img src={workspace.icono_url} alt={workspace.nombre} className="w-full h-full object-cover" />
                                        ) : (
                                            <FolderOpen size={24} style={{ color: workspace.color }} />
                                        )}
                                    </div>
                                    <div className="min-w-0 pr-2">
                                        <h3 className="font-semibold text-[17px] leading-tight text-slate-800 group-hover:text-slate-900 transition-colors truncate">
                                            {workspace.nombre}
                                        </h3>
                                        {workspace.es_general && (
                                            <span className="inline-block mt-1 text-[10px] uppercase tracking-wider font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
                                                Defecto
                                            </span>
                                        )}
                                    </div>
                                </div>

                                {/* Kebab menu */}
                                {!workspace.es_general && (
                                    <div className="relative" ref={openMenuId === workspace.id ? menuRef : null}>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                setOpenMenuId(openMenuId === workspace.id ? null : workspace.id);
                                            }}
                                            className="p-2 -mr-2 rounded-full text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                                            title="Más opciones"
                                        >
                                            <MoreVertical size={18} />
                                        </button>

                                        {openMenuId === workspace.id && (
                                            <div className="absolute right-0 top-10 z-20 w-48 bg-white border border-slate-100 rounded-2xl shadow-xl py-2 animate-in fade-in zoom-in-95 origin-top-right">
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); setOpenMenuId(null); handleDuplicate(workspace.id, workspace.nombre); }}
                                                    className="w-full flex items-center gap-2.5 px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-colors"
                                                >
                                                    <Copy size={16} /> Duplicar
                                                </button>
                                                <div className="border-t border-slate-50 my-1.5" />
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); setOpenMenuId(null); handleDelete(workspace.id, workspace.nombre); }}
                                                    className="w-full flex items-center gap-2.5 px-4 py-2 text-sm font-medium text-rose-600 hover:bg-rose-50 transition-colors"
                                                >
                                                    <Trash2 size={16} /> Eliminar
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>

                            {/* Description */}
                            {workspace.descripcion ? (
                                <p className="text-[13px] text-slate-500 mb-6 line-clamp-2 leading-relaxed flex-1">
                                    {workspace.descripcion}
                                </p>
                            ) : (
                                <div className="flex-1 min-h-[40px] mb-2" />
                            )}

                            {/* Visual Stats Pills */}
                            <div className="flex flex-wrap items-center gap-2 mt-auto mb-5">
                                <span className="inline-flex items-center gap-1.5 text-[11px] font-bold tracking-wide px-2.5 py-1 rounded-full bg-slate-50 text-slate-600 border border-slate-200/60" title={`${workspace.estadisticas?.total_videos || 0} videos en este proyecto`}>
                                    <Video size={12} className="text-slate-400" /> {workspace.estadisticas?.total_videos || 0}
                                </span>
                                {workspace.estadisticas?.total_videos > 0 && (
                                    <>
                                        {workspace.estadisticas.aprobados > 0 && (
                                            <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/60">
                                                ✓ {workspace.estadisticas.aprobados}
                                            </span>
                                        )}
                                        {workspace.estadisticas.rechazados > 0 && (
                                            <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full bg-rose-50 text-rose-700 border border-rose-200/60">
                                                ✗ {workspace.estadisticas.rechazados}
                                            </span>
                                        )}
                                    </>
                                )}
                            </div>

                            {/* Primary action */}
                            {!workspace.es_general ? (
                                <div className="pt-4 border-t border-slate-100 mt-auto">
                                    <WorkspaceChatButton
                                        workspaceId={workspace.id}
                                        variant="secondary"
                                        className="w-full text-sm font-semibold rounded-xl bg-slate-50/80 hover:bg-slate-100 text-slate-700 border border-transparent hover:border-slate-200 transition-all shadow-sm"
                                        onContextImproved={() => loadWorkspaces()}
                                        isContextualized={workspace.metadatos?.ia_contextualizada}
                                    />
                                </div>
                            ) : (
                                <div className="pt-4 border-t border-slate-100 mt-auto flex items-center justify-center">
                                    <div className="flex items-center justify-center gap-2 text-sm text-slate-400 font-semibold py-1.5 group-hover:text-blue-600 transition-colors">
                                        Explorar Proyecto <ArrowRight size={16} className="transition-transform duration-300 group-hover:translate-x-1.5" />
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                ))}

            </div>

            {/* ── Empty State ── */}
            {filteredWorkspaces.length === 0 && !loading && (
                <div className="text-center py-24 bg-white rounded-3xl border border-slate-200/60 shadow-sm flex flex-col items-center justify-center animate-in zoom-in-95 duration-500">
                    <div className="p-5 rounded-full bg-slate-50 mb-6 relative group cursor-pointer transition-transform hover:scale-105 duration-300">
                        <div className="absolute inset-0 bg-blue-50/50 rounded-full scale-0 group-hover:scale-100 transition-transform duration-500 ease-out" />
                        <FolderOpen size={48} className="text-slate-300 relative z-10 group-hover:text-blue-500 transition-colors duration-300" />
                    </div>
                    <h3 className="text-xl font-bold text-slate-800 mb-2">
                        {searchQuery ? 'Sin resultados' : 'Aún no hay proyectos'}
                    </h3>
                    <p className="text-slate-500 text-[15px] mb-8 max-w-sm mx-auto leading-relaxed">
                        {searchQuery
                            ? `No encontramos proyectos con el término "${searchQuery}". Intenta con otra palabra.`
                            : 'Crea tu primer proyecto para agrupar videos y dotarlos de contexto con IA.'}
                    </p>
                    {!searchQuery && (
                        <Button
                            onClick={() => setShowCreateModal(true)}
                            className="bg-slate-800 hover:bg-slate-700 text-white px-8 py-3 rounded-full font-semibold shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all text-[15px]"
                        >
                            <Plus size={18} className="mr-2" /> Empezar un Proyecto
                        </Button>
                    )}
                </div>
            )}
            
            {/* Create Modal */}
            <CreateWorkspaceModal
                open={showCreateModal}
                onClose={() => setShowCreateModal(false)}
                onCreated={() => {
                    loadWorkspaces();
                }}
            />
        </div>
    );
}
