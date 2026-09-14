import { Link } from '@tanstack/react-router';
import { ChevronRight, Home } from 'lucide-react';
import { cn } from '../lib/utils';
import { useTranslation } from '../i18n';

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

interface BreadcrumbsProps {
  items: BreadcrumbItem[];
  className?: string;
  showHome?: boolean;
}

export function Breadcrumbs({ items, className, showHome = true }: BreadcrumbsProps) {
  const { t } = useTranslation();

  return (
    <nav aria-label={t('nav.breadcrumbLabel')} className={cn('flex items-center gap-2 text-sm', className)}>
      {showHome && (
        <>
          <Link
            to="/dashboard"
            className="flex items-center gap-1.5 text-muted-foreground transition-colors hover:text-primary"
          >
            <Home size={15} aria-hidden="true" />
            <span>{t('nav.breadcrumbHome')}</span>
          </Link>
          {items.length > 0 && <ChevronRight size={15} className="text-gray-300" aria-hidden="true" />}
        </>
      )}

      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <div key={`${item.label}-${index}`} className="flex items-center gap-2">
            {index > 0 && <ChevronRight size={15} className="text-gray-300" aria-hidden="true" />}
            {item.to && !isLast ? (
              <Link
                to={item.to}
                className="text-muted-foreground transition-colors hover:text-primary"
              >
                {item.label}
              </Link>
            ) : (
              <span aria-current="page" className="font-medium text-foreground">
                {item.label}
              </span>
            )}
          </div>
        );
      })}
    </nav>
  );
}
