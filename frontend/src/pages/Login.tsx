import { useState } from 'react';
import { useNavigate, Link, useSearch } from '@tanstack/react-router';
import { useMutation } from '@tanstack/react-query';
import { Lock, User } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Alert, AlertDescription } from '../components/ui/alert';
import { useAuth } from '../context/AuthContext';
import { useTranslation } from '../i18n';

export default function Login() {
  const navigate = useNavigate();
  const search = useSearch({ strict: false });
  const { t } = useTranslation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const { login } = useAuth();

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () => {
      const redirectParams = search as { redirect?: string };
      navigate({ to: redirectParams.redirect || '/dashboard' });
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    loginMutation.mutate({ username, password });
  };

  return (
    <div>
      <div className="mb-8 text-center">
        <img
          src="/icon_tivit.svg"
          alt={t('common.appName')}
          className="mx-auto mb-5 h-14 w-14 rounded-xl object-contain"
        />
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          {t('auth.welcome')}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('auth.welcomeSubtitle')}</p>
      </div>

      {error && (
        <Alert variant="error" className="mb-6">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <form onSubmit={handleSubmit} className="space-y-5" noValidate>
        <div className="space-y-2">
          <Label htmlFor="login-username">{t('auth.username')}</Label>
          <Input
            id="login-username"
            name="username"
            type="text"
            autoComplete="username"
            placeholder={t('auth.usernamePlaceholder')}
            icon={<User />}
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="login-password">{t('auth.password')}</Label>
            <a
              href="#"
              className="text-xs font-medium text-primary transition-colors hover:text-brand-hover"
            >
              {t('auth.forgotPassword')}
            </a>
          </div>
          <Input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            placeholder={t('auth.passwordPlaceholder')}
            icon={<Lock />}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>

        <Button type="submit" fullWidth loading={loginMutation.isPending}>
          {loginMutation.isPending ? t('auth.loggingIn') : t('auth.login')}
        </Button>

        <p className="text-center text-sm text-muted-foreground">
          {t('auth.noAccount')}{' '}
          <Link
            to="/register"
            className="font-semibold text-primary transition-colors hover:text-brand-hover"
          >
            {t('auth.registerHere')}
          </Link>
        </p>
      </form>
    </div>
  );
}
