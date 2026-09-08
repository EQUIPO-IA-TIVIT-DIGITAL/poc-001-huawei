import { Clock, MoreHorizontal, Play, Trash2, Video } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Button } from '../ui/button';

interface VideoTableRowProps {
    video: any;
    onClick: (video: any) => void;
    onDelete: (videoId: string) => void;
    isSelected: boolean;
    onToggleSelect: (videoId: string, selected: boolean) => void;
    statusBadge: ReactNode;
}

function truncateMiddle(value: string, maxLength = 34, tailLength = 12) {
    if (!value || value.length <= maxLength) return value;
    const startLength = Math.max(8, maxLength - tailLength - 3);
    return `${value.slice(0, startLength)}...${value.slice(-tailLength)}`;
}

function formatDateLabel(dateRaw?: string) {
    if (!dateRaw) return 'Sin fecha';

    const date = new Date(dateRaw);
    if (Number.isNaN(date.getTime())) return 'Sin fecha';

    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const dayDiff = Math.round(
        (startOfDate.getTime() - startOfToday.getTime()) / (1000 * 60 * 60 * 24),
    );

    const timePart = date.toLocaleTimeString('es-ES', {
        hour: '2-digit',
        minute: '2-digit',
    });

    if (dayDiff === 0) return `Hoy, ${timePart}`;
    if (dayDiff === -1) return `Ayer, ${timePart}`;

    return date.toLocaleDateString('es-ES', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
    });
}

export function VideoTableRow({
    video,
    onClick,
    onDelete,
    isSelected,
    onToggleSelect,
    statusBadge,
}: VideoTableRowProps) {
    const [menuOpen, setMenuOpen] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!menuOpen) return;

        const handleOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setMenuOpen(false);
            }
        };

        document.addEventListener('mousedown', handleOutside);
        return () => document.removeEventListener('mousedown', handleOutside);
    }, [menuOpen]);

    const title = video?.titulo || video?.nombre_archivo || 'Video sin titulo';
    const project = video?.workspace_nombre || 'Sin proyecto';
    const dateRaw = video?.fecha_subida || video?.created_at;
    const date = formatDateLabel(dateRaw);

    return (
        <div
            className="group grid grid-cols-12 gap-4 items-center px-6 py-5 bg-white hover:bg-slate-50/80 border-b border-slate-100 last:border-0 transition-all cursor-pointer"
            onClick={() => onClick(video)}
        >
            <div className="col-span-1">
                <input
                    type="checkbox"
                    checked={isSelected}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => onToggleSelect(video.id, e.target.checked)}
                    aria-label={`Seleccionar video ${title}`}
                    className="h-4 w-4 rounded-md border-slate-300 text-blue-600 focus:ring-blue-600/30 transition-colors cursor-pointer"
                />
            </div>

            <div className="col-span-2">
                <div className="h-16 w-28 rounded-xl bg-slate-100 border border-slate-200/60 overflow-hidden flex items-center justify-center relative shadow-sm group-hover:shadow-md transition-all duration-300 group-hover:scale-105">
                    <img
                        crossOrigin="use-credentials"
                        src={`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001'}/socio/thumbnail/${video.id}`}
                        alt={title}
                        className="absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                        onError={(e) => {
                            (e.target as HTMLImageElement).style.display = 'none';
                        }}
                    />
                    <Video size={24} className="text-slate-300 absolute" />
                    <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/10 transition-colors z-10" />
                </div>
            </div>

            <div className="col-span-9 sm:col-span-3 min-w-0 pr-4">
                <p className="font-semibold text-[15px] text-slate-800 truncate group-hover:text-slate-900 transition-colors" title={title}>
                    {truncateMiddle(title)}
                </p>
            </div>

            <div className="hidden sm:block sm:col-span-2">
                <p className="text-[14px] font-medium text-slate-600 truncate">{project}</p>
            </div>

            <div className="hidden sm:block sm:col-span-2">
                <p className="text-[13px] font-medium text-slate-500 inline-flex items-center gap-1.5">
                    <Clock size={14} className="text-slate-400" /> {date}
                </p>
            </div>

            <div className="hidden sm:block sm:col-span-1">{statusBadge}</div>

            <div className="hidden sm:flex sm:col-span-1 justify-end relative" ref={menuRef}>
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        setMenuOpen((prev) => !prev);
                    }}
                    className="p-2 text-slate-400 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition-all opacity-0 group-hover:opacity-100 focus:opacity-100"
                    title="Opciones"
                >
                    <MoreHorizontal size={18} />
                </button>

                {menuOpen && (
                    <div className="absolute right-0 top-10 z-30 w-44 rounded-2xl border border-slate-100 bg-white shadow-xl py-2 animate-in fade-in zoom-in-95 duration-200">
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                setMenuOpen(false);
                                onDelete(video.id);
                            }}
                            className="w-full px-4 py-2.5 text-left text-[14px] font-medium text-rose-600 hover:bg-rose-50 inline-flex items-center gap-2.5 transition-colors"
                        >
                            <Trash2 size={16} />
                            Eliminar Video
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
