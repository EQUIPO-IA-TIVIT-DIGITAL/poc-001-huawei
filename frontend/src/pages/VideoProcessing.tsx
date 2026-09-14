import { useEffect, useState } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { Check, Loader2, AlertCircle, FileVideo, Clock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { Progress } from '../components/ui/progress';
import { apiRequest } from '../lib/api';
import { useTranslation, type TranslationKey } from '../i18n';

interface Phase {
  id: number;
  titleKey: TranslationKey;
  descriptionKey: TranslationKey;
  steps: number[];
  stepLabelKeys: TranslationKey[];
}

const PHASES: Phase[] = [
  {
    id: 1,
    titleKey: 'videoProcessing.phase1Title',
    descriptionKey: 'videoProcessing.phase1Desc',
    steps: [1, 2],
    stepLabelKeys: ['videoProcessing.phase1Step0', 'videoProcessing.phase1Step1'],
  },
  {
    id: 2,
    titleKey: 'videoProcessing.phase2Title',
    descriptionKey: 'videoProcessing.phase2Desc',
    steps: [3, 4, 5],
    stepLabelKeys: [
      'videoProcessing.phase2Step0',
      'videoProcessing.phase2Step1',
      'videoProcessing.phase2Step2',
    ],
  },
  {
    id: 3,
    titleKey: 'videoProcessing.phase3Title',
    descriptionKey: 'videoProcessing.phase3Desc',
    steps: [6],
    stepLabelKeys: ['videoProcessing.phase3Step0'],
  },
  {
    id: 4,
    titleKey: 'videoProcessing.phase4Title',
    descriptionKey: 'videoProcessing.phase4Desc',
    steps: [7, 8],
    stepLabelKeys: ['videoProcessing.phase4Step0', 'videoProcessing.phase4Step1'],
  },
];

interface VideoResult {
  titulo?: string;
  resultado?: string;
  confianza?: number;
  razon?: string;
  video_url?: string;
}

interface StatusResponse {
  status: 'pending' | 'processing' | 'completed' | 'error';
  step?: number;
  stepStatus?: ProcessingState['stepStatus'];
  message?: string;
  details?: unknown;
  error?: unknown;
  final_result?: { video?: VideoResult };
}

interface ProcessingState {
  currentStep: number;
  stepStatus: 'running' | 'success' | 'warning' | 'error' | 'skipped' | 'pending';
  status: 'pending' | 'processing' | 'completed' | 'error';
  message: string;
  details?: unknown;
  videoResult?: VideoResult;
}

export default function VideoProcessing() {
  const { videoId } = useParams({ from: '/app/processing/$videoId' });
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [state, setState] = useState<ProcessingState>({
    currentStep: 0,
    stepStatus: 'pending',
    status: 'pending',
    message: '',
  });

  useEffect(() => {
    setState((s) => ({ ...s, message: t('videoProcessing.initConnection') }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!videoId) return;

    let pollingInterval: ReturnType<typeof setInterval>;
    let isPolling = true;

    const checkStatus = async () => {
      if (!isPolling) return;
      try {
        const response = (await apiRequest(
          `/socio/video/${videoId}/status`,
        )) as StatusResponse;

        if (response.status === 'completed') {
          setState((s) => ({
            ...s,
            status: 'completed',
            currentStep: 8,
            stepStatus: 'success',
            message: response.message ?? '',
            videoResult: response.final_result?.video,
          }));
          isPolling = false;
        } else if (response.status === 'error') {
          setState((s) => ({
            ...s,
            status: 'error',
            stepStatus: 'error',
            message: response.message ?? '',
            details: response.error,
          }));
          isPolling = false;
        } else if (response.status === 'processing') {
          setState((s) => ({
            ...s,
            status: 'processing',
            currentStep: response.step || s.currentStep,
            message: response.message || s.message,
            stepStatus: response.stepStatus || 'running',
            details: response.details,
          }));
        } else if (response.status === 'pending') {
          setState((s) => ({ ...s, status: 'pending', message: t('videoProcessing.init') }));
        }
      } catch {
        // Reintenta en el siguiente ciclo de polling
      }
    };

    const startProcessing = async () => {
      try {
        await apiRequest(`/socio/video/${videoId}/start_processing`, { method: 'POST' });
        checkStatus();
        pollingInterval = setInterval(checkStatus, 2000);
      } catch {
        pollingInterval = setInterval(checkStatus, 2000);
      }
    };

    startProcessing();

    return () => {
      isPolling = false;
      if (pollingInterval) clearInterval(pollingInterval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  const progressPercent = Math.min(Math.round((state.currentStep / 7) * 100), 100);
  const result = state.videoResult?.resultado;

  return (
    <div className="mx-auto w-full max-w-6xl space-y-8 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            {t('videoProcessing.title')}
          </h1>
          <p className="mt-1 text-muted-foreground">{t('videoProcessing.description')}</p>
        </div>
        {state.status === 'completed' && (
          <Button onClick={() => navigate({ to: '/mis-videos' })}>
            {t('videoProcessing.viewVideos')}
          </Button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        {/* Visual Preview / Status Card */}
        <div className="space-y-6 lg:col-span-2">
          <Card className="relative flex aspect-video items-center justify-center overflow-hidden bg-gray-900 shadow-xl">
            {state.videoResult?.video_url && (
              <video
                src={state.videoResult.video_url}
                className="h-full w-full object-contain"
                autoPlay
                muted
                loop
                playsInline
                controls
              />
            )}

            {state.status === 'processing' && (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/50 backdrop-blur-sm">
                <Loader2 className="mb-4 h-8 w-8 animate-spin text-white" aria-hidden="true" />
                <p className="text-lg font-medium tracking-wide text-white">{state.message}</p>
              </div>
            )}

            {state.status === 'completed' ? (
              <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-black/70">
                {result === 'APROBADO' && (
                  <Check className="mb-4 h-20 w-20 text-success" aria-hidden="true" />
                )}
                {result === 'RECHAZADO' && (
                  <AlertCircle className="mb-4 h-20 w-20 text-error" aria-hidden="true" />
                )}
                {result === 'REQUIERE_REVISION' && (
                  <Clock className="mb-4 h-20 w-20 text-warning" aria-hidden="true" />
                )}

                <h3 className="mb-2 text-3xl font-bold text-white">
                  {result === 'APROBADO' && t('videoProcessing.approved')}
                  {result === 'RECHAZADO' && t('videoProcessing.rejected')}
                  {result === 'REQUIERE_REVISION' && t('videoProcessing.needsReview')}
                </h3>
                <p className="text-lg text-gray-300">{state.videoResult?.razon}</p>
              </div>
            ) : state.status === 'error' ? (
              <div className="z-10 p-8 text-center text-error">
                <AlertCircle size={64} className="mx-auto mb-4" aria-hidden="true" />
                <h3 className="mb-2 text-2xl font-bold text-white">
                  {t('videoProcessing.processingError')}
                </h3>
                <p className="text-gray-300">{state.message}</p>
              </div>
            ) : (
              !state.videoResult && (
                <div className="text-center text-gray-500">
                  <FileVideo size={64} className="mx-auto mb-2 opacity-50" aria-hidden="true" />
                  <p>{t('videoProcessing.waitingVideo')}</p>
                </div>
              )
            )}
          </Card>

          {state.videoResult && (
            <Card>
              <CardHeader>
                <CardTitle>{t('videoProcessing.summaryTitle')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 gap-4 text-sm md:grid-cols-3">
                  <div className="rounded-lg bg-muted p-4">
                    <p className="mb-1 text-muted-foreground">
                      {t('videoProcessing.generatedTitle')}
                    </p>
                    <p className="font-semibold text-foreground">{state.videoResult.titulo}</p>
                  </div>
                  <div className="rounded-lg bg-muted p-4">
                    <p className="mb-1 text-muted-foreground">{t('videoProcessing.result')}</p>
                    <Badge
                      variant={
                        result === 'APROBADO'
                          ? 'success'
                          : result === 'RECHAZADO'
                            ? 'destructive'
                            : 'warning'
                      }
                    >
                      {result}
                    </Badge>
                  </div>
                  <div className="rounded-lg bg-muted p-4">
                    <p className="mb-1 text-muted-foreground">{t('videoProcessing.confidence')}</p>
                    <p className="font-semibold text-foreground">
                      {((state.videoResult.confianza ?? 0) * 100).toFixed(1)}%
                    </p>
                  </div>
                  {state.videoResult.razon && (
                    <div className="md:col-span-3">
                      <Alert variant="info">
                        <AlertTitle>{t('videoProcessing.decisionDetail')}</AlertTitle>
                        <AlertDescription>{state.videoResult.razon}</AlertDescription>
                      </Alert>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Phases List */}
        <Card className="h-fit lg:sticky lg:top-6">
          <CardHeader className="border-b border-border">
            <CardTitle>{t('videoProcessing.stagesTitle')}</CardTitle>
            <p className="text-sm text-muted-foreground">
              {t('videoProcessing.overallProgress', { percent: progressPercent })}
            </p>
            <Progress
              value={progressPercent}
              className="mt-2"
              aria-label={t('videoProcessing.overallProgress', { percent: progressPercent })}
            />
          </CardHeader>
          <CardContent className="space-y-6 pt-6">
            {PHASES.map((phase, index) => {
              const currentStep = state.currentStep;
              const isPhaseComplete =
                phase.steps.every((s) => s < currentStep) || state.status === 'completed';
              const isPhaseActive =
                phase.steps.includes(currentStep) && state.status === 'processing';
              const isPhasePending = !isPhaseComplete && !isPhaseActive;
              const isPhaseError = state.status === 'error' && phase.steps.includes(currentStep);

              return (
                <div
                  key={phase.id}
                  className={`relative ${index !== PHASES.length - 1 ? 'pb-8' : ''}`}
                >
                  {index !== PHASES.length - 1 && (
                    <div
                      className={`absolute bottom-0 left-4 top-10 z-0 w-0.5 ${
                        isPhaseComplete ? 'bg-success' : 'bg-border'
                      }`}
                      aria-hidden="true"
                    />
                  )}

                  <div className="relative z-10">
                    <div className="flex items-start gap-4">
                      <div
                        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 transition-all duration-300 ${
                          isPhaseComplete
                            ? 'border-success bg-success text-success-foreground'
                            : isPhaseError
                              ? 'border-error bg-error text-error-foreground'
                              : isPhaseActive
                                ? 'border-primary bg-card text-primary'
                                : 'border-border bg-card text-muted-foreground'
                        }`}
                      >
                        {isPhaseComplete ? (
                          <Check size={16} strokeWidth={3} aria-hidden="true" />
                        ) : isPhaseError ? (
                          <AlertCircle size={16} aria-hidden="true" />
                        ) : isPhaseActive ? (
                          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                        ) : (
                          <span className="text-sm font-bold">{phase.id}</span>
                        )}
                      </div>

                      <div className="flex-1 pt-1">
                        <h3
                          className={`text-base font-bold ${
                            isPhaseActive
                              ? 'text-primary'
                              : isPhaseComplete
                                ? 'text-foreground'
                                : 'text-muted-foreground'
                          }`}
                        >
                          {t('videoProcessing.title')} {index + 1} – {t(phase.titleKey)}
                        </h3>
                        <p className="mb-3 mt-1 text-sm text-muted-foreground">
                          {t(phase.descriptionKey)}
                        </p>

                        <div className="space-y-2 border-l-2 border-border/60 pl-2">
                          {phase.steps.map((stepId, i) => {
                            const label = t(phase.stepLabelKeys[i]);
                            const isStepDone =
                              currentStep > stepId || state.status === 'completed';
                            const isStepCurrent =
                              currentStep === stepId && state.status === 'processing';

                            return (
                              <div key={stepId} className="flex items-center gap-2.5">
                                <div
                                  className={`h-2 w-2 rounded-full transition-colors duration-300 ${
                                    isStepDone
                                      ? 'bg-success'
                                      : isStepCurrent
                                        ? 'animate-pulse bg-primary'
                                        : 'bg-border'
                                  }`}
                                  aria-hidden="true"
                                />
                                <span
                                  className={`text-xs font-medium transition-colors duration-300 ${
                                    isStepDone
                                      ? 'text-success'
                                      : isStepCurrent
                                        ? 'text-primary'
                                        : 'text-muted-foreground'
                                  }`}
                                >
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
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
