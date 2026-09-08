import { useState, useEffect, useRef } from 'react';
import { Button } from './ui/button';
import { X, Upload, Video, Brain, CheckCircle } from 'lucide-react';

interface AnalysisExplanationModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export function AnalysisExplanationModal({ isOpen, onClose }: AnalysisExplanationModalProps) {
    const [currentStep, setCurrentStep] = useState(0);
    const [isPaused, setIsPaused] = useState(false);
    const intervalRef = useRef<any>(null);

    const steps = [
        {
            icon: Upload,
            title: "Subida Segura",
            description: "Tu video se sube encriptado a Google Cloud Platform. Validamos formato (MP4, MOV), tamaño y duración.",
            color: "text-blue-500",
            bg: "bg-blue-500/20",
            border: "border-blue-500/30",
            stepColor: "bg-blue-400"
        },
        {
            icon: Video,
            title: "Video Intelligence",
            description: "La IA analiza cada frame: detecta logos, texto, etiquetas y material inapropiado.",
            color: "text-purple-500",
            bg: "bg-purple-500/20",
            border: "border-purple-500/30",
            stepColor: "bg-purple-400"
        },
        {
            icon: Brain,
            title: "Decisión Inteligente",
            description: "DeepSeek evalúa toda la información y genera una puntuación de confianza.",
            color: "text-yellow-500",
            bg: "bg-yellow-500/20",
            border: "border-yellow-500/30",
            stepColor: "bg-yellow-400"
        },
        {
            icon: CheckCircle,
            title: "Resultado Final",
            description: "Clasificación automática en Aprobado (≥75%) o Revisión (<75%).",
            color: "text-green-500",
            bg: "bg-green-500/20",
            border: "border-green-500/30",
            stepColor: "bg-green-400"
        }
    ];

    useEffect(() => {
        if (isOpen && !isPaused) {
            intervalRef.current = setInterval(() => {
                setCurrentStep((prev) => (prev + 1) % steps.length);
            }, 3500);
        }
        return () => {
            if (intervalRef.current) clearInterval(intervalRef.current);
        };
    }, [isOpen, isPaused]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-300">
            <div className="relative w-full max-w-2xl bg-[#0f0f0f] rounded-2xl border border-white/10 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300 flex flex-col">
                {/* Header */}
                <div className="bg-linear-to-r from-tivit-red to-blue-600 p-8 text-center relative overflow-hidden shrink-0">
                    <div className="relative z-10">
                        <div className="inline-flex items-center justify-center p-3 bg-white/10 rounded-full mb-4 backdrop-blur-md border border-white/20">
                            <Brain size={32} className="text-white" />
                        </div>
                        <h2 className="text-2xl font-bold text-white mb-2">Sistema de Moderación con IA</h2>
                        <p className="text-white/80 max-w-lg mx-auto text-sm">Tecnología de punta para analizar su contenido.</p>
                    </div>
                    {/* Background decoration */}
                    <div className="absolute top-0 left-0 w-full h-full opacity-30 bg-[url('https://www.transparenttextures.com/patterns/cubes.png')]"></div>
                </div>

                <div className="p-8 flex-1 flex flex-col">
                    <h3 className="text-center text-xl font-bold text-white mb-6">¿Cómo funciona?</h3>

                    {/* Slider Content */}
                    <div
                        className="relative min-h-[220px] flex items-center justify-center"
                        onMouseEnter={() => setIsPaused(true)}
                        onMouseLeave={() => setIsPaused(false)}
                    >
                        {steps.map((step, index) => (
                            <div
                                key={index}
                                className={`absolute inset-0 transition-all duration-500 ease-in-out transform flex flex-col items-center justify-center text-center px-4 ${index === currentStep ? 'opacity-100 translate-x-0 scale-100' :
                                    index < currentStep ? 'opacity-0 -translate-x-10 scale-95' : 'opacity-0 translate-x-10 scale-95'
                                    }`}
                                style={{ pointerEvents: index === currentStep ? 'auto' : 'none' }}
                            >
                                <div className={`w-20 h-20 rounded-2xl ${step.bg} ${step.color} flex items-center justify-center mb-6 shadow-lg border border-white/5`}>
                                    <step.icon size={40} />
                                </div>
                                <div className={`inline-block px-3 py-1 rounded-full text-xs font-bold mb-3 border ${step.border} ${step.color} bg-black/50`}>
                                    PASO {index + 1}
                                </div>
                                <h4 className="text-white font-bold text-xl mb-3">{step.title}</h4>
                                <p className="text-gray-400 text-sm leading-relaxed max-w-md">
                                    {step.description}
                                </p>
                            </div>
                        ))}
                    </div>

                    {/* Dots Navigation */}
                    <div className="flex justify-center gap-2 mt-6 mb-8">
                        {steps.map((_, index) => (
                            <button
                                key={index}
                                className={`h-2 rounded-full transition-all duration-300 ${index === currentStep ? 'w-8 bg-tivit-red' : 'w-2 bg-gray-700 hover:bg-gray-600'
                                    }`}
                                onClick={() => {
                                    setCurrentStep(index);
                                    setIsPaused(true);
                                }}
                            />
                        ))}
                    </div>

                    <div className="mt-auto flex justify-center">
                        <Button
                            onClick={onClose}
                            className="bg-white text-black hover:bg-gray-200 px-8 py-6 text-lg font-bold rounded-full w-full sm:w-auto"
                        >
                            ¡Entendido!
                        </Button>
                    </div>
                </div>

                <div className="absolute top-4 right-4 z-50">
                    <button onClick={onClose} className="text-white/50 hover:text-white p-2 bg-black/20 rounded-full backdrop-blur-sm transition-colors">
                        <X size={20} />
                    </button>
                </div>
            </div>
        </div>
    );
}
