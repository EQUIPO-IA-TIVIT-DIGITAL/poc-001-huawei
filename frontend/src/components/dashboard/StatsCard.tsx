import { LucideIcon } from 'lucide-react';

interface StatsCardProps {
    title: string;
    value: number;
    total: number;
    icon: LucideIcon;
    bgFrom: string;
    bgTo: string;
    iconBg: string;
    delay: number;
    hideProgress?: boolean;
}

export function StatsCard({
    title,
    value,
    total,
    icon: Icon,
    bgFrom,
    bgTo,
    iconBg,
    delay,
    hideProgress,
}: StatsCardProps) {
    const percentage = total > 0 ? (value / total) * 100 : 0;

    return (
        <div
            className="group relative bg-white rounded-3xl border border-slate-200/60 p-5 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-md animate-in fade-in slide-in-from-bottom-4"
            style={{ animationDelay: `${delay}ms` }}
        >
            <div className="flex flex-col h-full justify-between gap-3">
                <div className="flex items-start justify-between">
                    <div className={`p-3 rounded-2xl ${iconBg} bg-opacity-20 flex items-center justify-center`}>
                        <Icon size={20} className="text-current drop-shadow-sm" strokeWidth={2.5} />
                    </div>
                    <span className="text-[11px] font-bold text-slate-400 uppercase tracking-[0.1em]">
                        {title}
                    </span>
                </div>
                <div>
                    <p className="text-3xl font-extrabold text-slate-800 tabular-nums leading-none tracking-tight">{value}</p>
                </div>
                {!hideProgress && (
                    <div className="flex items-center gap-2 mt-1">
                        <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div
                                className={`h-full rounded-full bg-gradient-to-r ${bgFrom} ${bgTo} transition-all duration-1000 ease-out`}
                                style={{ width: `${percentage}%` }}
                            />
                        </div>
                        <span className="text-[11px] font-bold text-slate-500 whitespace-nowrap">{percentage.toFixed(0)}%</span>
                    </div>
                )}
            </div>
        </div>
    );
}
