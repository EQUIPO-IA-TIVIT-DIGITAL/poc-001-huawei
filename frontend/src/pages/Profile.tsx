import { useState } from 'react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Avatar, AvatarFallback, AvatarImage } from '../components/ui/avatar';
import { ConfirmDialog } from '../components/ConfirmDialog';
import {
    Camera, User, Lock, Save, Key, CheckCircle, AlertCircle,
    Eye, EyeOff, Mail, Shield, Trash2,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useMutation } from '@tanstack/react-query';
import { apiRequest } from '../lib/api';
import { getErrorMessage } from '../lib/errors';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { authService } from '../services/auth';
import { toast } from 'sonner';
import { useTranslation } from '../i18n';
import { cn } from '../lib/utils';

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
    const { t } = useTranslation();
    const { user, verifySession, updateUser } = useAuth();
    const [nombreCompleto, setNombreCompleto] = useState(user?.nombre || '');
    const [email, setEmail] = useState(user?.email || '');
    const [profileSuccess, setProfileSuccess] = useState<string | null>(null);
    const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
    const [passwordError, setPasswordError] = useState<string | null>(null);
    const [showCurrentPwd, setShowCurrentPwd] = useState(false);
    const [showNewPwd, setShowNewPwd] = useState(false);
    const [showConfirmPwd, setShowConfirmPwd] = useState(false);
    const [showRemovePhoto, setShowRemovePhoto] = useState(false);

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
        { labelKey: 'profile.passwordMinLength', valid: watchedNewPassword.length >= 8 },
        { labelKey: 'profile.passwordUppercase', valid: /[A-Z]/.test(watchedNewPassword) },
        { labelKey: 'profile.passwordNumber', valid: /[0-9]/.test(watchedNewPassword) },
    ] as const;
    const passwordStrengthScore = passwordChecks.filter((item) => item.valid).length;
    const passwordStrengthTextKey =
        passwordStrengthScore <= 1
            ? 'profile.strengthWeak'
            : passwordStrengthScore === 2
                ? 'profile.strengthMedium'
                : 'profile.strengthStrong';
    const passwordStrengthColor =
        passwordStrengthScore <= 1
            ? 'bg-error'
            : passwordStrengthScore === 2
                ? 'bg-warning'
                : 'bg-success';
    const passwordStrengthTextColor =
        passwordStrengthScore <= 1
            ? 'text-error'
            : passwordStrengthScore === 2
                ? 'text-warning'
                : 'text-success';

    const uploadPhotoMutation = useMutation({
        mutationFn: async (base64Image: string) => {
            return await apiRequest('/api/v1/auth/upload-profile-photo', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: base64Image }),
            });
        },
        onSuccess: () => {
            setProfileSuccess(t('profile.photoUpdated'));
            void verifySession().finally(() => {
                setTimeout(() => setProfileSuccess(null), 3000);
            });
        },
        onError: (error: unknown) => {
            toast.error(getErrorMessage(error) || t('profile.photoUpdateError'));
        },
    });

    const removePhotoMutation = useMutation({
        mutationFn: async () => {
            return await apiRequest('/api/v1/auth/profile', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ remove_photo: true }),
            });
        },
        onSuccess: () => {
            updateUser({ foto_url: '' });
            setProfileSuccess(t('profile.photoRemoved'));
            setTimeout(() => setProfileSuccess(null), 3000);
            void verifySession();
        },
        onError: (error: unknown) => {
            toast.error(getErrorMessage(error) || t('profile.photoRemoveError'));
        },
    });

    const updateProfileMutation = useMutation({
        mutationFn: async (data: { nombre_completo: string; email: string }) => {
            return await apiRequest('/api/v1/auth/profile', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
        },
        onSuccess: () => {
            setProfileSuccess(t('profile.profileUpdated'));
            authService.updateLocalUser({ nombre: nombreCompleto, email });
            setTimeout(() => setProfileSuccess(null), 3000);
        },
        onError: (error: unknown) => {
            toast.error(getErrorMessage(error) || t('profile.profileUpdateError'));
        },
    });

    const changePasswordMutation = useMutation({
        mutationFn: async (data: { current_password: string; new_password: string }) => {
            return await apiRequest('/api/v1/auth/change-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
        },
        onSuccess: () => {
            setPasswordSuccess(t('profile.passwordUpdated'));
            reset();
            setPasswordError(null);
            setTimeout(() => setPasswordSuccess(null), 3000);
        },
        onError: (error: unknown) => {
            setPasswordError(getErrorMessage(error) || t('profile.passwordUpdateError'));
        },
    });

    const handleUpdateProfile = () => {
        updateProfileMutation.mutate({
            nombre_completo: nombreCompleto,
            email,
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
        <div className="mx-auto max-w-5xl space-y-8 py-4">
            <div className="relative overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
                <div className="pointer-events-none absolute -mr-32 -mt-32 right-0 top-0 h-[500px] w-[500px] rounded-full bg-brand-soft opacity-60 blur-3xl" />
                <div className="h-32 border-b border-border bg-muted/40" />

                <div className="relative z-10 px-8 pb-8 pt-0 lg:px-10">
                    <div className="-mt-16 flex flex-col items-center gap-6 sm:flex-row sm:items-end">
                        <div className="group relative shrink-0">
                            <button
                                type="button"
                                className="cursor-pointer transition-transform duration-300 hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                                onClick={() => document.getElementById('avatar-input')?.click()}
                                aria-label={t('profile.changePhoto')}
                            >
                                <Avatar className="h-32 w-32 rounded-2xl border-4 border-card">
                                    {user?.foto_url ? (
                                        <AvatarImage src={user.foto_url} alt={t('profile.profilePhotoAlt')} />
                                    ) : null}
                                    <AvatarFallback className="rounded-2xl bg-brand-soft text-4xl font-bold text-primary">
                                        {user?.nombre?.substring(0, 2).toUpperCase() || 'US'}
                                    </AvatarFallback>
                                </Avatar>
                                <div className="absolute -bottom-2 -right-2 rounded-xl border border-border bg-card p-2.5 text-muted-foreground shadow-sm transition-colors group-hover:border-brand-border group-hover:text-primary">
                                    <Camera size={18} aria-hidden="true" />
                                </div>
                            </button>
                            <input
                                type="file"
                                id="avatar-input"
                                className="hidden"
                                accept="image/*"
                                onChange={(e) => {
                                    const file = e.target.files?.[0];
                                    if (file) {
                                        if (file.size > 5 * 1024 * 1024) {
                                            toast.error(t('profile.photoTooLarge'));
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

                        <div className="flex-1 pb-2 text-center sm:text-left">
                            <h1 className="text-3xl font-bold tracking-tight text-foreground">
                                {user?.nombre || t('profile.userFallback')}
                            </h1>
                            <div className="mt-2 flex flex-wrap items-center justify-center gap-4 text-[14px] font-medium text-muted-foreground sm:justify-start">
                                <span className="flex items-center gap-1.5">
                                    <User size={15} className="text-muted-foreground" aria-hidden="true" /> @
                                    {user?.username || '—'}
                                </span>
                                {user?.email && (
                                    <span className="flex items-center gap-1.5">
                                        <Mail size={15} className="text-muted-foreground" aria-hidden="true" />
                                        {user.email}
                                    </span>
                                )}
                                <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted px-3 py-1 text-[12px] font-bold uppercase tracking-widest text-muted-foreground shadow-sm">
                                    <Shield size={13} className="text-muted-foreground" aria-hidden="true" />
                                    {user?.tipo || 'socio'}
                                </span>
                            </div>
                        </div>

                        <div className="flex flex-wrap items-center justify-center gap-3 pb-2 sm:justify-start">
                            <Button
                                variant="outline"
                                className="rounded-full"
                                onClick={() => document.getElementById('avatar-input')?.click()}
                            >
                                <Camera aria-hidden="true" /> {t('profile.changePhoto')}
                            </Button>
                            {user?.foto_url && (
                                <Button
                                    variant="ghost"
                                    className="rounded-full text-error hover:bg-error-surface hover:text-error"
                                    onClick={() => setShowRemovePhoto(true)}
                                    disabled={removePhotoMutation.isPending}
                                >
                                    <Trash2 aria-hidden="true" />
                                    {removePhotoMutation.isPending ? t('common.deleting') : t('profile.deletePhoto')}
                                </Button>
                            )}
                        </div>
                    </div>

                    {uploadPhotoMutation.isPending && (
                        <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground animate-pulse" aria-live="polite">
                            <div className="h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
                            {t('profile.uploadingPhoto')}
                        </div>
                    )}
                    {profileSuccess && (
                        <div className="mt-3 flex items-center gap-2 text-sm text-success" aria-live="polite">
                            <CheckCircle size={16} aria-hidden="true" /> {profileSuccess}
                        </div>
                    )}
                </div>
            </div>

            <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
                <Card className="h-full overflow-hidden shadow-sm">
                    <CardContent className="flex h-full flex-col p-8 lg:p-10">
                        <h2 className="mb-8 flex items-center gap-3 text-xl font-bold tracking-tight text-foreground">
                            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-muted shadow-sm">
                                <User size={20} className="text-muted-foreground" aria-hidden="true" />
                            </div>
                            {t('profile.personalInfo')}
                        </h2>

                        <div className="flex h-full flex-col gap-6">
                            <div className="space-y-2">
                                <Label htmlFor="profile-username" className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                                    {t('profile.username')}
                                </Label>
                                <Input
                                    id="profile-username"
                                    value={user?.username || ''}
                                    disabled
                                    className="cursor-not-allowed opacity-70"
                                />
                                <p className="min-h-[20px] text-xs font-medium text-muted-foreground">
                                    {t('profile.usernameHint')}
                                </p>
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="profile-fullname" className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                                    {t('profile.fullName')}
                                </Label>
                                <Input
                                    id="profile-fullname"
                                    value={nombreCompleto}
                                    onChange={(e) => setNombreCompleto(e.target.value)}
                                />
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="profile-email" className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                                    {t('profile.email')}
                                </Label>
                                <Input
                                    id="profile-email"
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                />
                            </div>

                            <div className="mt-8">
                                <Button
                                    className="w-full"
                                    onClick={handleUpdateProfile}
                                    disabled={updateProfileMutation.isPending}
                                    loading={updateProfileMutation.isPending}
                                >
                                    <Save aria-hidden="true" />
                                    {updateProfileMutation.isPending ? t('profile.savingChanges') : t('profile.saveInfo')}
                                </Button>
                                <div className="mt-4 flex min-h-[24px] justify-center">
                                    {profileSuccess && (
                                        <div className="flex items-center gap-2 text-[14px] font-bold text-success">
                                            <CheckCircle size={16} aria-hidden="true" /> {profileSuccess}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card className="h-full overflow-hidden shadow-sm">
                    <CardContent className="flex h-full flex-col p-8 lg:p-10">
                        <h2 className="mb-8 flex items-center gap-3 text-xl font-bold tracking-tight text-foreground">
                            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-brand-border bg-brand-soft shadow-sm">
                                <Lock size={20} className="text-primary" aria-hidden="true" />
                            </div>
                            {t('profile.changePassword')}
                        </h2>

                        <div className="flex h-full flex-col gap-6">
                            <div className="space-y-2">
                                <Label htmlFor="current-password" className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                                    {t('profile.currentPassword')}
                                </Label>
                                <div className="relative">
                                    <Input
                                        id="current-password"
                                        type={showCurrentPwd ? 'text' : 'password'}
                                        {...register('current_password')}
                                        placeholder={t('profile.currentPasswordPlaceholder')}
                                        invalid={!!errors.current_password}
                                        className="pr-12"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowCurrentPwd((v) => !v)}
                                        aria-label={showCurrentPwd ? t('profile.hidePassword') : t('profile.showPassword')}
                                        className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                                    >
                                        {showCurrentPwd ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
                                    </button>
                                </div>
                                <div className="min-h-[20px]">
                                    {errors.current_password && (
                                        <p className="text-xs font-medium text-error">{errors.current_password.message}</p>
                                    )}
                                </div>
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="new-password" className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                                    {t('profile.newPassword')}
                                </Label>
                                <div className="relative">
                                    <Input
                                        id="new-password"
                                        type={showNewPwd ? 'text' : 'password'}
                                        {...register('new_password')}
                                        placeholder={t('profile.newPasswordPlaceholder')}
                                        invalid={!!errors.new_password}
                                        className="pr-12"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowNewPwd((v) => !v)}
                                        aria-label={showNewPwd ? t('profile.hidePassword') : t('profile.showPassword')}
                                        className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                                    >
                                        {showNewPwd ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
                                    </button>
                                </div>
                                <div className="min-h-[14px]">
                                    {errors.new_password && (
                                        <p className="text-xs font-medium text-error">{errors.new_password.message}</p>
                                    )}
                                </div>

                                <div className="mt-1 space-y-3 rounded-2xl border border-border bg-muted/40 p-4 shadow-sm">
                                    <div className="flex items-center justify-between text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                                        <span>{t('profile.strength')}</span>
                                        <span className={cn('font-bold', passwordStrengthTextColor)}>
                                            {t(passwordStrengthTextKey)}
                                        </span>
                                    </div>
                                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                                        <div
                                            className={cn('h-full transition-all duration-300', passwordStrengthColor)}
                                            style={{ width: `${(passwordStrengthScore / 3) * 100}%` }}
                                        />
                                    </div>
                                    <ul className="space-y-1.5 pt-1">
                                        {passwordChecks.map((check) => (
                                            <li
                                                key={check.labelKey}
                                                className={cn(
                                                    'flex items-center gap-2 text-[12px] font-medium',
                                                    check.valid ? 'text-success' : 'text-muted-foreground',
                                                )}
                                            >
                                                <CheckCircle
                                                    size={14}
                                                    className={check.valid ? 'text-success' : 'text-muted-foreground/50'}
                                                    aria-hidden="true"
                                                />
                                                <span>{t(check.labelKey)}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="confirm-password" className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                                    {t('profile.confirmPassword')}
                                </Label>
                                <div className="relative">
                                    <Input
                                        id="confirm-password"
                                        type={showConfirmPwd ? 'text' : 'password'}
                                        {...register('confirm_password')}
                                        placeholder={t('profile.confirmPasswordPlaceholder')}
                                        invalid={!!errors.confirm_password}
                                        className="pr-12"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowConfirmPwd((v) => !v)}
                                        aria-label={showConfirmPwd ? t('profile.hidePassword') : t('profile.showPassword')}
                                        className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                                    >
                                        {showConfirmPwd ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
                                    </button>
                                </div>
                                <div className="min-h-[20px]">
                                    {errors.confirm_password && (
                                        <p className="text-xs font-medium text-error">{errors.confirm_password.message}</p>
                                    )}
                                </div>
                            </div>

                            <div className="mt-8">
                                <Button
                                    variant="outline"
                                    className="w-full"
                                    onClick={handleChangePassword}
                                    disabled={changePasswordMutation.isPending || !isValid}
                                    loading={changePasswordMutation.isPending}
                                >
                                    <Key aria-hidden="true" />
                                    {changePasswordMutation.isPending ? t('profile.changingPassword') : t('profile.changePassword')}
                                </Button>
                                <div className="mt-4 flex min-h-[24px] flex-col items-center justify-center gap-1">
                                    {passwordSuccess && (
                                        <div className="flex items-center gap-2 text-[14px] font-bold text-success" aria-live="polite">
                                            <CheckCircle size={16} aria-hidden="true" /> {passwordSuccess}
                                        </div>
                                    )}
                                    {passwordError && (
                                        <div className="flex items-center gap-2 text-[14px] font-bold text-error" aria-live="polite">
                                            <AlertCircle size={16} aria-hidden="true" /> {passwordError}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            <ConfirmDialog
                open={showRemovePhoto}
                onOpenChange={setShowRemovePhoto}
                onConfirm={() => {
                    removePhotoMutation.mutate();
                    setShowRemovePhoto(false);
                }}
                title={t('profile.photoRemoveTitle')}
                description={t('profile.photoRemoveDescription')}
                confirmText={t('profile.deletePhoto')}
                loading={removePhotoMutation.isPending}
            />
        </div>
    );
}
