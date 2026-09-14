import { cva } from 'class-variance-authority';
import {
  Ban,
  CheckCircle2,
  Circle,
  Clock,
  FileEdit,
  Loader2,
  XCircle,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useTranslation } from '../../i18n';
import type { TranslationKey } from '../../i18n/es';

export type AppStatus =
  | 'approved'
  | 'rejected'
  | 'processing'
  | 'uploading'
  | 'pending'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'draft'
  | 'active'
  | 'inactive';

type Tone = 'success' | 'error' | 'warning' | 'info' | 'neutral' | 'brand';

const STATUS_CONFIG: Record<
  AppStatus,
  { tone: Tone; labelKey: TranslationKey; Icon: typeof Circle; spin?: boolean }
> = {
  approved: { tone: 'success', labelKey: 'status.approved', Icon: CheckCircle2 },
  completed: { tone: 'success', labelKey: 'status.completed', Icon: CheckCircle2 },
  active: { tone: 'success', labelKey: 'status.active', Icon: Circle },
  rejected: { tone: 'error', labelKey: 'status.rejected', Icon: XCircle },
  failed: { tone: 'error', labelKey: 'status.failed', Icon: XCircle },
  cancelled: { tone: 'error', labelKey: 'status.cancelled', Icon: Ban },
  processing: { tone: 'warning', labelKey: 'status.processing', Icon: Loader2, spin: true },
  pending: { tone: 'warning', labelKey: 'status.pending', Icon: Clock },
  uploading: { tone: 'info', labelKey: 'status.uploading', Icon: Loader2, spin: true },
  draft: { tone: 'neutral', labelKey: 'status.draft', Icon: FileEdit },
  inactive: { tone: 'neutral', labelKey: 'status.inactive', Icon: Circle },
};

const toneVariants = cva(
  'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold [&_svg]:size-3.5',
  {
    variants: {
      tone: {
        success: 'border-success-border bg-success-surface text-green-700',
        error: 'border-error-border bg-error-surface text-rose-700',
        warning: 'border-warning-border bg-warning-surface text-amber-700',
        info: 'border-info-border bg-info-surface text-blue-700',
        neutral: 'border-border bg-muted text-muted-foreground',
        brand: 'border-brand-border bg-brand-soft text-brand-hover',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
);

export interface StatusBadgeProps {
  status: AppStatus;
  label?: string;
  className?: string;
  showIcon?: boolean;
}

export function StatusBadge({ status, label, className, showIcon = true }: StatusBadgeProps) {
  const { t } = useTranslation();
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  const { Icon, spin } = config;

  return (
    <span className={cn(toneVariants({ tone: config.tone }), className)}>
      {showIcon && <Icon className={cn(spin && 'animate-spin')} aria-hidden="true" />}
      {label ?? t(config.labelKey)}
    </span>
  );
}

export { toneVariants };
