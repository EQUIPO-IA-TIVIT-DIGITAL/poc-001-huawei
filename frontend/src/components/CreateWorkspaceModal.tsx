import { useEffect, useRef, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
    X,
    FolderOpen,
    Sparkles,
    ChevronRight,
    CheckCircle,
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
import { FormProvider, useForm, useFormContext } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { workspaceService, type CreateWorkspaceRequest } from '../services/workspace';
import { apiRequest } from '../lib/api';
import { getErrorMessage } from '../lib/errors';
import { Button } from './ui/button';

interface CreateWorkspaceModalProps {
    open: boolean;
    onClose: () => void;
    onCreated?: (workspace: unknown) => void;
}

const DEFAULT_WORKSPACE_COLOR = '#3B82F6';
const WORKSPACE_DRAFT_KEY = 'cu002-create-workspace-draft-v1';

const CATEGORIAS = [
    { value: 'deportes', label: 'Deportes', icon: Trophy, description: 'Competencias, entrenamientos, deportes de contacto' },
    { value: 'seguridad', label: 'Seguridad', icon: Shield, description: 'Vigilancia, monitoreo, cámaras de seguridad' },
    { value: 'educacion', label: 'Educación', icon: GraduationCap, description: 'Clases, tutoriales, contenido educativo' },
    { value: 'eventos', label: 'Eventos', icon: CalendarDays, description: 'Fiestas, conciertos, reuniones sociales' },
    { value: 'industrial', label: 'Industrial', icon: Factory, description: 'Procesos industriales, control de calidad' },
    { value: 'entretenimiento', label: 'Entretenimiento', icon: Clapperboard, description: 'Contenido creativo, sketches, vlogs' },
    { value: 'salud', label: 'Salud', icon: Stethoscope, description: 'Contenido médico, terapias, procedimientos' },
    { value: 'general', label: 'General', icon: FolderOpen, description: 'Sin categoría específica' },
];

const NIVELES_TOLERANCIA = [
    {
        value: 'bajo',
        label: 'Estricto',
        icon: Lock,
        color: 'text-blue-600',
        description: 'Para contenido familiar, educativo o corporativo formal'
    },
    {
        value: 'medio',
        label: 'Balanceado',
        icon: Scale,
        color: 'text-gray-600',
        description: 'Análisis estándar, criterios moderados'
    },
    {
        value: 'alto',
        label: 'Tolerante',
        icon: Target,
        color: 'text-red-600',
        description: 'Para deportes de contacto, acción, contenido intenso'
    },
];

const STEPS = [
    { number: 1, title: 'Proyecto' },
    { number: 2, title: 'Configuración IA' },
    { number: 3, title: 'Confirmación' },
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
        <div className="space-y-5 animate-in slide-in-from-right-4 duration-300">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1.5 animate-in fade-in slide-in-from-bottom-2 duration-300" style={{ animationDelay: '50ms' }}>
                    <label htmlFor="workspace-nombre" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Nombre del Proyecto <span className="text-red-500">*</span>
                    </label>
                    <input
                        id="workspace-nombre"
                        type="text"
                        {...register('nombre')}
                        onChange={(e) => setValue('nombre', e.target.value.slice(0, 50), { shouldDirty: true, shouldValidate: true })}
                        placeholder="Ej: Análisis de Seguridad Planta 1"
                        className="w-full px-4 py-3 text-sm bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-red-500/40 focus:border-red-500 focus:bg-white outline-none transition-all duration-200"
                        autoFocus
                    />
                    <div className="flex items-center justify-between min-h-[20px]">
                        <p className="text-xs text-red-600">{errors.nombre?.message || ''}</p>
                        <div className="text-xs text-gray-400 text-right">{nombre.length}/50</div>
                    </div>
                </div>

                <div className="space-y-1.5 animate-in fade-in slide-in-from-bottom-2 duration-300" style={{ animationDelay: '100ms' }}>
                    <label htmlFor="workspace-descripcion" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider">Descripción</label>
                    <input
                        id="workspace-descripcion"
                        type="text"
                        {...register('descripcion')}
                        onChange={(e) => setValue('descripcion', e.target.value.slice(0, 200), { shouldDirty: true, shouldValidate: true })}
                        placeholder="Breve descripción del propósito..."
                        className="w-full px-4 py-3 text-sm bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-red-500/40 focus:border-red-500 focus:bg-white outline-none transition-all duration-200"
                    />
                    <div className="flex items-center justify-between min-h-[20px]">
                        <p className="text-xs text-red-600">{errors.descripcion?.message || ''}</p>
                        <div className="text-xs text-gray-400 text-right">{descripcion.length}/200</div>
                    </div>
                </div>
            </div>

            <div className="space-y-2 animate-in fade-in slide-in-from-bottom-2 duration-300" style={{ animationDelay: '150ms' }}>
                <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider">Categoría</label>
                <div role="radiogroup" aria-label="Categoría del proyecto" className="grid grid-cols-4 md:grid-cols-8 gap-2">
                    {CATEGORIAS.map((cat, i) => (
                        <button
                            key={cat.value}
                            type="button"
                            role="radio"
                            aria-checked={categoria === cat.value}
                            onClick={() => setValue('categoria', cat.value, { shouldDirty: true })}
                            className={`group flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-all duration-200 animate-in fade-in zoom-in-95 ${
                                categoria === cat.value
                                    ? 'border-red-400 bg-red-50 shadow-sm ring-1 ring-red-200'
                                    : 'border-gray-200 bg-white hover:border-red-200 hover:shadow-sm hover:translate-y-[-1px]'
                            }`}
                            style={{ animationDelay: `${200 + i * 40}ms` }}
                        >
                            <cat.icon size={20} className={`transition-transform duration-200 ${categoria === cat.value ? 'scale-110 text-red-600' : 'text-gray-500 group-hover:text-red-600 group-hover:scale-110'}`} />
                            <span className={`text-[10px] font-semibold leading-tight text-center transition-colors duration-200 ${categoria === cat.value ? 'text-red-700' : 'text-gray-600 group-hover:text-red-600'}`}>
                                {cat.label}
                            </span>
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}

function AIConfigStep() {
    const {
        register,
        watch,
        setValue,
        formState: { errors },
    } = useFormContext<CreateWorkspaceFormValues>();

    const nivelTolerancia = watch('nivel_tolerancia');
    const contexto = watch('contexto');

    return (
        <div className="space-y-5 animate-in slide-in-from-right-4 duration-300">
            <div className="space-y-2 animate-in fade-in slide-in-from-bottom-2 duration-300" style={{ animationDelay: '50ms' }}>
                <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider">Nivel de Análisis IA</label>
                <div role="radiogroup" aria-label="Nivel de análisis IA" className="grid grid-cols-3 gap-3">
                    {NIVELES_TOLERANCIA.map((nivel, i) => (
                        <button
                            key={nivel.value}
                            type="button"
                            role="radio"
                            aria-checked={nivelTolerancia === nivel.value}
                            onClick={() => setValue('nivel_tolerancia', nivel.value, { shouldDirty: true })}
                            className={`p-3.5 rounded-xl border text-left transition-all duration-200 hover:-translate-y-0.5 animate-in fade-in zoom-in-95 ${
                                nivelTolerancia === nivel.value
                                    ? 'border-red-400 bg-red-50 ring-1 ring-red-200 shadow-sm'
                                    : 'border-gray-200 bg-white hover:border-red-200 hover:shadow-sm'
                            }`}
                            style={{ animationDelay: `${100 + i * 60}ms` }}
                        >
                            <div className="flex items-center gap-2 mb-1">
                                <span className={`w-7 h-7 rounded-md flex items-center justify-center transition-transform duration-200 ${nivelTolerancia === nivel.value ? 'bg-red-100 scale-110' : 'bg-gray-100'}`}>
                                    <nivel.icon size={16} className={nivelTolerancia === nivel.value ? 'text-red-600' : nivel.color} />
                                </span>
                                <span className={`font-bold text-sm transition-colors duration-200 ${nivelTolerancia === nivel.value ? 'text-red-700' : nivel.color}`}>{nivel.label}</span>
                            </div>
                            <p className={`text-[11px] leading-snug transition-colors duration-200 ${nivelTolerancia === nivel.value ? 'text-red-700/80' : 'text-gray-500'}`}>{nivel.description}</p>
                        </button>
                    ))}
                </div>
            </div>

            <div className="space-y-1.5 animate-in fade-in slide-in-from-bottom-2 duration-300" style={{ animationDelay: '200ms' }}>
                <label htmlFor="workspace-contexto" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Contexto del Proyecto <span className="text-red-500">*</span>
                </label>
                <textarea
                    id="workspace-contexto"
                    {...register('contexto')}
                    onChange={(e) => setValue('contexto', e.target.value.slice(0, 1000), { shouldDirty: true, shouldValidate: true })}
                    placeholder="Describe el tipo de videos, reglas específicas, excepciones o detalles importantes para el análisis IA..."
                    className="w-full px-4 py-3 text-sm bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-red-500/40 focus:border-red-500 focus:bg-white outline-none resize-none h-28 transition-all duration-200"
                />
                <div className="flex items-center justify-between min-h-[20px]">
                    <p className="text-xs text-red-600">{errors.contexto?.message || ''}</p>
                    <div className="text-xs text-gray-400 text-right">{contexto.length}/1000</div>
                </div>
            </div>
        </div>
    );
}

export function CreateWorkspaceModal({ open, onClose, onCreated }: CreateWorkspaceModalProps) {
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

    // UI State
    const [currentStep, setCurrentStep] = useState(1);
    const [creating, setCreating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [createdWorkspaceId, setCreatedWorkspaceId] = useState<string | null>(null);
    const createdWorkspaceRef = useRef<any>(null);
    const [showCloseConfirm, setShowCloseConfirm] = useState(false);

    // AI Validation State
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

    // Attempt to close — ask confirmation if user has unsaved data
    const attemptClose = () => {
        if (isDirty && !createdWorkspaceId) {
            setShowCloseConfirm(true);
        } else {
            handleClose();
        }
    };

    // Reset state on close
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
        setCurrentStep(prev => Math.min(prev + 1, 3));
    };

    const prevStep = () => setCurrentStep(prev => Math.max(prev - 1, 1));

    // --- AI Validation Logic ---

    const handleCreateAndValidate = async () => {
        try {
            setCreating(true);
            setError(null);

            const values = getValues();

            // 1. Create Workspace
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
            // IMPORTANT: We do NOT call onCreated here to avoid parent reload

            // 2. Start Validation
            setAiEstado('validando');
            // Small delay to ensure DB propagation if necessary
            setTimeout(() => validarContexto(workspace.id), 500);

        } catch (error: unknown) {
            setError(getErrorMessage(error));
            setCreating(false);
        }
    };

    const handleFinalize = () => {
        const wsId = createdWorkspaceRef.current?.id || createdWorkspaceId;
        if (createdWorkspaceRef.current && onCreated) {
            onCreated(createdWorkspaceRef.current);
        }
        handleClose();
        // Navigate to the created project
        if (wsId) {
            navigate({ to: '/proyecto/$id', params: { id: wsId } });
        }
    };

    // Skip AI validation — create workspace without Gemini analysis
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
        } catch (error: unknown) {
            setError(getErrorMessage(error));
        } finally {
            setCreating(false);
        }
    };

    const validarContexto = async (id: string) => {
        try {
            const data = await apiRequest<{ validacion: { suficiente: boolean; preguntas?: string[] } }>(
                `/workspaces/${id}/chat/validate`,
                { method: 'POST' }
            );

            if (data?.validacion.suficiente) {
                setAiEstado('completo');
            } else {
                setAiPreguntas(data?.validacion.preguntas || []);
                setAiEstado('preguntas');
            }
        } catch (error: unknown) {
            console.error(error);
            setError(getErrorMessage(error));
            // If validation fails error, we assume complete to let user continue
            setAiEstado('completo');
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

                await apiRequest(
                    `/workspaces/${createdWorkspaceId}/chat/improve`,
                    {
                        method: 'POST',
                        body: JSON.stringify({ respuestas: nuevasRespuestas })
                    }
                );

                setAiEstado('completo');
            } catch (error: unknown) {
                // La mejora de contexto es no-crítica: no bloquear flujo si falla Gemini.
                console.warn('No se pudo mejorar el contexto automáticamente:', getErrorMessage(error));
                setError('');
                setAiEstado('completo');
            }
        }
    };

    const renderStep3_AI = () => {
        if (aiEstado === 'idle' && !creating) {
            return (
                <div className="flex flex-col items-center justify-center py-10 space-y-6 text-center animate-in zoom-in-50 duration-300">
                    <div className="w-20 h-20 bg-red-50 rounded-full flex items-center justify-center">
                        <Sparkles className="text-red-600 w-10 h-10" />
                    </div>
                    <div>
                        <h3 className="text-lg font-bold text-gray-900">¡Todo listo!</h3>
                        <p className="text-sm text-gray-500 max-w-sm mx-auto mt-2">
                            Crearemos tu proyecto y la IA validará automáticamente si el contexto es suficiente.
                        </p>
                    </div>
                    <Button
                        onClick={handleCreateAndValidate}
                        className="bg-red-600 hover:bg-red-700 text-white px-8 py-4 rounded-xl text-base shadow-lg hover:shadow-xl hover:-translate-y-1 transition-all"
                    >
                        Crear y Validar con IA <ArrowRight className="ml-2 w-5 h-5" />
                    </Button>
                    <button
                        onClick={handleCreateWithoutAI}
                        className="text-sm text-gray-400 hover:text-gray-600 transition-colors flex items-center gap-1.5"
                    >
                        <SkipForward size={14} />
                        Crear sin validación IA
                    </button>
                </div>
            );
        }

        if (creating || aiEstado === 'validando' || aiEstado === 'mejorando') {
            return (
                <div className="flex flex-col items-center justify-center py-16 space-y-6 animate-in fade-in duration-300">
                    <span className="loader"></span>
                    <div className="text-center">
                        <h3 className="text-lg font-bold text-gray-900">
                            {creating ? 'Creando Proyecto...' :
                                aiEstado === 'validando' ? 'IA Analizando Contexto...' : 'Mejorando Contexto...'}
                        </h3>
                        <p className="text-sm text-gray-500 mt-2">Estamos configurando todo para ti</p>
                    </div>
                    {(aiEstado === 'validando' || aiEstado === 'mejorando') && (
                        <button
                            onClick={() => setAiEstado('completo')}
                            className="text-xs text-gray-400 hover:text-gray-600 transition-colors flex items-center gap-1 mt-2"
                        >
                            <SkipForward size={12} />
                            Omitir y continuar
                        </button>
                    )}
                </div>
            );
        }

        if (aiEstado === 'preguntas') {
            const currentQIndex = aiRespuestas.length;
            const currentQ = aiPreguntas[currentQIndex];

            return (
                <div className="space-y-6 animate-in slide-in-from-right-4 duration-300">
                    <div className="bg-amber-50/60 border border-amber-200 p-3.5 rounded-xl flex gap-3">
                        <Sparkles className="text-amber-600 shrink-0 mt-0.5" size={18} />
                        <div>
                            <h4 className="font-bold text-amber-800 text-xs">La IA necesita aclarar algo</h4>
                            <p className="text-xs text-amber-700 mt-0.5">
                                Responde para asegurar la máxima precisión en el análisis.
                            </p>
                        </div>
                    </div>

                    <div className="space-y-4">
                        <div className="bg-white border-2 border-gray-100 p-4 rounded-xl shadow-sm">
                            <span className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1 block">
                                Pregunta {currentQIndex + 1} de {aiPreguntas.length}
                            </span>
                            <p className="text-base font-medium text-gray-900">{currentQ}</p>
                        </div>

                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={aiRespuestaActual}
                                onChange={(e) => setAiRespuestaActual(e.target.value)}
                                placeholder="Escribe tu respuesta aquí..."
                                className="flex-1 px-4 py-3 text-sm bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-red-500/40 focus:border-red-500 focus:bg-white outline-none transition-all duration-200"
                                onKeyDown={(e) => e.key === 'Enter' && handleAiResponder()}
                                autoFocus
                            />
                            <Button
                                onClick={handleAiResponder}
                                disabled={!aiRespuestaActual.trim()}
                                className="bg-gradient-to-r from-tivit-red to-rose-500 hover:from-red-700 hover:to-rose-600 text-white px-4 rounded-xl shadow-md transition-all duration-200"
                            >
                                <ArrowRight />
                            </Button>
                        </div>
                    </div>
                </div>
            );
        }

        if (aiEstado === 'completo') {
            return (
                <div className="flex flex-col items-center justify-center py-12 space-y-6 text-center animate-in zoom-in-50 duration-300">
                    <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center">
                        <CheckCircle className="text-green-600 w-10 h-10" />
                    </div>
                    <div>
                        <h3 className="text-xl font-bold text-gray-900">¡Proyecto Creado!</h3>
                        <p className="text-sm text-gray-500 max-w-sm mx-auto mt-2">
                            Tu proyecto ha sido configurado y validado exitosamente.
                        </p>
                    </div>
                    <Button
                        onClick={handleFinalize}
                        className="bg-gradient-to-r from-tivit-red to-rose-500 hover:from-red-700 hover:to-rose-600 text-white px-8 py-3 rounded-xl shadow-md transition-all duration-200 w-full md:w-auto text-sm font-semibold hover:-translate-y-0.5"
                    >
                        Ir al Proyecto
                    </Button>
                </div>
            );
        }
    };

    if (!open) return null;

    return (
        <div
            className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-in fade-in duration-200"
            onClick={(e) => {
                if (e.target === e.currentTarget) attemptClose();
            }}
        >
            {/* Main Modal Container - Dynamic Height */}
            <div className="bg-white rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden shadow-2xl flex flex-col animate-in slide-in-from-bottom-4 duration-300 border border-gray-100">
                {/* Header */}
                <div className="px-6 md:px-8 py-5 bg-gradient-to-br from-[#1a1a2e] via-[#2d1b33] to-[#1a1a2e] flex items-center justify-between shrink-0 relative overflow-hidden">
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_80%_20%,rgba(227,6,19,0.15),transparent_60%)]" />
                    <div className="flex items-center gap-3 relative z-10">
                        <div className="bg-white/10 p-2.5 rounded-xl backdrop-blur-sm shadow-lg">
                            <FolderOpen className="text-white" size={22} />
                        </div>
                        <div>
                            <h2 className="text-lg md:text-xl font-bold text-white leading-tight">Nuevo Proyecto</h2>
                            <p className="text-xs md:text-sm text-gray-400">Configura tu espacio de trabajo inteligente</p>
                        </div>
                    </div>
                    <button
                        onClick={attemptClose}
                        className="text-gray-400 hover:text-white transition-all duration-200 p-2 rounded-full hover:bg-white/10 relative z-10 hover:rotate-90"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Stepper */}
                <div className="bg-white px-4 md:px-8 py-3 md:py-4 border-b border-gray-100 shrink-0">
                    <ol className="relative flex items-center justify-between max-w-2xl mx-auto">
                        {/* Connecting Line Back */}
                        <div className="absolute left-0 top-[14px] md:top-[16px] w-full h-0.5 bg-gray-200 -z-10" />

                        {/* Connecting Line Front (Progress) */}
                        <div
                            className="absolute left-0 top-[14px] md:top-[16px] h-0.5 bg-gradient-to-r from-tivit-red to-rose-400 -z-10 transition-all duration-500 ease-in-out"
                            style={{ width: `${((currentStep - 1) / (STEPS.length - 1)) * 100}%` }}
                        />

                        {STEPS.map((step) => {
                            const isActive = step.number === currentStep;
                            const isCompleted = step.number < currentStep;
                            return (
                                <li
                                    key={step.number}
                                    className="flex flex-col items-center gap-1.5 md:gap-2 bg-white px-1 md:px-2 min-w-[50px] md:min-w-[60px]"
                                    aria-current={isActive ? 'step' : undefined}
                                >
                                    <div
                                        className={`w-7 h-7 md:w-8 md:h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300 ${isActive
                                            ? 'bg-tivit-red text-white scale-110 shadow-lg shadow-red-300/40'
                                            : isCompleted
                                                ? 'bg-tivit-red text-white'
                                                : 'bg-gray-100 text-gray-400 border border-gray-200'
                                            }`}
                                    >
                                        {isCompleted ? (
                                            <>
                                                <CheckCircle size={14} />
                                                <span className="sr-only">Paso completado</span>
                                            </>
                                        ) : step.number}
                                    </div>
                                    <span
                                        className={`text-[9px] md:text-[10px] font-bold uppercase tracking-wider transition-colors hidden sm:block ${isActive ? 'text-red-600' : isCompleted ? 'text-red-500' : 'text-gray-400'
                                            }`}
                                    >
                                        {step.title}
                                    </span>
                                </li>
                            );
                        })}
                    </ol>
                </div>

                {/* Body */}
                <div className="flex-1 overflow-y-auto px-6 md:px-8 lg:px-10 py-5 md:py-6 bg-[#f9fafb]">
                    <FormProvider {...methods}>
                        <div className="max-w-3xl mx-auto">
                            {error && (
                                <div className="bg-red-50 text-red-700 px-4 py-3 rounded-xl mb-4 flex items-center gap-3 border border-red-100">
                                    <AlertCircle size={18} className="shrink-0" />
                                    <p className="text-sm font-medium">{error}</p>
                                </div>
                            )}

                            {currentStep === 1 && <ProjectStep />}
                            {currentStep === 2 && <AIConfigStep />}
                            {currentStep === 3 && renderStep3_AI()}
                        </div>
                    </FormProvider>
                </div>

                {/* Footer Actions - Responsive */}
                {currentStep < 3 && (
                    <div className="bg-white border-t border-gray-100 px-4 md:px-8 py-4 flex justify-between items-center shrink-0">
                        <Button
                            variant="ghost"
                            onClick={currentStep === 1 ? attemptClose : prevStep}
                            className="text-gray-500 hover:text-gray-900 hover:bg-gray-100 px-4 md:px-6 text-sm"
                        >
                            {currentStep === 1 ? 'Cancelar' : 'Atrás'}
                        </Button>

                        <Button
                            onClick={() => {
                                void nextStep();
                            }}
                            className="bg-gradient-to-r from-tivit-red to-rose-500 hover:from-red-700 hover:to-rose-600 text-white px-6 md:px-8 py-2.5 rounded-xl font-semibold shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 flex items-center gap-2 text-sm"
                        >
                            Siguiente
                            <ChevronRight size={18} />
                        </Button>
                    </div>
                )}

                {/* Confirmation dialog on close */}
                {showCloseConfirm && (
                    <div className="absolute inset-0 bg-black/30 backdrop-blur-[2px] flex items-center justify-center z-10 rounded-2xl">
                        <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm mx-4 animate-in zoom-in-95 duration-200">
                            <h3 className="text-base font-bold text-gray-900 mb-2">¿Descartar cambios?</h3>
                            <p className="text-sm text-gray-500 mb-5">Se perderán los datos ingresados del nuevo proyecto.</p>
                            <div className="flex gap-3 justify-end">
                                <Button
                                    variant="ghost"
                                    onClick={() => setShowCloseConfirm(false)}
                                    className="text-sm text-gray-600 hover:bg-gray-100"
                                >
                                    Seguir editando
                                </Button>
                                <Button
                                    onClick={handleClose}
                                    className="bg-red-600 hover:bg-red-700 text-white text-sm px-4 rounded-lg font-medium"
                                >
                                    Descartar
                                </Button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
