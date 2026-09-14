import { useEffect, useRef, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
    FolderOpen,
    Sparkles,
    ChevronRight,
    CheckCircle2,
    AlertCircle,
    ArrowRight,
    SkipForward,
    Shield,
    GraduationCap,
    CalendarDays,
    Factory,
    Clapperboard,
    Stethoscope,
    Trophy,
    Lock,
    Scale,
    Target,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { FormProvider, useForm, useFormContext } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { workspaceService, type CreateWorkspaceRequest, type Workspace } from '../services/workspace';
import { apiRequest } from '../lib/api';
import { getErrorMessage } from '../lib/errors';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';
import { Spinner } from './ui/spinner';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from './ui/dialog';
import { ConfirmDialog } from './ConfirmDialog';
import { cn } from '../lib/utils';
import { useTranslation } from '../i18n';
import type { TranslationKey } from '../i18n/es';

interface CreateWorkspaceModalProps {
    open: boolean;
    onClose: () => void;
    onCreated?: (workspace: unknown) => void;
}

const DEFAULT_WORKSPACE_COLOR = '#e30613';
const WORKSPACE_DRAFT_KEY = 'cu002-create-workspace-draft-v1';

interface CategoryOption {
    value: string;
    labelKey: TranslationKey;
    descriptionKey: TranslationKey;
    icon: LucideIcon;
}

const CATEGORIAS: CategoryOption[] = [
    { value: 'deportes', labelKey: 'createWorkspace.catSports', descriptionKey: 'createWorkspace.catSportsDesc', icon: Trophy },
    { value: 'seguridad', labelKey: 'createWorkspace.catSecurity', descriptionKey: 'createWorkspace.catSecurityDesc', icon: Shield },
    { value: 'educacion', labelKey: 'createWorkspace.catEducation', descriptionKey: 'createWorkspace.catEducationDesc', icon: GraduationCap },
    { value: 'eventos', labelKey: 'createWorkspace.catEvents', descriptionKey: 'createWorkspace.catEventsDesc', icon: CalendarDays },
    { value: 'industrial', labelKey: 'createWorkspace.catIndustrial', descriptionKey: 'createWorkspace.catIndustrialDesc', icon: Factory },
    { value: 'entretenimiento', labelKey: 'createWorkspace.catEntertainment', descriptionKey: 'createWorkspace.catEntertainmentDesc', icon: Clapperboard },
    { value: 'salud', labelKey: 'createWorkspace.catHealth', descriptionKey: 'createWorkspace.catHealthDesc', icon: Stethoscope },
    { value: 'general', labelKey: 'createWorkspace.catGeneral', descriptionKey: 'createWorkspace.catGeneralDesc', icon: FolderOpen },
];

interface ToleranceOption {
    value: string;
    labelKey: TranslationKey;
    descriptionKey: TranslationKey;
    icon: LucideIcon;
}

const NIVELES_TOLERANCIA: ToleranceOption[] = [
    {
        value: 'bajo',
        labelKey: 'createWorkspace.levelStrict',
        descriptionKey: 'createWorkspace.levelStrictDesc',
        icon: Lock,
    },
    {
        value: 'medio',
        labelKey: 'createWorkspace.levelBalanced',
        descriptionKey: 'createWorkspace.levelBalancedDesc',
        icon: Scale,
    },
    {
        value: 'alto',
        labelKey: 'createWorkspace.levelTolerant',
        descriptionKey: 'createWorkspace.levelTolerantDesc',
        icon: Target,
    },
];

const STEP_KEYS: TranslationKey[] = [
    'createWorkspace.stepProject',
    'createWorkspace.stepAiConfig',
    'createWorkspace.stepConfirm',
];

const CreateWorkspaceSchema = z.object({
    nombre: z
        .string()
        .min(3, 'El nombre debe tener al menos 3 caracteres')
        .max(50, 'El nombre no puede exceder 50 caracteres'),
    descripcion: z.string().max(200, 'La descripción no puede exceder 200 caracteres'),
    contexto: z
        .string()
        .min(1, 'El contexto es obligatorio para que la IA pueda analizar correctamente los videos')
        .max(1000, 'El contexto no puede exceder 1000 caracteres'),
    categoria: z.string(),
    nivel_tolerancia: z.string(),
});

type CreateWorkspaceFormValues = z.infer<typeof CreateWorkspaceSchema>;

const DEFAULT_FORM_VALUES: CreateWorkspaceFormValues = {
    nombre: '',
    descripcion: '',
    contexto: '',
    categoria: 'general',
    nivel_tolerancia: 'medio',
};

function ProjectStep() {
    const { t } = useTranslation();
    const {
        register,
        watch,
        setValue,
        formState: { errors },
    } = useFormContext<CreateWorkspaceFormValues>();

    const nombre = watch('nombre');
    const descripcion = watch('descripcion');
    const categoria = watch('categoria');

    return (
        <div className="space-y-5">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="space-y-1.5">
                    <label htmlFor="workspace-nombre" className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        {t('createWorkspace.nameLabel')} <span className="text-error">*</span>
                    </label>
                    <Input
                        id="workspace-nombre"
                        type="text"
                        invalid={!!errors.nombre}
                        {...register('nombre')}
                        onChange={(e) => setValue('nombre', e.target.value.slice(0, 50), { shouldDirty: true, shouldValidate: true })}
                        placeholder={t('createWorkspace.namePlaceholder')}
                        autoFocus
                    />
                    <div className="flex min-h-[20px] items-center justify-between">
                        <p className="text-xs text-error">{errors.nombre?.message || ''}</p>
                        <div className="text-right text-xs text-muted-foreground">{nombre.length}/50</div>
                    </div>
                </div>

                <div className="space-y-1.5">
                    <label htmlFor="workspace-descripcion" className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        {t('createWorkspace.descriptionLabel')}
                    </label>
                    <Input
                        id="workspace-descripcion"
                        type="text"
                        invalid={!!errors.descripcion}
                        {...register('descripcion')}
                        onChange={(e) => setValue('descripcion', e.target.value.slice(0, 200), { shouldDirty: true, shouldValidate: true })}
                        placeholder={t('createWorkspace.descriptionPlaceholder')}
                    />
                    <div className="flex min-h-[20px] items-center justify-between">
                        <p className="text-xs text-error">{errors.descripcion?.message || ''}</p>
                        <div className="text-right text-xs text-muted-foreground">{descripcion.length}/200</div>
                    </div>
                </div>
            </div>

            <div className="space-y-2">
                <span className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {t('createWorkspace.categoryLabel')}
                </span>
                <div
                    role="radiogroup"
                    aria-label={t('createWorkspace.categoryAria')}
                    className="grid grid-cols-4 gap-2 md:grid-cols-8"
                >
                    {CATEGORIAS.map((cat) => {
                        const Icon = cat.icon;
                        const selected = categoria === cat.value;
                        return (
                            <button
                                key={cat.value}
                                type="button"
                                role="radio"
                                aria-checked={selected}
                                title={t(cat.descriptionKey)}
                                onClick={() => setValue('categoria', cat.value, { shouldDirty: true })}
                                className={cn(
                                    'group flex flex-col items-center gap-1.5 rounded-xl border p-3 transition-all duration-200',
                                    selected
                                        ? 'border-brand-border bg-brand-soft shadow-sm ring-1 ring-brand-border'
                                        : 'border-border bg-card hover:-translate-y-px hover:border-brand-border hover:shadow-sm',
                                )}
                            >
                                <Icon
                                    size={20}
                                    aria-hidden="true"
                                    className={cn(
                                        'transition-transform duration-200',
                                        selected
                                            ? 'scale-110 text-primary'
                                            : 'text-muted-foreground group-hover:scale-110 group-hover:text-primary',
                                    )}
                                />
                                <span
                                    className={cn(
                                        'text-center text-[10px] font-semibold leading-tight transition-colors duration-200',
                                        selected ? 'text-brand-hover' : 'text-muted-foreground group-hover:text-primary',
                                    )}
                                >
                                    {t(cat.labelKey)}
                                </span>
                            </button>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

function AIConfigStep() {
    const { t } = useTranslation();
    const {
        register,
        watch,
        setValue,
        formState: { errors },
    } = useFormContext<CreateWorkspaceFormValues>();

    const nivelTolerancia = watch('nivel_tolerancia');
    const contexto = watch('contexto');

    return (
        <div className="space-y-5">
            <div className="space-y-2">
                <span className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {t('createWorkspace.aiLevelLabel')}
                </span>
                <div role="radiogroup" aria-label={t('createWorkspace.aiLevelAria')} className="grid grid-cols-3 gap-3">
                    {NIVELES_TOLERANCIA.map((nivel) => {
                        const Icon = nivel.icon;
                        const selected = nivelTolerancia === nivel.value;
                        return (
                            <button
                                key={nivel.value}
                                type="button"
                                role="radio"
                                aria-checked={selected}
                                onClick={() => setValue('nivel_tolerancia', nivel.value, { shouldDirty: true })}
                                className={cn(
                                    'rounded-xl border p-3.5 text-left transition-all duration-200 hover:-translate-y-0.5',
                                    selected
                                        ? 'border-brand-border bg-brand-soft shadow-sm ring-1 ring-brand-border'
                                        : 'border-border bg-card hover:border-brand-border hover:shadow-sm',
                                )}
                            >
                                <div className="mb-1 flex items-center gap-2">
                                    <span
                                        className={cn(
                                            'flex h-7 w-7 items-center justify-center rounded-md transition-transform duration-200',
                                            selected ? 'scale-110 bg-brand-soft' : 'bg-muted',
                                        )}
                                    >
                                        <Icon
                                            size={16}
                                            aria-hidden="true"
                                            className={selected ? 'text-primary' : 'text-muted-foreground'}
                                        />
                                    </span>
                                    <span className={cn('text-sm font-bold', selected ? 'text-brand-hover' : 'text-foreground')}>
                                        {t(nivel.labelKey)}
                                    </span>
                                </div>
                                <p className={cn('text-[11px] leading-snug', selected ? 'text-muted-foreground' : 'text-muted-foreground')}>
                                    {t(nivel.descriptionKey)}
                                </p>
                            </button>
                        );
                    })}
                </div>
            </div>

            <div className="space-y-1.5">
                <label htmlFor="workspace-contexto" className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {t('createWorkspace.contextLabel')} <span className="text-error">*</span>
                </label>
                <Textarea
                    id="workspace-contexto"
                    invalid={!!errors.contexto}
                    {...register('contexto')}
                    onChange={(e) => setValue('contexto', e.target.value.slice(0, 1000), { shouldDirty: true, shouldValidate: true })}
                    placeholder={t('createWorkspace.contextPlaceholder')}
                    className="h-28 resize-none"
                />
                <div className="flex min-h-[20px] items-center justify-between">
                    <p className="text-xs text-error">{errors.contexto?.message || ''}</p>
                    <div className="text-right text-xs text-muted-foreground">{contexto.length}/1000</div>
                </div>
            </div>
        </div>
    );
}

export function CreateWorkspaceModal({ open, onClose, onCreated }: CreateWorkspaceModalProps) {
    const { t } = useTranslation();
    const navigate = useNavigate();

    const methods = useForm<CreateWorkspaceFormValues>({
        resolver: zodResolver(CreateWorkspaceSchema),
        mode: 'onChange',
        defaultValues: DEFAULT_FORM_VALUES,
    });

    const {
        watch,
        reset,
        getValues,
        trigger,
        formState: { isDirty },
    } = methods;

    const [currentStep, setCurrentStep] = useState(1);
    const [creating, setCreating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [createdWorkspaceId, setCreatedWorkspaceId] = useState<string | null>(null);
    const createdWorkspaceRef = useRef<Workspace | null>(null);
    const [showCloseConfirm, setShowCloseConfirm] = useState(false);

    const [aiEstado, setAiEstado] = useState<'idle' | 'validando' | 'preguntas' | 'mejorando' | 'completo'>('idle');
    const [aiPreguntas, setAiPreguntas] = useState<string[]>([]);
    const [aiRespuestas, setAiRespuestas] = useState<string[]>([]);
    const [aiRespuestaActual, setAiRespuestaActual] = useState('');

    useEffect(() => {
        if (!open) return;

        const rawDraft = localStorage.getItem(WORKSPACE_DRAFT_KEY);
        if (rawDraft) {
            try {
                const parsed = JSON.parse(rawDraft) as Partial<CreateWorkspaceFormValues>;
                reset({ ...DEFAULT_FORM_VALUES, ...parsed });
            } catch {
                localStorage.removeItem(WORKSPACE_DRAFT_KEY);
                reset(DEFAULT_FORM_VALUES);
            }
        } else {
            reset(DEFAULT_FORM_VALUES);
        }
    }, [open, reset]);

    useEffect(() => {
        if (!open) return;

        const subscription = watch((values) => {
            localStorage.setItem(WORKSPACE_DRAFT_KEY, JSON.stringify(values));
        });

        return () => subscription.unsubscribe();
    }, [open, watch]);

    const handleClose = () => {
        reset(DEFAULT_FORM_VALUES);
        setError(null);
        setCurrentStep(1);
        setCreatedWorkspaceId(null);
        createdWorkspaceRef.current = null;
        setAiEstado('idle');
        setAiPreguntas([]);
        setAiRespuestas([]);
        setAiRespuestaActual('');
        setShowCloseConfirm(false);
        localStorage.removeItem(WORKSPACE_DRAFT_KEY);
        onClose();
    };

    const attemptClose = () => {
        if (isDirty && !createdWorkspaceId) {
            setShowCloseConfirm(true);
        } else {
            handleClose();
        }
    };

    const nextStep = async () => {
        if (currentStep === 1) {
            const isValid = await trigger(['nombre']);
            if (!isValid) return;
        }

        if (currentStep === 2) {
            const isValid = await trigger(['contexto']);
            if (!isValid) return;
        }

        setError(null);
        setCurrentStep((prev) => Math.min(prev + 1, 3));
    };

    const prevStep = () => setCurrentStep((prev) => Math.max(prev - 1, 1));

    const validarContexto = async (id: string) => {
        try {
            const data = await apiRequest<{ validacion: { suficiente: boolean; preguntas?: string[] } }>(
                `/workspaces/${id}/chat/validate`,
                { method: 'POST' },
            );

            if (data?.validacion.suficiente) {
                setAiEstado('completo');
            } else {
                setAiPreguntas(data?.validacion.preguntas || []);
                setAiEstado('preguntas');
            }
        } catch (err: unknown) {
            setError(getErrorMessage(err));
            setAiEstado('completo');
        } finally {
            setCreating(false);
        }
    };

    const handleCreateAndValidate = async () => {
        try {
            setCreating(true);
            setError(null);

            const values = getValues();

            const data: CreateWorkspaceRequest = {
                nombre: values.nombre,
                descripcion: values.descripcion,
                contexto: values.contexto,
                color: DEFAULT_WORKSPACE_COLOR,
                categoria: values.categoria,
                tipo_contenido: '',
                elementos_visuales: '',
                nivel_tolerancia: values.nivel_tolerancia,
                icono_url: '',
            };

            const workspace = await workspaceService.createWorkspace(data);
            setCreatedWorkspaceId(workspace.id);
            createdWorkspaceRef.current = workspace;
            localStorage.removeItem(WORKSPACE_DRAFT_KEY);

            setAiEstado('validando');
            setTimeout(() => void validarContexto(workspace.id), 500);
        } catch (err: unknown) {
            setError(getErrorMessage(err));
            setCreating(false);
        }
    };

    const handleFinalize = () => {
        const wsId = createdWorkspaceRef.current?.id || createdWorkspaceId;
        if (createdWorkspaceRef.current && onCreated) {
            onCreated(createdWorkspaceRef.current);
        }
        handleClose();
        if (wsId) {
            navigate({ to: '/proyecto/$id', params: { id: wsId } });
        }
    };

    const handleCreateWithoutAI = async () => {
        try {
            setCreating(true);
            setError(null);

            const values = getValues();

            const data: CreateWorkspaceRequest = {
                nombre: values.nombre,
                descripcion: values.descripcion,
                contexto: values.contexto,
                color: DEFAULT_WORKSPACE_COLOR,
                categoria: values.categoria,
                tipo_contenido: '',
                elementos_visuales: '',
                nivel_tolerancia: values.nivel_tolerancia,
                icono_url: '',
            };

            const workspace = await workspaceService.createWorkspace(data);
            setCreatedWorkspaceId(workspace.id);
            createdWorkspaceRef.current = workspace;
            localStorage.removeItem(WORKSPACE_DRAFT_KEY);
            setAiEstado('completo');
        } catch (err: unknown) {
            setError(getErrorMessage(err));
        } finally {
            setCreating(false);
        }
    };

    const handleAiResponder = async () => {
        if (!aiRespuestaActual.trim()) return;

        const nuevasRespuestas = [...aiRespuestas, aiRespuestaActual.trim()];
        setAiRespuestas(nuevasRespuestas);
        setAiRespuestaActual('');

        if (nuevasRespuestas.length === aiPreguntas.length) {
            setAiEstado('mejorando');
            try {
                if (!createdWorkspaceId) return;

                await apiRequest(`/workspaces/${createdWorkspaceId}/chat/improve`, {
                    method: 'POST',
                    body: JSON.stringify({ respuestas: nuevasRespuestas }),
                });

                setAiEstado('completo');
            } catch {
                setError('');
                setAiEstado('completo');
            }
        }
    };

    const renderStep3AI = () => {
        if (aiEstado === 'idle' && !creating) {
            return (
                <div className="flex flex-col items-center justify-center space-y-6 py-10 text-center">
                    <div className="flex h-20 w-20 items-center justify-center rounded-full bg-brand-soft">
                        <Sparkles className="h-10 w-10 text-primary" aria-hidden="true" />
                    </div>
                    <div>
                        <h3 className="text-lg font-bold text-foreground">{t('createWorkspace.allReadyTitle')}</h3>
                        <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
                            {t('createWorkspace.allReadyDesc')}
                        </p>
                    </div>
                    <Button onClick={handleCreateAndValidate} size="lg">
                        {t('createWorkspace.createAndValidate')}
                        <ArrowRight aria-hidden="true" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={handleCreateWithoutAI} className="text-muted-foreground">
                        <SkipForward aria-hidden="true" />
                        {t('createWorkspace.createWithoutAi')}
                    </Button>
                </div>
            );
        }

        if (creating || aiEstado === 'validando' || aiEstado === 'mejorando') {
            return (
                <div className="flex flex-col items-center justify-center space-y-6 py-16" aria-live="polite">
                    <Spinner size="xl" className="text-primary" />
                    <div className="text-center">
                        <h3 className="text-lg font-bold text-foreground">
                            {creating
                                ? t('createWorkspace.creating')
                                : aiEstado === 'validando'
                                    ? t('createWorkspace.validatingContext')
                                    : t('createWorkspace.improvingContext')}
                        </h3>
                        <p className="mt-2 text-sm text-muted-foreground">{t('createWorkspace.configuringHint')}</p>
                    </div>
                    {(aiEstado === 'validando' || aiEstado === 'mejorando') && (
                        <Button variant="ghost" size="sm" onClick={() => setAiEstado('completo')} className="text-muted-foreground">
                            <SkipForward aria-hidden="true" />
                            {t('createWorkspace.skipAndContinue')}
                        </Button>
                    )}
                </div>
            );
        }

        if (aiEstado === 'preguntas') {
            const currentQIndex = aiRespuestas.length;
            const currentQ = aiPreguntas[currentQIndex];

            return (
                <div className="space-y-6">
                    <Alert variant="warning">
                        <Sparkles aria-hidden="true" />
                        <AlertTitle>{t('createWorkspace.needsClarify')}</AlertTitle>
                        <AlertDescription>{t('createWorkspace.needsClarifyDesc')}</AlertDescription>
                    </Alert>

                    <div className="space-y-4">
                        <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                            <span className="mb-1 block text-xs font-bold uppercase tracking-wider text-muted-foreground">
                                {t('createWorkspace.questionOf', {
                                    current: currentQIndex + 1,
                                    total: aiPreguntas.length,
                                })}
                            </span>
                            <p className="text-base font-medium text-foreground">{currentQ}</p>
                        </div>

                        <div className="flex gap-2">
                            <Input
                                type="text"
                                value={aiRespuestaActual}
                                onChange={(e) => setAiRespuestaActual(e.target.value)}
                                placeholder={t('createWorkspace.answerPlaceholder')}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                        e.preventDefault();
                                        void handleAiResponder();
                                    }
                                }}
                                autoFocus
                            />
                            <Button
                                onClick={() => void handleAiResponder()}
                                disabled={!aiRespuestaActual.trim()}
                                size="icon"
                                aria-label={t('createWorkspace.sendAnswer')}
                            >
                                <ArrowRight aria-hidden="true" />
                            </Button>
                        </div>
                    </div>
                </div>
            );
        }

        if (aiEstado === 'completo') {
            return (
                <div className="flex flex-col items-center justify-center space-y-6 py-12 text-center">
                    <div className="flex h-20 w-20 items-center justify-center rounded-full bg-success-surface">
                        <CheckCircle2 className="h-10 w-10 text-success" aria-hidden="true" />
                    </div>
                    <div>
                        <h3 className="text-xl font-bold text-foreground">{t('createWorkspace.projectCreatedTitle')}</h3>
                        <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
                            {t('createWorkspace.projectCreatedDesc')}
                        </p>
                    </div>
                    <Button onClick={handleFinalize} className="w-full md:w-auto">
                        {t('createWorkspace.goToProject')}
                    </Button>
                </div>
            );
        }

        return null;
    };

    const progressPercent = ((currentStep - 1) / (STEP_KEYS.length - 1)) * 100;

    return (
        <>
            <Dialog
                open={open}
                onOpenChange={(nextOpen) => {
                    if (!nextOpen) {
                        attemptClose();
                    }
                }}
            >
                <DialogContent
                    className="flex max-h-[90vh] max-w-4xl flex-col gap-0 overflow-hidden p-0"
                    onInteractOutside={(e: Event) => e.preventDefault()}
                >
                    <DialogHeader className="relative flex-row items-center justify-between gap-3 bg-foreground px-6 py-5">
                        <div className="flex items-center gap-3">
                            <div className="rounded-xl bg-white/10 p-2.5 backdrop-blur">
                                <FolderOpen className="text-primary-foreground" size={22} aria-hidden="true" />
                            </div>
                            <div className="text-left">
                                <DialogTitle className="text-lg font-bold text-primary-foreground md:text-xl">
                                    {t('createWorkspace.title')}
                                </DialogTitle>
                                <DialogDescription className="text-xs text-primary-foreground/70 md:text-sm">
                                    {t('createWorkspace.subtitle')}
                                </DialogDescription>
                            </div>
                        </div>
                    </DialogHeader>

                    <div className="shrink-0 border-b border-border bg-card px-4 py-3 md:px-8 md:py-4">
                        <ol className="relative mx-auto flex max-w-2xl items-center justify-between">
                            <div className="absolute left-0 top-[14px] -z-10 h-0.5 w-full bg-border md:top-[16px]" />
                            <div
                                className="absolute left-0 top-[14px] -z-10 h-0.5 bg-primary transition-all duration-500 ease-in-out md:top-[16px]"
                                style={{ width: `${progressPercent}%` }}
                            />
                            {STEP_KEYS.map((stepKey, index) => {
                                const stepNumber = index + 1;
                                const isActive = stepNumber === currentStep;
                                const isCompleted = stepNumber < currentStep;
                                return (
                                    <li
                                        key={stepKey}
                                        aria-current={isActive ? 'step' : undefined}
                                        className="flex min-w-[50px] flex-col items-center gap-1.5 bg-card px-1 md:min-w-[60px] md:gap-2 md:px-2"
                                    >
                                        <div
                                            className={cn(
                                                'flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-all duration-300 md:h-8 md:w-8',
                                                isActive
                                                    ? 'scale-110 bg-primary text-primary-foreground shadow-sm'
                                                    : isCompleted
                                                        ? 'bg-primary text-primary-foreground'
                                                        : 'border border-border bg-muted text-muted-foreground',
                                            )}
                                        >
                                            {isCompleted ? (
                                                <>
                                                    <CheckCircle2 size={14} aria-hidden="true" />
                                                    <span className="sr-only">{t('createWorkspace.stepCompleted')}</span>
                                                </>
                                            ) : (
                                                stepNumber
                                            )}
                                        </div>
                                        <span
                                            className={cn(
                                                'hidden text-[9px] font-bold uppercase tracking-wider transition-colors sm:block md:text-[10px]',
                                                isActive ? 'text-primary' : isCompleted ? 'text-primary' : 'text-muted-foreground',
                                            )}
                                        >
                                            {t(stepKey)}
                                        </span>
                                    </li>
                                );
                            })}
                        </ol>
                    </div>

                    <div className="flex-1 overflow-y-auto bg-muted/30 px-6 py-5 md:px-10 md:py-6">
                        <FormProvider {...methods}>
                            <div className="mx-auto max-w-3xl">
                                {error && (
                                    <Alert variant="error" className="mb-4">
                                        <AlertCircle aria-hidden="true" />
                                        <AlertTitle>{t('common.error')}</AlertTitle>
                                        <AlertDescription>{error}</AlertDescription>
                                    </Alert>
                                )}

                                {currentStep === 1 && <ProjectStep />}
                                {currentStep === 2 && <AIConfigStep />}
                                {currentStep === 3 && renderStep3AI()}
                            </div>
                        </FormProvider>
                    </div>

                    {currentStep < 3 && (
                        <div className="flex shrink-0 items-center justify-between border-t border-border bg-card px-4 py-4 md:px-8">
                            <Button
                                variant="ghost"
                                onClick={currentStep === 1 ? attemptClose : prevStep}
                            >
                                {currentStep === 1 ? t('common.cancel') : t('common.back')}
                            </Button>

                            <Button
                                onClick={() => void nextStep()}
                            >
                                {t('common.next')}
                                <ChevronRight aria-hidden="true" />
                            </Button>
                        </div>
                    )}
                </DialogContent>
            </Dialog>

            <ConfirmDialog
                open={showCloseConfirm}
                onOpenChange={setShowCloseConfirm}
                onConfirm={handleClose}
                title={t('createWorkspace.discardTitle')}
                description={t('createWorkspace.discardDesc')}
                confirmText={t('createWorkspace.discard')}
                cancelText={t('createWorkspace.keepEditing')}
            />
        </>
    );
}
