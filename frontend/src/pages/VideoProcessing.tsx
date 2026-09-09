import { useEffect, useState } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { Check, Loader2, AlertCircle, FileVideo } from 'lucide-react';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { apiRequest } from '../lib/api';


interface Phase {
    id: number;
    title: string;
    description: string;
    steps: number[];
    stepLabels: string[];
}

const PHASES: Phase[] = [
    {
        id: 1,
        title: 'Carga y Preparación',
        description: 'Estamos subiendo y preparando tu video.',
        steps: [1, 2],
        stepLabels: ['Carga a almacenamiento local', 'Verificación de duración']
    },
    {
        id: 2,
        title: 'Análisis del Contenido',
        description: 'Analizamos lo que aparece y se escucha en el video.',
        steps: [3, 4, 5],
        stepLabels: ['Análisis de video local', 'IA de visión local', 'Transcripción local']
    },
    {
        id: 3,
        title: 'Evaluación Inteligente',
        description: 'Evaluamos el contenido según políticas y contexto.',
        steps: [6],
        stepLabels: ['Motor de decisión (DeepSeek)']
    },
    {
        id: 4,
        title: 'Resultados',
        description: 'Generamos información útil para ti.',
        steps: [7, 8],
        stepLabels: ['Generación de título', 'Output final']
    }
];

interface ProcessingState {
    currentStep: number;
    stepStatus: 'running' | 'success' | 'warning' | 'error' | 'skipped' | 'pending';
    status: 'pending' | 'processing' | 'completed' | 'error';
    message: string;
    details?: any;
    videoResult?: any;
}

