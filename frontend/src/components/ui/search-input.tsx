import * as React from 'react';
import { Search, X } from 'lucide-react';
import { useTranslation } from '../../i18n';
import { Input, type InputProps } from './input';

export interface SearchInputProps extends Omit<InputProps, 'icon'> {
  onClear?: () => void;
}

const SearchInput = React.forwardRef<HTMLInputElement, SearchInputProps>(
  ({ onClear, value, className, ...props }, ref) => {
    const { t } = useTranslation();
    const hasValue = value !== undefined && value !== '';

    return (
      <div className="relative w-full">
        <Input ref={ref} type="search" value={value} icon={<Search />} className={className} {...props} />
        {hasValue && onClear && (
          <button
            type="button"
            onClick={onClear}
            aria-label={t('common.clearSelection')}
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-0.5 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X size={16} aria-hidden="true" />
          </button>
        )}
      </div>
    );
  },
);
SearchInput.displayName = 'SearchInput';

export { SearchInput };
