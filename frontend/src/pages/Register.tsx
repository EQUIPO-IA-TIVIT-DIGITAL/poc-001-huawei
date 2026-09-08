import { useState } from 'react';
import { useNavigate, Link } from '@tanstack/react-router';
import { useMutation } from '@tanstack/react-query';
import { Video, Mail, Lock, User, AlertCircle, Loader2, ArrowRight } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { apiRequest } from '../lib/api';

export default function Register() {
    const navigate = useNavigate();
    const [formData, setFormData] = useState({
        nombre: '',
        username: '',
        email: '',
        password: '',
        confirmPassword: ''
    });
    const [error, setError] = useState('');

    const registerMutation = useMutation({
        mutationFn: async (data: any) => {
            return apiRequest('/registro/socio', {
                method: 'POST',
                body: JSON.stringify({
                    username: data.username,
                    nombre_completo: data.nombre,
                    email: data.email,
                    password: data.password,
                    password_confirm: data.confirmPassword
                })
            });
        },
        onSuccess: () => {
            navigate({ to: '/login', search: { redirect: undefined } });
        },
        onError: (err) => {
            setError(err.message);
        }
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (formData.password !== formData.confirmPassword) {
            setError('Las contraseñas no coinciden');
            return;
        }

        registerMutation.mutate(formData);
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    return (
        <div className="p-8 pt-6">
            <div className="mb-8 text-center">
                <div className="mb-6 flex justify-center">
                    <img src="/icon_tivit.svg" alt="TIVIT CU002" className="h-24 w-auto object-contain drop-shadow-2xl" />
                </div>
                <h1 className="mb-2 text-2xl font-bold text-white">Crear Cuenta</h1>
                <p className="text-sm text-white/50">Únete a TIVIT CU002 hoy mismo</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
                {error && (
                    <div className="flex items-center gap-2 rounded-lg bg-error/10 p-3 text-sm text-error border border-error/20">
                        <AlertCircle size={16} />
                        <span>{error}</span>
                    </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2 md:col-span-2">
                        <label className="text-sm font-medium text-white/80">Nombre Completo</label>
                        <Input
                            name="nombre"
                            type="text"
                            placeholder="Juan Pérez"
                            icon={<User size={18} />}
                            value={formData.nombre}
                            onChange={handleChange}
                            className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:bg-white/10"
                            required
                        />
                    </div>

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-white/80">Nombre de Usuario</label>
                        <Input
                            name="username"
                            type="text"
                            placeholder="usuario123"
                            icon={<User size={18} />}
                            value={formData.username}
                            onChange={handleChange}
                            className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:bg-white/10"
                            required
                        />
                    </div>

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-white/80">Correo Electrónico</label>
                        <Input
                            name="email"
                            type="email"
                            placeholder="tu@email.com"
                            icon={<Mail size={18} />}
                            value={formData.email}
                            onChange={handleChange}
                            className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:bg-white/10"
                            required
                        />
                    </div>

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-white/80">Contraseña</label>
                        <Input
                            name="password"
                            type="password"
                            placeholder="••••••••"
                            icon={<Lock size={18} />}
                            value={formData.password}
                            onChange={handleChange}
                            className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:bg-white/10"
                            required
                        />
                    </div>

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-white/80">Confirmar Contraseña</label>
                        <Input
                            name="confirmPassword"
                            type="password"
                            placeholder="••••••••"
                            icon={<Lock size={18} />}
                            value={formData.confirmPassword}
                            onChange={handleChange}
                            className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:bg-white/10"
                            required
                        />
                    </div>
                </div>

                <Button
                    type="submit"
                    fullWidth
                    disabled={registerMutation.isPending}
                    className="mt-6"
                >
                    {registerMutation.isPending ? (
                        <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Creando cuenta...
                        </>
                    ) : (
                        <>
                            Registrarse <ArrowRight className="ml-2 h-4 w-4" />
                        </>
                    )}
                </Button>

                <div className="text-center text-sm text-white/50 mt-4">
                    ¿Ya tienes una cuenta?{' '}
                    <Link to="/login" search={{ redirect: undefined }} className="font-medium text-white hover:underline">
                        Iniciar Sesión
                    </Link>
                </div>
            </form>
        </div>
    );
}