export default function VideoProcessing() {
    const { videoId } = useParams({ from: '/app/processing/$videoId' });
    const navigate = useNavigate();
    const [state, setState] = useState<ProcessingState>({
        currentStep: 0,
        stepStatus: 'pending',
        status: 'pending',
        message: 'Iniciando conexión...',
    });

    useEffect(() => {
        if (!videoId) return;

        let pollingInterval: NodeJS.Timeout;
        let isPolling = true;

        const checkStatus = async () => {
            if (!isPolling) return;
            try {
                const response = await apiRequest(`/socio/video/${videoId}/status`) as any;

                if (response.status === 'completed') {
                    setState(s => ({
                        ...s,
                        status: 'completed',
                        currentStep: 8,
                        stepStatus: 'success',
                        message: response.message,
                        videoResult: response.final_result?.video
                    }));
                    isPolling = false; // Stop polling
                } else if (response.status === 'error') {
                    setState(s => ({
                        ...s,
                        status: 'error',
                        stepStatus: 'error',
                        message: response.message,
                        details: response.error
                    }));
                    isPolling = false;
                } else if (response.status === 'processing') {
                    // Update progress
                    setState(s => ({
                        ...s,
                        status: 'processing',
                        currentStep: response.step || s.currentStep,
                        message: response.message || s.message,
                        stepStatus: response.stepStatus || 'running',
                        details: response.details
                    }));
                } else if (response.status === 'pending') {
                    setState(s => ({ ...s, status: 'pending', message: 'Iniciando...' }));
                }

            } catch (error) {
                console.error("Polling error:", error);
                // Don't stop polling immediately on network error, retry next tick
            }
        };

        // Start processing call (idempotent)
        const startProcessing = async () => {
            try {
                await apiRequest(`/socio/video/${videoId}/start_processing`, { method: 'POST' });
                // Immediate check after start
                checkStatus();
                // Start polling loop
                pollingInterval = setInterval(checkStatus, 2000);
            } catch (err) {
                console.error("Error starting processing:", err);
                // If start fails, checking status might still reveal it's already running or failed
                pollingInterval = setInterval(checkStatus, 2000);
            }
        };

        startProcessing();

        return () => {
            isPolling = false;
            if (pollingInterval) clearInterval(pollingInterval);
        };
    }, [videoId]);

    return (
        <div className="max-w-6xl mx-auto p-6 space-y-8">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900">Procesando Video</h1>
                    <p className="text-gray-500 mt-1">Análisis de IA en tiempo real</p>
                </div>
                {state.status === 'completed' && (
                    <Button onClick={() => navigate({ to: '/mis-videos' })}>
                        Ver mis videos
                    </Button>
                )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Visual Preview / Status Card */}
                <div className="lg:col-span-2 space-y-6">
                    <Card className="aspect-video bg-gray-900 rounded-xl overflow-hidden flex items-center justify-center relative shadow-xl">
                        {state.videoResult?.video_url && (
                            <video
                                src={state.videoResult.video_url}
                                className="w-full h-full object-contain"
                                autoPlay
                                muted
                                loop
                                playsInline
                                controls
                            />
                        )}

                        {state.status === 'processing' && (
                            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/50 backdrop-blur-sm animate-pulse z-10">
                                <span className="loader mb-4"></span>
                                <p className="text-white font-medium text-lg tracking-wide">{state.message}</p>
                            </div>
                        )}

                        {state.status === 'completed' ? (
                            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70 z-20">
                                {state.videoResult?.resultado === 'APROBADO' && <Check className="w-20 h-20 text-green-500 mb-4" />}
                                {state.videoResult?.resultado === 'RECHAZADO' && <AlertCircle className="w-20 h-20 text-red-500 mb-4" />}
                                {state.videoResult?.resultado === 'REQUIERE_REVISION' && <div className="w-20 h-20 text-amber-500 mb-4 text-center text-6xl">⏳</div>}

                                <h3 className="text-3xl font-bold text-white mb-2">
                                    {state.videoResult?.resultado === 'APROBADO' && '¡Video Aprobado!'}
                                    {state.videoResult?.resultado === 'RECHAZADO' && 'Video Rechazado'}
                                    {state.videoResult?.resultado === 'REQUIERE_REVISION' && 'Revisión Manual Requerida'}
                                </h3>
                                <p className="text-gray-300 text-lg">
                                    {state.videoResult?.razon}
                                </p>
                            </div>
                        ) : state.status === 'error' ? (
                            <div className="text-center text-red-500 p-8 z-10">
                                <AlertCircle size={64} className="mx-auto mb-4" />
                                <h3 className="text-2xl font-bold text-white mb-2">Error en el procesamiento</h3>
                                <p className="text-gray-300">{state.message}</p>
                            </div>
                        ) : !state.videoResult && (
                            <div className="text-center text-gray-500">
                                <FileVideo size={64} className="mx-auto mb-2 opacity-50" />
                                <p>Esperando video...</p>
                            </div>
                        )}

                        {/* Static background pattern */}
                        <div className="absolute inset-0 opacity-10 bg-[radial-gradient(ellipse_at_center,var(--tw-gradient-stops))] from-gray-700 via-gray-900 to-black pointer-events-none"></div>
                    </Card>

                    {state.videoResult && (
                        <Card className="p-6">
                            <h3 className="text-lg font-bold mb-4">Resumen del Análisis</h3>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                                <div className="p-4 bg-gray-50 rounded-lg">
                                    <p className="text-gray-500 mb-1">Título Generado</p>
                                    <p className="font-semibold text-gray-900">{state.videoResult.titulo}</p>
                                </div>
                                <div className="p-4 bg-gray-50 rounded-lg">
                                    <p className="text-gray-500 mb-1">Resultado</p>
                                    <div className={`font-bold inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium
                                        ${state.videoResult.resultado === 'APROBADO' ? 'bg-green-100 text-green-800' :
                                            state.videoResult.resultado === 'RECHAZADO' ? 'bg-red-100 text-red-800' :
                                                'bg-amber-100 text-amber-800'}`}>
                                        {state.videoResult.resultado}
                                    </div>
                                </div>
                                <div className="p-4 bg-gray-50 rounded-lg">
                                    <p className="text-gray-500 mb-1">Confianza</p>
                                    <p className="font-semibold text-gray-900">
                                        {(state.videoResult.confianza * 100).toFixed(1)}%
                                    </p>
                                </div>
                                {state.videoResult.razon && (
                                    <div className="md:col-span-3 p-4 bg-blue-50 rounded-lg border border-blue-100">
                                        <p className="text-blue-600 mb-1 font-semibold">Detalle de la Decisión</p>
                                        <p className="text-blue-900">{state.videoResult.razon}</p>
                                    </div>
                                )}
                            </div>
                        </Card>
                    )}
                </div>

                {/* Phases List */}
                <Card className="h-fit sticky top-6">
                    <div className="p-6 border-b border-gray-100 bg-gray-50/50">
                        <h2 className="font-bold text-lg text-gray-900">Etapas del Proceso</h2>
                        <p className="text-sm text-gray-500">Progreso general: {Math.min(Math.round((state.currentStep / 7) * 100), 100)}%</p>
                    </div>
                    <div className="p-6 space-y-6">
                        {PHASES.map((phase, index) => {
                            // Logic for Phase Status
                            const currentStep = state.currentStep;
                            const isPhaseComplete = phase.steps.every(s => s < currentStep) || state.status === 'completed';
                            const isPhaseActive = phase.steps.includes(currentStep) && state.status === 'processing';
                            const isPhasePending = !isPhaseComplete && !isPhaseActive;
                            const isPhaseError = state.status === 'error' && phase.steps.includes(currentStep);

                            return (
                                <div key={phase.id} className={`relative ${index !== PHASES.length - 1 ? 'pb-8' : ''}`}>
                                    {/* Connecting Line for Phases */}
                                    {index !== PHASES.length - 1 && (
                                        <div className={`absolute left-4 top-10 bottom-0 w-0.5 ${isPhaseComplete ? 'bg-green-500' : 'bg-gray-200'} z-0`} />
                                    )}

                                    <div className="relative z-10">
                                        <div className="flex items-start gap-4">
                                            {/* Phase Icon */}
                                            <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 border-2 transition-all duration-300
                                                    ${isPhaseComplete ? 'bg-green-500 border-green-500 text-white shadow-lg shadow-green-200' :
                                                    isPhaseError ? 'bg-red-500 border-red-500 text-white' :
                                                        isPhaseActive ? 'bg-white border-tivit-red text-tivit-red shadow-lg shadow-red-100 scale-110' :
                                                            'bg-white border-gray-300 text-gray-300'}
                                                `}>
                                                {isPhaseComplete ? <Check size={16} strokeWidth={3} /> :
                                                    isPhaseError ? <AlertCircle size={16} /> :
                                                        isPhaseActive ? <Loader2 size={16} className="animate-spin" /> :
                                                            <span className="text-sm font-bold">{phase.id}</span>
                                                }
                                            </div>

                                            <div className="flex-1 pt-1">
                                                <h3 className={`font-bold text-base ${isPhaseActive ? 'text-tivit-red' : isPhaseComplete ? 'text-gray-900' : 'text-gray-500'}`}>
                                                    FASE {index + 1} – {phase.title}
                                                </h3>
                                                <p className="text-sm text-gray-500 mt-1 mb-3">
                                                    {phase.description}
                                                </p>

                                                {/* Sub-steps List */}
                                                <div className="space-y-2 pl-2 border-l-2 border-gray-100/50">
                                                    {phase.steps.map((stepId, i) => {
                                                        const label = phase.stepLabels[i];
                                                        const isStepDone = currentStep > stepId || state.status === 'completed';
                                                        const isStepCurrent = currentStep === stepId && state.status === 'processing';

                                                        return (
                                                            <div key={stepId} className="flex items-center gap-2.5">
                                                                <div className={`w-2 h-2 rounded-full transition-colors duration-300
                                                                        ${isStepDone ? 'bg-green-500' :
                                                                        isStepCurrent ? 'bg-tivit-red animate-pulse' :
                                                                            'bg-gray-200'}
                                                                    `} />
                                                                <span className={`text-xs font-medium transition-colors duration-300
                                                                        ${isStepDone ? 'text-green-700' :
                                                                        isStepCurrent ? 'text-tivit-red' :
                                                                            'text-gray-400'}
                                                                    `}>
                                                                    {label}
                                                                </span>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </Card>
            </div>
        </div>
    );
}
