import { useState } from 'react';
import { useNavigate, Link, useSearch } from '@tanstack/react-router';
import { useMutation } from '@tanstack/react-query';
import { User, Lock, AlertCircle, Loader2 } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useAuth } from '../context/AuthContext';

export default function Login() {
    const navigate = useNavigate();
    const search = useSearch({ strict: false });
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');

    const { login } = useAuth();

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
                    disabled={loginMutation.isPending}
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
