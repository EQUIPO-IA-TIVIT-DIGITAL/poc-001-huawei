import type { LucideIcon } from 'lucide-react';
import { cva } from 'class-variance-authority';
import { cn } from '../../lib/utils';
import { Progress } from './progress';
import { Skeleton } from './skeleton';

type StatTone = 'brand' | 'info' | 'success' | 'warning' | 'neutral';

const iconVariants = cva(
  'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg [&_svg]:size-5',
  {
    variants: {
      tone: {
        brand: 'bg-brand-soft text-brand',
        info: 'bg-info-surface text-info',
        success: 'bg-success-surface text-success',
        warning: 'bg-warning-surface text-warning',
        neutral: 'bg-muted text-muted-foreground',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
);

export interface StatCardProps {
  title: string;
  value: number | string;
  total?: number;
  icon: LucideIcon;
  tone?: StatTone;
  hint?: string;
  hideProgress?: boolean;
  isLoading?: boolean;
  className?: string;
}

export function StatCard({
  title,
  value,
  total,
  icon: Icon,
  tone = 'neutral',
  hint,
  hideProgress = false,
  isLoading = false,
  className,
}: StatCardProps) {
  const numericValue = typeof value === 'number' ? value : Number(value);
  const percentage =
    total && total > 0 && Number.isFinite(numericValue)
      ? Math.min(100, Math.round((numericValue / total) * 100))
      : 0;

  if (isLoading) {
    return (
      <div className={cn('rounded-xl border border-border bg-card p-5', className)}>
        <div className="flex items-center justify-between gap-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-10 w-10 rounded-lg" />
        </div>
        <Skeleton className="mt-4 h-8 w-16" />
      </div>
    );
  }

  return (
    <div className={cn('rounded-xl border border-border bg-card p-5 shadow-card', className)}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-muted-foreground">{title}</p>
        <div className={iconVariants({ tone })}>
          <Icon aria-hidden="true" />
        </div>
      </div>
      <p className="mt-3 text-2xl font-semibold tracking-tight text-foreground">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      {!hideProgress && total !== undefined && total > 0 && (
        <Progress
          value={percentage}
          aria-label={title}
          className="mt-4 h-1.5"
        />
      )}
    </div>
  );
}
