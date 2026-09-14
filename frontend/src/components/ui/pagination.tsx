import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from '../../i18n';
import { Button } from './button';
import { cn } from '../../lib/utils';

export interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  totalItems?: number;
  rowsPerPage?: number;
  rowsPerPageOptions?: number[];
  onRowsPerPageChange?: (rows: number) => void;
  className?: string;
}

export function Pagination({
  page,
  totalPages,
  onPageChange,
  totalItems,
  rowsPerPage,
  rowsPerPageOptions = [10, 25, 50],
  onRowsPerPageChange,
  className,
}: PaginationProps) {
  const { t } = useTranslation();
  const safeTotalPages = Math.max(1, totalPages);
  const isFirst = page <= 1;
  const isLast = page >= safeTotalPages;

  return (
    <div
      className={cn(
        'flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        {totalItems !== undefined && (
          <span>
            {totalItems} {t('common.total').toLowerCase()}
          </span>
        )}
        {rowsPerPage !== undefined && onRowsPerPageChange && (
          <label className="flex items-center gap-2">
            <span className="hidden sm:inline">{t('common.rowsPerPage')}</span>
            <select
              value={rowsPerPage}
              onChange={(event) => onRowsPerPageChange(Number(event.target.value))}
              className="h-8 rounded-md border border-input bg-card px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {rowsPerPageOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">
          {t('common.page')} {page} / {safeTotalPages}
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon-sm"
            onClick={() => onPageChange(page - 1)}
            disabled={isFirst}
            aria-label={t('common.previousPage')}
          >
            <ChevronLeft aria-hidden="true" />
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            onClick={() => onPageChange(page + 1)}
            disabled={isLast}
            aria-label={t('common.nextPage')}
          >
            <ChevronRight aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  );
}
