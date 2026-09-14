import { AlertCircle, RefreshCw } from 'lucide-react';
import { useTranslation } from '../../i18n';
import { Alert, AlertDescription, AlertTitle } from './alert';
import { Button } from './button';
import { cn } from '../../lib/utils';

export interface ErrorStateProps {
  title?: string;
  description?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({ title, description, onRetry, className }: ErrorStateProps) {
  const { t } = useTranslation();

  return (
    <Alert variant="error" className={cn('flex-col items-start sm:flex-row sm:items-center', className)}>
      <AlertCircle aria-hidden="true" />
      <div className="flex-1 space-y-1">
        <AlertTitle>{title ?? t('common.error')}</AlertTitle>
        <AlertDescription>{description ?? t('common.errorGeneric')}</AlertDescription>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-1 sm:mt-0">
          <RefreshCw aria-hidden="true" />
          {t('common.retry')}
        </Button>
      )}
    </Alert>
  );
}
