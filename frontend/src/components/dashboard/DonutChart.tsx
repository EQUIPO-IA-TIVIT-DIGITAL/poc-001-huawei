interface Stats {
    total: number;
    aprobados: number;
    pendientes: number;
    rechazados: number;
}

export function DonutChart({ stats }: { stats: Stats }) {
    const size = 120;
    const strokeWidth = 14;
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;

    const segments = [
        { value: stats.aprobados, color: '#10b981', label: 'Aprobados' },
        { value: stats.pendientes, color: '#f59e0b', label: 'Pendientes' },
        { value: stats.rechazados, color: '#f43f5e', label: 'Rechazados' },
    ];

    let offset = 0;
    const segmentPaths =
        stats.total > 0
            ? segments.map((seg) => {
                  const pct = seg.value / stats.total;
                  const dashLen = pct * circumference;
                  const dashOffset = -offset;
                  offset += dashLen;
                  return { ...seg, dashLen, dashOffset, pct };
              })
            : [];

    return (
        <div className="flex items-center gap-5">
            <div className="relative shrink-0">
                <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
                    <circle
                        cx={size / 2}
                        cy={size / 2}
                        r={radius}
                        fill="none"
                        stroke="#f3f4f6"
                        strokeWidth={strokeWidth}
                    />
                    {stats.total > 0
                        ? segmentPaths.map((seg, i) => (
                              <circle
                                  key={i}
                                  cx={size / 2}
                                  cy={size / 2}
                                  r={radius}
                                  fill="none"
                                  stroke={seg.color}
                                  strokeWidth={strokeWidth}
                                  strokeDasharray={`${seg.dashLen} ${circumference - seg.dashLen}`}
                                  strokeDashoffset={seg.dashOffset}
                                  strokeLinecap="round"
                                  className="transition-all duration-1000 ease-out"
                              />
                          ))
                        : null}
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-2xl font-extrabold text-gray-900 leading-none">{stats.total}</span>
                    <span className="text-[9px] text-gray-400 font-semibold uppercase tracking-wider mt-0.5">
                        videos
                    </span>
                </div>
            </div>
            <div className="space-y-2.5 flex-1 min-w-0">
                {segments.map((seg) => (
                    <div key={seg.label} className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                            <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: seg.color }} />
                            <span className="text-xs text-gray-600 truncate">{seg.label}</span>
                        </div>
                        <div className="flex items-baseline gap-1.5 shrink-0">
                            <span className="text-sm font-bold text-gray-900">{seg.value}</span>
                            <span className="text-[10px] text-gray-400">
                                {stats.total > 0 ? `${((seg.value / stats.total) * 100).toFixed(0)}%` : '-'}
                            </span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
