import * as React from 'react';
import { cn } from '../../lib/utils';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  icon?: React.ReactNode;
  invalid?: boolean;
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, icon, invalid, 'aria-invalid': ariaInvalid, ...props }, ref) => {
    const isInvalid = invalid ?? (ariaInvalid === true || ariaInvalid === 'true');

    return (
      <div className="relative w-full">
        {icon && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute left-3.5 top-1/2 flex -translate-y-1/2 text-muted-foreground [&_svg]:size-4"
          >
            {icon}
          </span>
        )}
        <input
          type={type}
          ref={ref}
          aria-invalid={ariaInvalid ?? (invalid || undefined)}
          className={cn(
            'flex h-10 w-full rounded-md border border-input bg-card px-3.5 text-sm text-foreground transition-colors',
            'placeholder:text-muted-foreground',
            'focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/30',
            'disabled:cursor-not-allowed disabled:opacity-50',
            'file:border-0 file:bg-transparent file:text-sm file:font-medium',
            isInvalid &&
              'border-error focus-visible:border-error focus-visible:ring-error/30',
            icon && 'pl-10',
            className,
          )}
          {...props}
        />
      </div>
    );
  },
);
Input.displayName = 'Input';

export { Input };
