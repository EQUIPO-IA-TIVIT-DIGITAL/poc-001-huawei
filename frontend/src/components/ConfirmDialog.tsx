import { AlertTriangle, Trash2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from './ui/dialog';
import { Button } from './ui/button';
import { useTranslation } from '../i18n';
import { cn } from '../lib/utils';

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'danger' | 'warning';
  loading?: boolean;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  onConfirm,
  title,
  description,
  confirmText,
  cancelText,
  variant = 'danger',
  loading = false,
}: ConfirmDialogProps) {
  const { t } = useTranslation();
  const isDanger = variant === 'danger';
  const Icon = isDanger ? Trash2 : AlertTriangle;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div
            className={cn(
              'mb-1 flex h-11 w-11 items-center justify-center rounded-full',
              isDanger ? 'bg-error-surface text-error' : 'bg-warning-surface text-warning',
            )}
          >
            <Icon size={20} aria-hidden="true" />
          </div>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={loading}
            className="sm:flex-1"
          >
            {cancelText ?? t('common.cancel')}
          </Button>
          <Button
            variant={isDanger ? 'danger' : 'default'}
            onClick={onConfirm}
            loading={loading}
            className={cn('sm:flex-1', !isDanger && 'bg-warning hover:bg-amber-700')}
          >
            {confirmText ?? t('common.accept')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
