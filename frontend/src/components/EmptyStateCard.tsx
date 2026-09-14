import type { ReactNode } from 'react';
import { cn } from '../lib/utils';
import { Button } from './ui/button';

interface EmptyStateFeature {
  icon?: ReactNode;
  label: string;
}

interface EmptyStateCardProps {
  icon: ReactNode;
  title: string;
  description: string;
  primaryActionLabel: string;
  onPrimaryAction: () => void;
  primaryActionIcon?: ReactNode;
  features?: EmptyStateFeature[];
  className?: string;
}

export function EmptyStateCard({
  icon,
  title,
  description,
  primaryActionLabel,
  onPrimaryAction,
  primaryActionIcon,
  features = [],
  className,
}: EmptyStateCardProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center rounded-xl border border-dashed border-border bg-card p-10 text-center lg:p-14',
        className,
      )}
    >
      <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-soft text-brand [&_svg]:size-7">
        {icon}
      </div>
      <h3 className="text-lg font-semibold text-foreground">{title}</h3>
      <p className="mt-1.5 max-w-xl text-sm text-muted-foreground">{description}</p>

      {features.length > 0 && (
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {features.map((feature) => (
            <span
              key={feature.label}
              className="inline-flex items-center gap-2 rounded-full border border-brand-border bg-brand-soft px-3 py-1.5 text-sm font-medium text-brand-hover [&_svg]:size-4"
            >
              {feature.icon}
              {feature.label}
            </span>
          ))}
        </div>
      )}

      <Button onClick={onPrimaryAction} className="mt-7">
        {primaryActionIcon}
        {primaryActionLabel}
      </Button>
    </div>
  );
}
