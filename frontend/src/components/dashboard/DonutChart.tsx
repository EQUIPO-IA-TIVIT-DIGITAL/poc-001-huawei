import { useTranslation } from '../../i18n';

interface Stats {
  total: number;
  aprobados: number;
  pendientes: number;
  rechazados: number;
}

export function DonutChart({ stats }: { stats: Stats }) {
  const { t } = useTranslation();
  const size = 120;
  const strokeWidth = 14;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  const segments = [
    { value: stats.aprobados, color: 'var(--color-success)', label: t('dashboard.approved') },
    { value: stats.pendientes, color: 'var(--color-warning)', label: t('dashboard.pending') },
    { value: stats.rechazados, color: 'var(--color-error)', label: 'Rechazados' },
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

  const ariaLabel = segments
    .map((seg) => `${seg.label}: ${seg.value}`)
    .join(', ');

  return (
    <div className="flex items-center gap-5">
      <div className="relative shrink-0">
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="-rotate-90"
          role="img"
          aria-label={ariaLabel}
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--color-muted)"
            strokeWidth={strokeWidth}
          />
          {segmentPaths.map((seg, index) => (
            <circle
              key={index}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={seg.color}
              strokeWidth={strokeWidth}
              strokeDasharray={`${seg.dashLen} ${circumference - seg.dashLen}`}
              strokeDashoffset={seg.dashOffset}
              strokeLinecap="round"
              className="transition-all duration-700 ease-out"
            />
          ))}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold leading-none text-foreground">{stats.total}</span>
          <span className="mt-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            videos
          </span>
        </div>
      </div>

      <div className="min-w-0 flex-1 space-y-2.5">
        {segments.map((seg) => (
          <div key={seg.label} className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2">
              <span
                aria-hidden="true"
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: seg.color }}
              />
              <span className="truncate text-xs text-muted-foreground">{seg.label}</span>
            </div>
            <div className="flex shrink-0 items-baseline gap-1.5">
              <span className="text-sm font-semibold text-foreground">{seg.value}</span>
              <span className="text-[11px] text-muted-foreground">
                {stats.total > 0 ? `${((seg.value / stats.total) * 100).toFixed(0)}%` : '-'}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
