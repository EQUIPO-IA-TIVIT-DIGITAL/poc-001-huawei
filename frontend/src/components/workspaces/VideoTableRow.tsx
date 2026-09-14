import { Clock, MoreHorizontal, Play, Trash2, Video } from 'lucide-react';
import type { ReactNode } from 'react';
import { Button } from '../ui/button';
import { Checkbox } from '../ui/checkbox';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';
import { getApiBaseUrl } from '../../lib/backendUrl';
import { useTranslation } from '../../i18n';
import { cn } from '../../lib/utils';

interface VideoRow {
  id: string;
  titulo?: string;
  nombre_archivo?: string;
  workspace_nombre?: string;
  fecha_subida?: string;
  created_at?: string;
  resultado_ia?: string;
  estado?: string;
}

interface VideoTableRowProps {
  video: VideoRow;
  onClick: (video: VideoRow) => void;
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

export function VideoTableRow({
  video,
  onClick,
  onDelete,
  isSelected,
  onToggleSelect,
  statusBadge,
}: VideoTableRowProps) {
  const { t, formatDate } = useTranslation();

  const title = video?.titulo || video?.nombre_archivo || t('dashboard.videoFallbackTitle');
  const project = video?.workspace_nombre || t('common.noProject');
  const dateRaw = video?.fecha_subida || video?.created_at;

  const formatDateLabel = (value?: string) => {
    if (!value) return t('common.noDate');
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return t('common.noDate');

    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const dayDiff = Math.round(
      (startOfDate.getTime() - startOfToday.getTime()) / (1000 * 60 * 60 * 24),
    );

    if (dayDiff === 0) return `${t('common.today')}, ${formatDate(date, { hour: '2-digit', minute: '2-digit' })}`;
    if (dayDiff === -1)
      return `${t('common.yesterday')}, ${formatDate(date, { hour: '2-digit', minute: '2-digit' })}`;

    return formatDate(date, { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  const date = formatDateLabel(dateRaw);

  return (
    <div
      className={cn(
        'group grid grid-cols-12 items-center gap-4 border-b border-border px-4 py-4 transition-colors last:border-0 sm:px-6',
        isSelected ? 'bg-brand-soft/50' : 'bg-card hover:bg-muted/60',
      )}
    >
      <div className="col-span-1 flex items-center">
        <Checkbox
          checked={isSelected}
          onCheckedChange={(checked) => onToggleSelect(video.id, checked === true)}
          aria-label={t('common.selectVideo', { title })}
        />
      </div>

      <div className="col-span-3 sm:col-span-2">
        <button
          type="button"
          onClick={() => onClick(video)}
          aria-label={`${t('common.play')}: ${title}`}
          className="group/thumb relative flex h-14 w-24 items-center justify-center overflow-hidden rounded-lg border border-border bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <img
            crossOrigin="use-credentials"
            src={`${getApiBaseUrl()}/socio/thumbnail/${video.id}`}
            alt=""
            className="absolute inset-0 h-full w-full object-cover"
            onError={(event) => {
              event.currentTarget.style.display = 'none';
            }}
          />
          <Video size={22} className="absolute text-gray-300" aria-hidden="true" />
          <span className="absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover/thumb:bg-black/20">
            <Play
              size={18}
              className="text-white opacity-0 transition-opacity group-hover/thumb:opacity-100"
              fill="currentColor"
              aria-hidden="true"
            />
          </span>
        </button>
      </div>

      <div className="col-span-8 min-w-0 sm:col-span-3">
        <button
          type="button"
          onClick={() => onClick(video)}
          title={title}
          className="max-w-full truncate text-left text-sm font-semibold text-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:underline"
        >
          {truncateMiddle(title)}
        </button>
      </div>

      <div className="hidden min-w-0 sm:col-span-2 sm:block">
        <p className="truncate text-sm text-muted-foreground">{project}</p>
      </div>

      <div className="hidden sm:col-span-2 sm:block">
        <p className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Clock size={13} aria-hidden="true" /> {date}
        </p>
      </div>

      <div className="hidden sm:col-span-1 sm:block">{statusBadge}</div>

      <div className="col-span-12 flex justify-end sm:col-span-1">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t('common.options')}
              className="opacity-0 transition-opacity focus:opacity-100 group-hover:opacity-100"
            >
              <MoreHorizontal aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem destructive onSelect={() => onDelete(video.id)}>
              <Trash2 aria-hidden="true" />
              {t('common.deleteVideo')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}

export type { VideoRow };
