import { useState } from 'react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Camera, User, Lock, Info, Save, Key, CheckCircle, AlertCircle, Eye, EyeOff, Mail, Shield, Trash2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useMutation } from '@tanstack/react-query';
import { apiRequest } from '../lib/api';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { authService } from '../services/auth';

const changePasswordSchema = z
    .object({
        current_password: z.string().min(1, 'Ingresa tu contraseña actual'),
        new_password: z
            .string()
            .min(8, 'La contraseña debe tener al menos 8 caracteres')
            .regex(/[A-Z]/, 'Incluye al menos una mayúscula')
            .regex(/[0-9]/, 'Incluye al menos un número'),
        confirm_password: z.string().min(1, 'Confirma tu nueva contraseña'),
    })
    .refine((data) => data.new_password === data.confirm_password, {
        message: 'Las nuevas contraseñas no coinciden',
        path: ['confirm_password'],
    });

type ChangePasswordFormData = z.infer<typeof changePasswordSchema>;

export default function Profile() {
    const { user, verifySession, updateUser } = useAuth();
    const [nombreCompleto, setNombreCompleto] = useState(user?.nombre || '');
    const [email, setEmail] = useState(user?.email || ''); // Note: Email might not be in user object if not returned by login
    const [profileSuccess, setProfileSuccess] = useState<string | null>(null);
    const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
    const [passwordError, setPasswordError] = useState<string | null>(null);
    const [showCurrentPwd, setShowCurrentPwd] = useState(false);
    const [showNewPwd, setShowNewPwd] = useState(false);
    const [showConfirmPwd, setShowConfirmPwd] = useState(false);

    const {
        register,
        handleSubmit,
        watch,
        reset,
        formState: { errors, isValid },
    } = useForm<ChangePasswordFormData>({
        resolver: zodResolver(changePasswordSchema),
        mode: 'onChange',
        defaultValues: {
            current_password: '',
            new_password: '',
            confirm_password: '',
        },
    });

    const watchedNewPassword = watch('new_password') || '';
    const passwordChecks = [
        { label: 'Mínimo 8 caracteres', valid: watchedNewPassword.length >= 8 },
        { label: 'Al menos una mayúscula', valid: /[A-Z]/.test(watchedNewPassword) },
        { label: 'Al menos un número', valid: /[0-9]/.test(watchedNewPassword) },
    ];
    const passwordStrengthScore = passwordChecks.filter((item) => item.valid).length;
    const passwordStrengthText =
        passwordStrengthScore <= 1 ? 'Débil' : passwordStrengthScore === 2 ? 'Media' : 'Fuerte';
    const passwordStrengthColor =
        passwordStrengthScore <= 1
            ? 'bg-red-500'
            : passwordStrengthScore === 2
                ? 'bg-amber-500'
                : 'bg-emerald-500';

    // Mutation for uploading profile photo
    const uploadPhotoMutation = useMutation({
        mutationFn: async (base64Image: string) => {
            return await apiRequest('/api/v1/auth/upload-profile-photo', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: base64Image })
            });
        },
        onSuccess: () => {
            setProfileSuccess("Foto actualizada correctamente");
            // Refrescar el contexto de usuario desde el backend para obtener la nueva foto
            verifySession().finally(() => {
                setTimeout(() => setProfileSuccess(null), 3000);
            });
        },
        onError: (error: any) => {
            alert(error.message || 'Error al subir la foto');
        }
    });

    // Mutation for removing profile photo
    const removePhotoMutation = useMutation({
        mutationFn: async () => {
            return await apiRequest('/api/v1/auth/profile', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ remove_photo: true })
            });
        },
        onSuccess: () => {
            updateUser({ foto_url: '' });
            setProfileSuccess("Foto eliminada correctamente");
            setTimeout(() => setProfileSuccess(null), 3000);
            void verifySession();
        },
        onError: (error: any) => {
            alert(error.message || 'Error al eliminar la foto');
        }
    });

    // Mutation for updating profile
    const updateProfileMutation = useMutation({
        mutationFn: async (data: { nombre_completo: string, email: string }) => {
            return await apiRequest('/api/v1/auth/profile', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        },
        onSuccess: () => {
            setProfileSuccess('Perfil actualizado correctamente');
            authService.updateLocalUser({ nombre: nombreCompleto, email: email });
            setTimeout(() => setProfileSuccess(null), 3000);
        },
        onError: (error) => {
            console.error('Failed to update profile', error);
        }
    });

    // Mutation for changing password
    const changePasswordMutation = useMutation({
        mutationFn: async (data: { current_password: string; new_password: string }) => {
            return await apiRequest('/api/v1/auth/change-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        },
        onSuccess: () => {
            setPasswordSuccess('Contraseña actualizada correctamente');
            reset();
            setPasswordError(null);
            setTimeout(() => setPasswordSuccess(null), 3000);
        },
        onError: (error: any) => {
            setPasswordError(error.message || 'Error al cambiar la contraseña');
        }
    });

    const handleUpdateProfile = () => {
        updateProfileMutation.mutate({
            nombre_completo: nombreCompleto,
            email: email
        });
    };

    const handleChangePassword = handleSubmit((data) => {
        setPasswordError(null);
        changePasswordMutation.mutate({
            current_password: data.current_password,
            new_password: data.new_password,
        });
    });

    return (
        <div className="max-w-5xl mx-auto space-y-8 py-4">
            {/* ── Profile Hero Banner ── */}
            <div className="relative bg-white rounded-[32px] overflow-hidden shadow-sm border border-slate-200/60">
                {/* Subtle glow instead of hard banner */}
                <div className="absolute top-0 right-0 w-[500px] h-[500px] rounded-full blur-3xl -mr-32 -mt-32 opacity-30 pointer-events-none bg-blue-50" />
                <div className="h-32 bg-slate-50/50 border-b border-slate-100/60">
                    <div className="absolute inset-0 h-32 opacity-20"
                        style={{ backgroundImage: 'radial-gradient(circle at 20% 50%, rgba(59,130,246,0.3) 0%, transparent 50%), radial-gradient(circle at 80% 50%, rgba(220,38,38,0.2) 0%, transparent 50%)' }}
                    />
                </div>

                {/* Profile info overlay */}
                <div className="relative bg-transparent px-8 lg:px-10 pb-8 pt-0 z-10">
                    {/* Avatar — overlapping the banner */}
                    <div className="flex flex-col sm:flex-row items-center sm:items-end gap-6 -mt-16">
                        <div className="relative group shrink-0">
                            <div
                                className="cursor-pointer transition-transform duration-300 hover:scale-105"
                                onClick={() => document.getElementById('avatar-input')?.click()}
                            >
                                {user?.foto_url ? (
                                    <img
                                        src={user.foto_url}
                                        alt="Profile"
                                        className="h-32 w-32 rounded-[28px] object-cover border-4 border-white shadow-sm ring-1 ring-slate-200/60 bg-white"
                                    />
                                ) : (
                                    <div className="h-32 w-32 rounded-[28px] bg-red-50 text-red-500 flex items-center justify-center text-4xl font-bold border-4 border-white shadow-sm ring-1 ring-slate-200/60 bg-white">
                                        {user?.nombre?.substring(0, 2).toUpperCase() || 'US'}
                                    </div>
                                )}
                                <div className="absolute -bottom-2 -right-2 bg-white p-2.5 rounded-xl text-slate-500 border border-slate-200 shadow-sm hover:text-red-500 hover:border-red-200 transition-colors">
                                    <Camera size={18} />
                                </div>
                            </div>
                            <input
                                type="file"
                                id="avatar-input"
                                className="hidden"
                                accept="image/*"
                                onChange={(e) => {
                                    const file = e.target.files?.[0];
                                    if (file) {
                                        if (file.size > 5 * 1024 * 1024) {
                                            alert("La imagen no debe superar los 5MB");
                                            return;
                                        }
                                        const reader = new FileReader();
                                        reader.onload = (event) => {
                                            if (event.target?.result) {
                                                uploadPhotoMutation.mutate(event.target.result as string);
                                            }
                                        };
                                        reader.readAsDataURL(file);
                                    }
                                }}
                            />
                        </div>

                        {/* Name + meta */}
                        <div className="flex-1 text-center sm:text-left pb-2">
                            <h1 className="text-3xl font-bold text-slate-800 tracking-tight">{user?.nombre || 'Usuario'}</h1>
                            <div className="flex flex-wrap items-center justify-center sm:justify-start gap-4 mt-2 text-[14px] font-medium text-slate-500">
                                <span className="flex items-center gap-1.5"><User size={15} className="text-slate-400" /> @{user?.username || '—'}</span>
                                {user?.email && <span className="flex items-center gap-1.5"><Mail size={15} className="text-slate-400" /> {user.email}</span>}
                                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[12px] font-bold bg-slate-50 border border-slate-200/60 text-slate-600 uppercase tracking-widest shadow-sm">
                                    <Shield size={13} className="text-slate-400" /> {user?.tipo || 'socio'}
                                </span>
                            </div>
                        </div>

                        {/* Photo actions */}
                        <div className="flex items-center gap-3 pb-2 flex-wrap justify-center sm:justify-start">
                            <Button
                                variant="outline"
                                className="rounded-full font-bold text-[13px] border-slate-200/80 text-slate-600 hover:bg-slate-50/80 shadow-sm"
                                onClick={() => document.getElementById('avatar-input')?.click()}
                            >
                                <Camera size={16} className="mr-2" /> Cambiar foto
                            </Button>
                            {user?.foto_url && (
                                <Button
                                    variant="ghost"
                                    className="rounded-full font-bold text-[13px] text-red-500 hover:text-red-600 hover:bg-red-50 border border-transparent hover:border-red-100"
                                    onClick={() => {
                                        if (window.confirm('¿Seguro que deseas eliminar tu foto de perfil?')) {
                                            removePhotoMutation.mutate();
                                        }
                                    }}
                                    disabled={removePhotoMutation.isPending}
                                >
                                    <Trash2 size={16} className="mr-1.5" />
                                    {removePhotoMutation.isPending ? '...' : 'Eliminar foto'}
                                </Button>
                            )}
                        </div>
                    </div>

                    {/* Upload feedback */}
                    {uploadPhotoMutation.isPending && (
                        <div className="mt-3 flex items-center gap-2 text-sm text-gray-500 animate-pulse">
                            <div className="h-3 w-3 rounded-full border-2 border-gray-400 border-t-transparent animate-spin" />
                            Subiendo foto…
                        </div>
                    )}
                    {profileSuccess && (
                        <div className="mt-3 flex items-center gap-2 text-green-600 text-sm">
                            <CheckCircle size={16} /> {profileSuccess}
                        </div>
                    )}
                </div>
            </div>

            {/* ── Two-column form area ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Personal Information */}
                <Card className="border border-slate-200/60 shadow-sm rounded-[32px] overflow-hidden h-full bg-white">
                    <CardContent className="p-8 lg:p-10 h-full flex flex-col">
                        <h2 className="text-xl font-bold text-slate-800 flex items-center gap-3 mb-8 tracking-tight">
                            <div className="w-10 h-10 rounded-[12px] bg-slate-50 border border-slate-200/60 flex items-center justify-center shadow-sm"><User size={20} className="text-slate-500" /></div>
                            Información Personal
                        </h2>

                        <div className="flex h-full flex-col gap-6">
                            <div className="space-y-2">
                                <label className="text-[12px] font-bold text-slate-400 uppercase tracking-widest pl-1">Nombre de usuario</label>
                                <div className="relative">
                                    <Input
                                        value={user?.username || ''}
                                        disabled
                                        className="bg-slate-50/50 border-slate-200/60 text-slate-400 pr-10 rounded-full py-6 text-[15px] font-medium opacity-70 cursor-not-allowed"
                                    />
                                    <div className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-300">
                                        <Info size={18} />
                                    </div>
                                </div>
                                <div className="pl-1 min-h-[20px]">
                                    <p className="text-[12px] font-medium text-slate-400">Este valor no se puede cambiar</p>
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-[12px] font-bold text-slate-500 uppercase tracking-widest pl-1">Nombre completo</label>
                                <Input
                                    value={nombreCompleto}
                                    onChange={(e) => setNombreCompleto(e.target.value)}
                                    className="bg-slate-50/50 border-slate-200/60 focus:border-blue-400 focus:ring-4 focus:ring-blue-500/10 rounded-full py-6 text-[15px] font-medium text-slate-800 transition-all shadow-sm"
                                />
                            </div>

                            <div className="space-y-2">
                                <label className="text-[12px] font-bold text-slate-500 uppercase tracking-widest pl-1">Correo electrónico</label>
                                <Input
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    className="bg-slate-50/50 border-slate-200/60 focus:border-blue-400 focus:ring-4 focus:ring-blue-500/10 rounded-full py-6 text-[15px] font-medium text-slate-800 transition-all shadow-sm"
                                />
                            </div>

                            <div className="mt-8">
                                <Button
                                    className="w-full bg-red-500 hover:bg-red-600 text-white rounded-full py-6 text-[15px] font-bold shadow-md transition-colors disabled:opacity-50"
                                    onClick={handleUpdateProfile}
                                    disabled={updateProfileMutation.isPending}
                                >
                                    <Save size={18} className="mr-2" />
                                    {updateProfileMutation.isPending ? 'Guardando cambios...' : 'Guardar Información'}
                                </Button>
                                <div className="min-h-[24px] mt-4 flex justify-center">
                                    {profileSuccess && (
                                        <div className="flex items-center gap-2 text-emerald-600 text-[14px] font-bold animate-in fade-in">
                                            <CheckCircle size={16} /> {profileSuccess}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Change Password */}
                <Card className="border border-slate-200/60 shadow-sm rounded-[32px] overflow-hidden h-full bg-white">
                    <CardContent className="p-8 lg:p-10 h-full flex flex-col">
                        <h2 className="text-xl font-bold text-slate-800 flex items-center gap-3 mb-8 tracking-tight">
                            <div className="w-10 h-10 rounded-[12px] bg-red-50 border border-red-100/60 flex items-center justify-center shadow-sm"><Lock size={20} className="text-red-500" /></div>
                            Cambiar Contraseña
                        </h2>

                        <div className="flex h-full flex-col gap-6">
                            <div className="space-y-2">
                                <label className="text-[12px] font-bold text-slate-500 uppercase tracking-widest pl-1">Contraseña actual</label>
                                <div className="relative">
                                    <Input
                                        type={showCurrentPwd ? 'text' : 'password'}
                                        {...register('current_password')}
                                        placeholder="••••••••"
                                        className="bg-slate-50/50 border-slate-200/60 focus:border-red-400 focus:ring-4 focus:ring-red-500/10 rounded-full py-6 pr-12 text-[15px] font-medium text-slate-800 transition-all shadow-sm"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowCurrentPwd(v => !v)}
                                        className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
                                    >
                                        {showCurrentPwd ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                                <div className="pl-1 min-h-[20px]">
                                    {errors.current_password && (
                                        <p className="text-[12px] font-medium text-red-500">{errors.current_password.message}</p>
                                    )}
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-[12px] font-bold text-slate-500 uppercase tracking-widest pl-1">Nueva contraseña</label>
                                <div className="relative">
                                    <Input
                                        type={showNewPwd ? 'text' : 'password'}
                                        {...register('new_password')}
                                        placeholder="Mínimo 8 caracteres"
                                        className="bg-slate-50/50 border-slate-200/60 focus:border-red-400 focus:ring-4 focus:ring-red-500/10 rounded-full py-6 pr-12 text-[15px] font-medium text-slate-800 transition-all shadow-sm"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowNewPwd(v => !v)}
                                        className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
                                    >
                                        {showNewPwd ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                                <div className="pl-1 min-h-[14px]">
                                    {errors.new_password && (
                                        <p className="text-[12px] font-medium text-red-500">{errors.new_password.message}</p>
                                    )}
                                </div>
                                
                                <div className="rounded-[20px] border border-slate-100 bg-slate-50/50 p-4 space-y-3 mt-1 shadow-sm">
                                    <div className="flex items-center justify-between text-[11px] uppercase tracking-widest font-bold text-slate-400">
                                        <span>Fortaleza</span>
                                        <span className={`font-bold ${
                                            passwordStrengthScore <= 1 ? 'text-red-500' : 
                                            passwordStrengthScore === 2 ? 'text-amber-500' : 'text-emerald-500'
                                        }`}>{passwordStrengthText}</span>
                                    </div>
                                    <div className="h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
                                        <div
                                            className={`h-full transition-all duration-300 ${passwordStrengthColor}`}
                                            style={{ width: `${(passwordStrengthScore / 3) * 100}%` }}
                                        />
                                    </div>
                                    <ul className="space-y-1.5 pt-1">
                                        {passwordChecks.map((check) => (
                                            <li key={check.label} className={`text-[12px] font-medium flex items-center gap-2 ${check.valid ? 'text-emerald-600' : 'text-slate-400'}`}>
                                                <CheckCircle size={14} className={check.valid ? 'text-emerald-500' : 'text-slate-300'} />
                                                <span>{check.label}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-[12px] font-bold text-slate-500 uppercase tracking-widest pl-1">Confirmar nueva contraseña</label>
                                <div className="relative">
                                    <Input
                                        type={showConfirmPwd ? 'text' : 'password'}
                                        {...register('confirm_password')}
                                        placeholder="Repite la contraseña"
                                        className="bg-slate-50/50 border-slate-200/60 focus:border-red-400 focus:ring-4 focus:ring-red-500/10 rounded-full py-6 pr-12 text-[15px] font-medium text-slate-800 transition-all shadow-sm"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowConfirmPwd(v => !v)}
                                        className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
                                    >
                                        {showConfirmPwd ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                                <div className="pl-1 min-h-[20px]">
                                    {errors.confirm_password && (
                                        <p className="text-[12px] font-medium text-red-500">{errors.confirm_password.message}</p>
                                    )}
                                </div>
                            </div>

                            <div className="mt-8">
                                <Button
                                    variant="outline"
                                    className="w-full bg-white border-slate-200/80 text-slate-600 hover:bg-slate-50 hover:text-slate-900 rounded-full py-6 text-[15px] font-bold shadow-sm transition-colors disabled:opacity-50"
                                    onClick={handleChangePassword}
                                    disabled={changePasswordMutation.isPending || !isValid}
                                >
                                    <Key size={18} className="mr-2 text-slate-400" />
                                    {changePasswordMutation.isPending ? 'Cambiando contraseña...' : 'Cambiar Contraseña'}
                                </Button>
                                <div className="min-h-[24px] mt-4 flex justify-center flex-col items-center gap-1">
                                    {passwordSuccess && (
                                        <div className="flex items-center gap-2 text-emerald-600 text-[14px] font-bold animate-in fade-in">
                                            <CheckCircle size={16} /> {passwordSuccess}
                                        </div>
                                    )}
                                    {passwordError && (
                                        <div className="flex items-center gap-2 text-rose-600 text-[14px] font-bold animate-in fade-in">
                                            <AlertCircle size={16} /> {passwordError}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>


        </div>
    );
}
