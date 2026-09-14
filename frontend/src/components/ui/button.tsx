import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { Loader2 } from 'lucide-react';
import { cn } from '../../lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-60 [&_svg]:pointer-events-none [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default:
          'bg-primary text-primary-foreground shadow-[0_1px_2px_rgba(15,17,21,0.08)] hover:bg-brand-hover active:bg-brand-active',
        secondary:
          'bg-secondary text-secondary-foreground hover:bg-gray-200 border border-border',
        outline:
          'border border-border bg-card text-foreground hover:bg-muted hover:text-foreground',
        ghost: 'text-muted-foreground hover:bg-muted hover:text-foreground',
        danger:
          'bg-destructive text-destructive-foreground hover:bg-rose-700 active:bg-rose-800',
        success: 'bg-success text-success-foreground hover:bg-green-700',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        xs: 'h-8 rounded-md px-2.5 text-xs [&_svg]:size-3.5',
        sm: 'h-9 rounded-md px-3.5 text-[13px] [&_svg]:size-4',
        default: 'h-10 rounded-md px-4 text-sm [&_svg]:size-4',
        lg: 'h-12 rounded-md px-6 text-[15px] [&_svg]:size-[18px]',
        icon: 'h-10 w-10 p-0 [&_svg]:size-[18px]',
        'icon-sm': 'h-8 w-8 p-0 [&_svg]:size-4',
      },
      fullWidth: {
        true: 'w-full',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
      fullWidth: false,
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { className, variant, size, fullWidth, asChild = false, loading = false, disabled, children, ...props },
    ref,
  ) => {
    const Comp = asChild ? Slot : 'button';

    return (
      <Comp
        className={cn(buttonVariants({ variant, size, fullWidth, className }))}
        ref={ref}
        type={asChild ? undefined : (props.type ?? 'button')}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading ? (
          <>
            <Loader2 className="animate-spin" aria-hidden="true" />
            {children}
          </>
        ) : (
          children
        )}
      </Comp>
    );
  },
);
Button.displayName = 'Button';

export { Button, buttonVariants };
