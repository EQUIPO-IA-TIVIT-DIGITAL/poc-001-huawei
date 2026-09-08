import { useState, useEffect } from 'react';
import { useNavigate, Link, useSearch } from '@tanstack/react-router';
import { useMutation } from '@tanstack/react-query';
import { User, Lock, AlertCircle, Loader2 } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useAuth } from '../context/AuthContext';
import { authService } from '../services/auth';

// Mensajes de error para los códigos del flujo OAuth2 de Azure AD
const OAUTH_ERROR_MESSAGES: Record<string, string> = {
    microsoft_denied: 'Cancelaste el inicio de sesión con Microsoft.',
    no_code: 'No se recibió autorización de Microsoft. Intenta nuevamente.',
    invalid_state: 'Error de seguridad en el inicio de sesión. Intenta nuevamente.',
    token_failed: 'No se pudo completar la autenticación con Microsoft.',
    token_empty: 'Error al obtener credenciales de Microsoft.',
    graph_failed: 'No se pudo obtener tu perfil de Microsoft.',
    no_email: 'Tu cuenta de Microsoft no tiene un email accesible.',
    server_error: 'Error interno del servidor. Por favor, intenta más tarde.',
};

export default function Login() {
    const navigate = useNavigate();
    const search = useSearch({ strict: false });
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isMicrosoftLoading, setIsMicrosoftLoading] = useState(false);

    const { login } = useAuth();

    // Leer error del query string (viene del callback de Azure AD)
    useEffect(() => {
        const params = search as { error?: string; redirect?: string };
        if (params.error) {
            const errorMsg = OAUTH_ERROR_MESSAGES[params.error] || 'Error al iniciar sesión con Microsoft.';
            setError(errorMsg);
        }
    }, [search]);

    const _doNavigate = () => {
        const redirectParams = search as { redirect?: string };
        const redirectTo = redirectParams.redirect || '/dashboard';
        navigate({ to: redirectTo });
    };

    const loginMutation = useMutation({
        mutationFn: login,
        onSuccess: () => {
            _doNavigate();
        },
        onError: (err: any) => {
            setError(err.message);
        }
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        loginMutation.mutate({ username, password });
    };

    const handleMicrosoftLogin = () => {
        setError('');
        setIsMicrosoftLoading(true);
        // Redirige al backend → Microsoft login page
        authService.loginWithMicrosoft();
    };

    return (
        <div className="p-8 pt-10">
            {/* Header */}
            <div className="mb-8 text-center">
                <div className="mb-6 flex justify-center">
                    <img src="/icon_tivit.svg" alt="TIVIT CU002" className="h-16 w-auto object-cover drop-shadow-lg rounded-lg" />
                </div>
                <h1 className="mb-2 text-2xl font-bold text-white">Bienvenido</h1>
                <p className="text-sm text-white/50">Ingresa a tu cuenta para continuar</p>
            </div>

            {/* Error banner */}
            {error && (
                <div className="flex items-center gap-2 rounded-lg bg-error/10 p-4 text-sm text-error border border-error/20 mb-6">
                    <AlertCircle size={16} className="shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            {/* Botón Microsoft */}
            <button
                type="button"
                onClick={handleMicrosoftLogin}
                disabled={isMicrosoftLoading || loginMutation.isPending}
                className="w-full flex items-center justify-center gap-3 rounded-lg border border-white/15 bg-white/5 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-white/10 hover:border-white/25 disabled:opacity-50 disabled:cursor-not-allowed mb-6"
            >
                {isMicrosoftLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                    /* Logo oficial de Microsoft */
                    <svg width="18" height="18" viewBox="0 0 21 21" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect x="1" y="1" width="9" height="9" fill="#F25022"/>
                        <rect x="11" y="1" width="9" height="9" fill="#7FBA00"/>
                        <rect x="1" y="11" width="9" height="9" fill="#00A4EF"/>
                        <rect x="11" y="11" width="9" height="9" fill="#FFB900"/>
                    </svg>
                )}
                {isMicrosoftLoading ? 'Redirigiendo...' : 'Continuar con Microsoft'}
            </button>

            {/* Separador */}
            <div className="flex items-center gap-3 mb-6">
                <div className="flex-1 border-t border-white/10" />
                <span className="text-xs text-white/30 shrink-0">o ingresa con usuario y contraseña</span>
                <div className="flex-1 border-t border-white/10" />
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
                <div className="space-y-4">
                    <div className="space-y-2">
                        <label className="text-sm font-medium text-white/80">Nombre de Usuario</label>
                        <Input
                            type="text"
                            placeholder="tu_usuario"
                            icon={<User size={18} />}
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:bg-white/10"
                            required
                        />
                    </div>

                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <label className="text-sm font-medium text-white/80">Contraseña</label>
                            <a href="#" className="text-xs text-white hover:text-white/80 transition-colors">
                                ¿Olvidaste tu contraseña?
                            </a>
                        </div>
                        <Input
                            type="password"
                            placeholder="••••••••"
                            icon={<Lock size={18} />}
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:bg-white/10"
                            required
                        />
                    </div>
                </div>

                <Button
                    type="submit"
                    fullWidth
                    disabled={loginMutation.isPending || isMicrosoftLoading}
                >
                    {loginMutation.isPending ? (
                        <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Ingresando...
                        </>
                    ) : (
                        'Iniciar Sesión'
                    )}
                </Button>

                <div className="text-center text-sm text-white/50">
                    ¿No tienes una cuenta?{' '}
                    <Link to="/register" className="font-medium text-white hover:underline">
                        Regístrate aquí
                    </Link>
                </div>
            </form>
        </div>
    );
}
