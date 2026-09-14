import { useState } from 'react';
import { useNavigate, Link } from '@tanstack/react-router';
import { useMutation } from '@tanstack/react-query';
import { ArrowRight, Lock, Mail, User } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Alert, AlertDescription } from '../components/ui/alert';
import { apiRequest } from '../lib/api';
import { useTranslation } from '../i18n';

interface RegisterFormData {
  nombre: string;
  username: string;
  email: string;
  password: string;
  confirmPassword: string;
}

export default function Register() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [formData, setFormData] = useState<RegisterFormData>({
    nombre: '',
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [error, setError] = useState('');

  const registerMutation = useMutation({
    mutationFn: async (data: RegisterFormData) =>
      apiRequest('/registro/socio', {
        method: 'POST',
        body: JSON.stringify({
          username: data.username,
          nombre_completo: data.nombre,
          email: data.email,
          password: data.password,
          password_confirm: data.confirmPassword,
        }),
      }),
    onSuccess: () => {
      navigate({ to: '/login', search: { redirect: undefined } });
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setError('');

    if (formData.password !== formData.confirmPassword) {
      setError(t('auth.passwordMismatch'));
      return;
    }

    registerMutation.mutate(formData);
  };

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
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
          {t('auth.registerTitle')}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('auth.registerSubtitle')}</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5" noValidate>
        {error && (
          <Alert variant="error">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="register-name">{t('auth.fullName')}</Label>
            <Input
              id="register-name"
              name="nombre"
              type="text"
              autoComplete="name"
              placeholder="Juan Pérez"
              icon={<User />}
              value={formData.nombre}
              onChange={handleChange}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="register-username">{t('auth.username')}</Label>
            <Input
              id="register-username"
              name="username"
              type="text"
              autoComplete="username"
              placeholder="usuario123"
              icon={<User />}
              value={formData.username}
              onChange={handleChange}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="register-email">{t('auth.email')}</Label>
            <Input
              id="register-email"
              name="email"
              type="email"
              autoComplete="email"
              placeholder="tu@email.com"
              icon={<Mail />}
              value={formData.email}
              onChange={handleChange}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="register-password">{t('auth.password')}</Label>
            <Input
              id="register-password"
              name="password"
              type="password"
              autoComplete="new-password"
              placeholder={t('auth.passwordPlaceholder')}
              icon={<Lock />}
              value={formData.password}
              onChange={handleChange}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="register-confirm">{t('auth.confirmPassword')}</Label>
            <Input
              id="register-confirm"
              name="confirmPassword"
              type="password"
              autoComplete="new-password"
              placeholder={t('auth.passwordPlaceholder')}
              icon={<Lock />}
              value={formData.confirmPassword}
              onChange={handleChange}
              required
            />
          </div>
        </div>

        <Button type="submit" fullWidth loading={registerMutation.isPending} className="mt-2">
          {registerMutation.isPending ? t('auth.registering') : t('auth.register')}
          {!registerMutation.isPending && <ArrowRight aria-hidden="true" />}
        </Button>

        <p className="text-center text-sm text-muted-foreground">
          {t('auth.haveAccount')}{' '}
          <Link
            to="/login"
            search={{ redirect: undefined }}
            className="font-semibold text-primary transition-colors hover:text-brand-hover"
          >
            {t('auth.login')}
          </Link>
        </p>
      </form>
    </div>
  );
}
