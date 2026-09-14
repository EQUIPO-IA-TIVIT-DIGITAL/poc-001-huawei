import * as React from 'react';
import { cn } from '../../lib/utils';

interface PageContainerProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export function PageContainer({ className, children, ...props }: PageContainerProps) {
  return (
    <div className={cn('mx-auto w-full max-w-[1400px] space-y-6', className)} {...props}>
      {children}
    </div>
  );
}

export function PageSection({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  return (
    <section className={cn('space-y-4', className)} {...props}>
      {children}
    </section>
  );
}
