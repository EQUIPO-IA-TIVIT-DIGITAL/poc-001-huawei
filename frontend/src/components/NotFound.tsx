import { Link } from '@tanstack/react-router';
import { Button } from './ui/button';

interface NotFoundProps {
  to?: string;
  backLabel?: string;
}

export function NotFound({ to = '/dashboard', backLabel = 'Volver al Dashboard' }: NotFoundProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="text-center">
        <p className="text-sm font-semibold uppercase tracking-widest text-primary">404</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-foreground">
          Página no encontrada
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          La página que buscas no existe o fue movida.
        </p>
        <Button asChild className="mt-6">
          <Link to={to}>{backLabel}</Link>
        </Button>
      </div>
    </div>
  );
}
