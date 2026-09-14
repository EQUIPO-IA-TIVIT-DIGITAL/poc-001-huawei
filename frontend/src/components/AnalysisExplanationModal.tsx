import { useState, useEffect, useRef } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Upload, Video, Brain, CheckCircle } from 'lucide-react';
import { Button } from './ui/button';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from './ui/dialog';
import { useTranslation } from '../i18n';
import type { TranslationKey } from '../i18n/es';

interface AnalysisExplanationModalProps {
    isOpen: boolean;
    onClose: () => void;
}

interface ExplanationStep {
    icon: LucideIcon;
    titleKey: TranslationKey;
    descriptionKey: TranslationKey;
    iconClassName: string;
    surfaceClassName: string;
    badgeClassName: string;
    dotClassName: string;
}

const STEPS: ExplanationStep[] = [
    {
        icon: Upload,
        titleKey: 'analysisExplanation.uploadTitle',
        descriptionKey: 'analysisExplanation.uploadDesc',
        iconClassName: 'text-info',
        surfaceClassName: 'bg-info-surface border-info-border',
        badgeClassName: 'border-info-border text-info bg-info-surface',
        dotClassName: 'bg-info',
    },
    {
        icon: Video,
        titleKey: 'analysisExplanation.videoTitle',
        descriptionKey: 'analysisExplanation.videoDesc',
        iconClassName: 'text-primary',
        surfaceClassName: 'bg-brand-soft border-brand-border',
        badgeClassName: 'border-brand-border text-primary bg-brand-soft',
        dotClassName: 'bg-primary',
    },
    {
        icon: Brain,
        titleKey: 'analysisExplanation.decisionTitle',
        descriptionKey: 'analysisExplanation.decisionDesc',
        iconClassName: 'text-warning',
        surfaceClassName: 'bg-warning-surface border-warning-border',
        badgeClassName: 'border-warning-border text-warning bg-warning-surface',
        dotClassName: 'bg-warning',
    },
    {
        icon: CheckCircle,
        titleKey: 'analysisExplanation.resultTitle',
        descriptionKey: 'analysisExplanation.resultDesc',
        iconClassName: 'text-success',
        surfaceClassName: 'bg-success-surface border-success-border',
        badgeClassName: 'border-success-border text-success bg-success-surface',
        dotClassName: 'bg-success',
    },
];

export function AnalysisExplanationModal({ isOpen, onClose }: AnalysisExplanationModalProps) {
    const { t } = useTranslation();
    const [currentStep, setCurrentStep] = useState(0);
    const [isPaused, setIsPaused] = useState(false);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    useEffect(() => {
        if (isOpen && !isPaused) {
            intervalRef.current = setInterval(() => {
                setCurrentStep((prev) => (prev + 1) % STEPS.length);
            }, 3500);
        }
        return () => {
            if (intervalRef.current) clearInterval(intervalRef.current);
        };
    }, [isOpen, isPaused]);

    return (
        <Dialog
            open={isOpen}
            onOpenChange={(nextOpen) => {
                if (!nextOpen) onClose();
            }}
        >
            <DialogContent className="max-w-2xl gap-0 overflow-hidden p-0">
                <DialogHeader className="relative shrink-0 overflow-hidden bg-gradient-to-br from-primary to-brand-hover p-8 text-center">
                    <div className="relative z-10 flex flex-col items-center">
                        <div className="mb-4 inline-flex items-center justify-center rounded-full border border-white/20 bg-white/10 p-3 backdrop-blur">
                            <Brain size={32} className="text-primary-foreground" aria-hidden="true" />
                        </div>
                        <DialogTitle className="text-2xl font-bold text-primary-foreground">
                            {t('analysisExplanation.title')}
                        </DialogTitle>
                        <DialogDescription className="mt-2 max-w-lg text-sm text-primary-foreground/80">
                            {t('analysisExplanation.subtitle')}
                        </DialogDescription>
                    </div>
                </DialogHeader>

                <div className="flex flex-1 flex-col p-8">
                    <h3 className="mb-6 text-center text-xl font-bold text-foreground">
                        {t('analysisExplanation.howItWorks')}
                    </h3>

                    <div
                        className="relative flex min-h-[220px] items-center justify-center"
                        onMouseEnter={() => setIsPaused(true)}
                        onMouseLeave={() => setIsPaused(false)}
                    >
                        {STEPS.map((step, index) => {
                            const isActive = index === currentStep;
                            const isPast = index < currentStep;
                            const Icon = step.icon;
                            return (
                                <div
                                    key={step.titleKey}
                                    aria-hidden={!isActive}
                                    className={`absolute inset-0 flex flex-col items-center justify-center px-4 text-center transition-all duration-500 ease-in-out ${
                                        isActive
                                            ? 'translate-x-0 scale-100 opacity-100'
                                            : isPast
                                                ? '-translate-x-10 scale-95 opacity-0'
                                                : 'translate-x-10 scale-95 opacity-0'
                                    }`}
                                    style={{ pointerEvents: isActive ? 'auto' : 'none' }}
                                >
                                    <div
                                        className={`mb-6 flex h-20 w-20 items-center justify-center rounded-2xl border shadow-sm ${step.surfaceClassName} ${step.iconClassName}`}
                                    >
                                        <Icon size={40} aria-hidden="true" />
                                    </div>
                                    <div
                                        className={`mb-3 inline-block rounded-full border px-3 py-1 text-xs font-bold ${step.badgeClassName}`}
                                    >
                                        {t('analysisExplanation.stepLabel', { number: index + 1 })}
                                    </div>
                                    <h4 className="mb-3 text-xl font-bold text-foreground">
                                        {t(step.titleKey)}
                                    </h4>
                                    <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
                                        {t(step.descriptionKey)}
                                    </p>
                                </div>
                            );
                        })}
                    </div>

                    <div
                        className="mb-8 mt-6 flex justify-center gap-2"
                        role="tablist"
                        aria-label={t('analysisExplanation.howItWorks')}
                    >
                        {STEPS.map((step, index) => (
                            <button
                                key={step.titleKey}
                                type="button"
                                role="tab"
                                aria-selected={index === currentStep}
                                aria-label={t('analysisExplanation.goToStep', { number: index + 1 })}
                                className={`h-2 rounded-full transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
                                    index === currentStep
                                        ? `w-8 ${step.dotClassName}`
                                        : 'w-2 bg-muted-foreground/30 hover:bg-muted-foreground/50'
                                }`}
                                onClick={() => {
                                    setCurrentStep(index);
                                    setIsPaused(true);
                                }}
                            />
                        ))}
                    </div>

                    <div className="mt-auto flex justify-center">
                        <Button onClick={onClose} size="lg" className="w-full sm:w-auto">
                            {t('analysisExplanation.understand')}
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
