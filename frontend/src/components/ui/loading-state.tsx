import { Spinner } from './spinner';
import { cn } from '../../lib/utils';

export interface LoadingStateProps {
  label?: string;
  className?: string;
}

export function LoadingState({ label = 'Cargando...', className }: LoadingStateProps) {
  return (
    <div
      className={cn(
        'flex min-h-40 w-full flex-col items-center justify-center gap-3 py-10',
        className,
      )}
    >
      <Spinner size="lg" className="text-primary" label={label} />
      <p className="text-sm font-medium text-muted-foreground">{label}</p>
    </div>
  );
}
