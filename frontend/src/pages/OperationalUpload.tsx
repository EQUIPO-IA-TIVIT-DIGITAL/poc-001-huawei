import { useState, useEffect } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import {
  operationalVideoService,
  OperationalAnalysisType,
  TimeEstimate,
} from '../services/operationalVideoService';
import {
  videoCompressionService,
  type CompressionProgress,
} from '../services/videoCompressionService';
import { toast } from 'sonner';
import {
  Upload,
  Activity,
  AlertCircle,
  CheckCircle,
  Loader2,
  Clock,
  BarChart3,
} from 'lucide-react';
import { PageContainer } from '../components/ui/page-container';
import { PageHeader } from '../components/ui/page-header';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Checkbox } from '../components/ui/checkbox';
import { Badge } from '../components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { Progress } from '../components/ui/progress';
import { useTranslation } from '../i18n';

type UploadStatus =
  | 'idle'
  | 'loading-ffmpeg'
  | 'compressing'
  | 'uploading'
  | 'processing'
  | 'completed';

export default function OperationalUpload() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const search = useSearch({ strict: false }) as { analysisType?: string };

  const [types, setTypes] = useState<Record<string, OperationalAnalysisType>>({});
  const [selectedType, setSelectedType] = useState<string>('');
  const [customContext, setCustomContext] = useState('');
  const [maxContextLength] = useState(2000);

  const [file, setFile] = useState<File | null>(null);
  const [enableCompression, setEnableCompression] = useState(true);

  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle');
  const [compressionProgress, setCompressionProgress] = useState<CompressionProgress | null>(null);
  const [originalSize, setOriginalSize] = useState(0);
  const [compressedSize, setCompressedSize] = useState(0);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [timeEstimate, setTimeEstimate] = useState<TimeEstimate | null>(null);

  useEffect(() => {
    operationalVideoService
      .listarTipos()
      .then(setTypes)
      .catch(() => {
        toast.error(t('operationalUpload.toastTypesError'));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!search.analysisType || !types || Object.keys(types).length === 0) return;
    if (types[search.analysisType]) {
      setSelectedType(search.analysisType);
    }
  }, [search.analysisType, types]);

  useEffect(() => {
    if (selectedType && file) {
      operationalVideoService
        .estimarTiempo({
          analysis_type: selectedType,
          file_size_mb: file.size / (1024 * 1024),
        })
        .then(setTimeEstimate)
        .catch(() => setTimeEstimate(null));
    } else {
      setTimeEstimate(null);
    }
  }, [selectedType, file]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      if (!selectedFile.type.startsWith('video/')) {
        toast.error(t('operationalUpload.toastInvalid'));
        return;
      }
      if (selectedFile.size > 100 * 1024 * 1024 * 1024) {
        toast.error(t('operationalUpload.toastTooLarge'));
        return;
      }
      if (selectedFile.size > 50 * 1024 * 1024 * 1024) {
        setEnableCompression(false);
      }
      setFile(selectedFile);
      toast.success(t('operationalUpload.toastSelected', { size: formatFileSize(selectedFile.size) }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!file) {
      toast.error(t('operationalUpload.toastNoFile'));
      return;
    }
    if (!selectedType) {
      toast.error(t('operationalUpload.toastNoType'));
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setOriginalSize(file.size);
    setSubmitError(null);

    try {
      let fileToUpload = file;

      if (enableCompression && file.size > 500 * 1024 * 1024) {
        setUploadStatus('loading-ffmpeg');
        await videoCompressionService.initialize((progress) => {
          setCompressionProgress(progress);
        });

        setUploadStatus('compressing');
        toast.info(t('operationalUpload.toastCompressing'));
        const result = await videoCompressionService.compressVideo(file, (progress) => {
          setCompressionProgress(progress);
        });
        fileToUpload = result.compressedFile;
        setCompressedSize(result.compressedSize);
        toast.success(
          t('operationalUpload.toastCompressed', { percent: result.reductionPercent.toFixed(1) }),
        );
      } else {
        setCompressedSize(file.size);
      }

      setUploadStatus('uploading');

      toast.info(t('operationalUpload.toastInit'));
      const initResponse = await operationalVideoService.iniciarUpload({
        filename: fileToUpload.name,
        content_type: fileToUpload.type,
        analysis_type: selectedType,
        custom_context: customContext,
      });

      if (!initResponse.success) {
        throw new Error(initResponse.error || t('operationalUpload.initError'));
      }

      toast.success(t('operationalUpload.toastInitSuccess'));

      toast.info(t('operationalUpload.toastUploading'));
      await operationalVideoService.subirArchivoProxy(
        initResponse.analysis_id,
        fileToUpload,
        (percentage) => setUploadProgress(percentage),
      );

      toast.success(t('operationalUpload.toastUploaded'));
      setUploadStatus('processing');

      toast.info(t('operationalUpload.toastAnalyzing'));
      const completeResponse = await operationalVideoService.completarUpload(
        initResponse.analysis_id,
      );

      if (completeResponse.success) {
        setUploadStatus('completed');
        toast.success(t('operationalUpload.toastCompleted'));
      } else {
        toast.warning(t('operationalUpload.toastAnalyzeWarn'));
      }

      setTimeout(() => {
        navigate({ to: '/operational' });
      }, 2000);
    } catch (error) {
      const msg = getErrorText(error, t('operationalUpload.error'));
      toast.error(msg);
      setSubmitError(msg);
      setUploading(false);
      setUploadStatus('idle');
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const selectedTypeInfo = selectedType ? types[selectedType] : null;
  const contextOverLimit = customContext.length > maxContextLength;

  const hasCompression = enableCompression && !!file && file.size > 500 * 1024 * 1024;
  const allProgressSteps: { key: UploadStatus; label: string }[] = hasCompression
    ? [
        { key: 'loading-ffmpeg', label: t('operationalUpload.stepPreparing') },
        { key: 'compressing', label: t('operationalUpload.stepCompressing') },
        { key: 'uploading', label: t('operationalUpload.stepUploading') },
        { key: 'processing', label: t('operationalUpload.stepProcessing') },
        { key: 'completed', label: t('operationalUpload.stepCompleted') },
      ]
    : [
        { key: 'uploading', label: t('operationalUpload.stepUploading') },
        { key: 'processing', label: t('operationalUpload.stepProcessing') },
        { key: 'completed', label: t('operationalUpload.stepCompleted') },
      ];
  const progressCurrentIdx = allProgressSteps.findIndex((s) => s.key === uploadStatus);
  const progressPct =
    uploadStatus === 'loading-ffmpeg'
      ? 5
      : uploadStatus === 'compressing'
        ? 5 + (compressionProgress?.percent ?? 0) * 0.25
        : uploadStatus === 'uploading'
          ? (hasCompression ? 30 : 0) + uploadProgress * (hasCompression ? 0.5 : 0.8)
          : uploadStatus === 'processing'
            ? 85
            : uploadStatus === 'completed'
              ? 100
              : 0;
  const progressLabel =
    uploadStatus === 'loading-ffmpeg'
      ? t('operationalUpload.progressLoading')
      : uploadStatus === 'compressing'
        ? compressionProgress?.message ?? t('operationalUpload.progressCompressing')
        : uploadStatus === 'uploading'
          ? t('operationalUpload.progressUploading', { percent: uploadProgress })
          : uploadStatus === 'processing'
            ? t('operationalUpload.progressProcessing')
            : uploadStatus === 'completed'
              ? t('operationalUpload.progressCompleted')
              : '';

  const stepComplete = (idx: number) =>
    idx === 0 ? !!selectedType : idx === 1 ? true : idx === 2 ? !!file : false;

  return (
    <PageContainer className="max-w-4xl pb-16">
      <PageHeader
        icon={Activity}
        title={t('operationalUpload.title')}
        description={t('operationalUpload.description')}
      />

      {/* Step indicator */}
      <Card>
        <CardContent className="flex items-center justify-between p-4">
          {[
            t('operationalUpload.stepType'),
            t('operationalUpload.stepContext'),
            t('operationalUpload.stepVideo'),
            t('operationalUpload.stepConfirm'),
          ].map((step, idx) => {
            const isComplete = stepComplete(idx);
            return (
              <div key={step} className="flex items-center gap-2">
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium transition-colors ${
                    isComplete ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {isComplete ? (
                    <CheckCircle className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    idx + 1
                  )}
                </div>
                <span
                  className={`hidden text-sm md:inline ${
                    isComplete ? 'font-medium text-primary' : 'text-muted-foreground'
                  }`}
                >
                  {step}
                </span>
                {idx < 3 && (
                  <div
                    className={`h-0.5 w-8 lg:w-16 ${isComplete ? 'bg-primary' : 'bg-border'}`}
                    aria-hidden="true"
                  />
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Card variant="elevated">
        <CardContent className="p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            {uploadStatus === 'completed' && (
              <Alert variant="success">
                <CheckCircle aria-hidden="true" />
                <AlertTitle>{t('operationalUpload.successBannerTitle')}</AlertTitle>
                <AlertDescription>{t('operationalUpload.successBannerDesc')}</AlertDescription>
              </Alert>
            )}

            {/* Tipo de análisis */}
            <div>
              <Label className="mb-2 block">{t('operationalUpload.typeLabel')} *</Label>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                {Object.entries(types).map(([key, info]) => (
                  <button
                    key={key}
                    type="button"
                    disabled={uploading}
                    onClick={() => setSelectedType(key)}
                    aria-pressed={selectedType === key}
                    className={`rounded-lg border-2 p-4 text-center transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      selectedType === key
                        ? 'border-primary bg-brand-soft'
                        : 'border-border hover:border-brand-border hover:bg-brand-soft/40'
                    } ${uploading ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
                  >
                    <Activity
                      className="mx-auto mb-1 h-6 w-6 text-primary"
                      aria-hidden="true"
                    />
                    <div className="text-sm font-semibold text-foreground">{info.name}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{info.description}</div>
                  </button>
                ))}
              </div>

              {selectedTypeInfo &&
                selectedTypeInfo.key_metrics &&
                selectedTypeInfo.key_metrics.length > 0 && (
                  <Alert className="mt-4">
                    <BarChart3 aria-hidden="true" />
                    <AlertDescription>
                      <p className="mb-2 font-medium">{t('operationalUpload.metricsTitle')}</p>
                      <div className="flex flex-wrap gap-2">
                        {selectedTypeInfo.key_metrics.map((metric: string, i: number) => (
                          <Badge key={i} variant="outline">
                            {metric}
                          </Badge>
                        ))}
                      </div>
                    </AlertDescription>
                  </Alert>
                )}
            </div>

            {/* Contexto personalizado */}
            <div>
              <Label htmlFor="op-context" className="mb-2 block">
                {t('operationalUpload.contextLabel')}
              </Label>
              <Textarea
                id="op-context"
                value={customContext}
                onChange={(e) => setCustomContext(e.target.value)}
                disabled={uploading}
                rows={3}
                maxLength={maxContextLength + 100}
                placeholder={t('operationalUpload.contextPlaceholder')}
                invalid={contextOverLimit}
              />
              <div className="mt-1 flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  {t('operationalUpload.contextHint')}
                </p>
                <span
                  className={`font-mono text-xs ${
                    contextOverLimit
                      ? 'font-semibold text-error'
                      : customContext.length > maxContextLength * 0.8
                        ? 'text-warning'
                        : 'text-muted-foreground'
                  }`}
                >
                  {customContext.length}/{maxContextLength}
                </span>
              </div>
              {contextOverLimit && (
                <p className="mt-1 text-xs text-error">
                  {t('operationalUpload.contextOverLimit', { max: maxContextLength })}
                </p>
              )}
            </div>

            {/* Selección de archivo */}
            <div>
              <Label className="mb-2 flex items-center gap-2">
                <Upload className="h-4 w-4" aria-hidden="true" />
                {t('operationalUpload.fileLabel')} *
              </Label>
              <div className="rounded-lg border-2 border-dashed border-border p-8 text-center transition-colors hover:border-brand-border">
                <input
                  type="file"
                  accept="video/*"
                  onChange={handleFileChange}
                  className="hidden"
                  id="op-video-file"
                  disabled={uploading}
                />
                <label
                  htmlFor="op-video-file"
                  className={`cursor-pointer ${uploading ? 'cursor-not-allowed opacity-50' : ''}`}
                >
                  <Upload
                    className="mx-auto mb-3 h-12 w-12 text-muted-foreground"
                    aria-hidden="true"
                  />
                  {file ? (
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-foreground">{file.name}</p>
                      <p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-sm text-muted-foreground">
                        {t('operationalUpload.selectPrompt')}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {t('operationalUpload.selectHint')}
                      </p>
                    </div>
                  )}
                </label>
              </div>
            </div>

            {/* Opción de compresión */}
            {file && file.size > 500 * 1024 * 1024 && (
              <Alert variant="warning">
                <AlertTitle className="flex items-center justify-between gap-4">
                  <span>{t('operationalUpload.largeTitle')}</span>
                  <label className="flex cursor-pointer items-center gap-2">
                    <Checkbox
                      checked={enableCompression}
                      onCheckedChange={(checked) => setEnableCompression(checked === true)}
                      disabled={uploading}
                      aria-label={t('operationalUpload.compressLabel')}
                    />
                    <span className="text-sm font-medium text-foreground">
                      {t('operationalUpload.compressLabel')}
                    </span>
                  </label>
                </AlertTitle>
              </Alert>
            )}

            {/* Time Estimation */}
            {timeEstimate && (
              <Alert>
                <Clock aria-hidden="true" />
                <AlertDescription>
                  <p className="mb-2 text-sm font-semibold text-foreground">
                    {t('operationalUpload.timeTitle')}
                  </p>
                  <div className="grid grid-cols-3 gap-3">
                    <div className="rounded-lg bg-card/70 p-2 text-center">
                      <p className="text-xl font-bold text-primary">
                        {timeEstimate.estimated_range.min_minutes.toFixed(0)}–
                        {timeEstimate.estimated_range.max_minutes.toFixed(0)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {t('operationalUpload.timeMinutes')}
                      </p>
                    </div>
                    <div className="rounded-lg bg-card/70 p-2 text-center">
                      <p className="text-lg font-semibold text-foreground">
                        {timeEstimate.breakdown.upload_minutes.toFixed(1)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {t('operationalUpload.timeUpload')}
                      </p>
                    </div>
                    <div className="rounded-lg bg-card/70 p-2 text-center">
                      <p className="text-lg font-semibold text-foreground">
                        {timeEstimate.breakdown.analysis_minutes.toFixed(1)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {t('operationalUpload.timeAnalysis')}
                      </p>
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-primary">{t('operationalUpload.timeNote')}</p>
                </AlertDescription>
              </Alert>
            )}

            {/* Progreso unificado */}
            {uploading && (
              <div className="space-y-4 rounded-xl border border-border bg-muted/50 p-5">
                <div className="flex items-center justify-between">
                  {allProgressSteps.map((step, idx) => {
                    const done = idx < progressCurrentIdx;
                    const active = idx === progressCurrentIdx;
                    return (
                      <div key={step.key} className="flex flex-1 flex-col items-center gap-1">
                        <div
                          className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                            done
                              ? 'bg-success text-success-foreground'
                              : active
                                ? 'bg-primary text-primary-foreground'
                                : 'bg-muted text-muted-foreground'
                          }`}
                        >
                          {done ? (
                            <CheckCircle className="h-4 w-4" aria-hidden="true" />
                          ) : active ? (
                            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                          ) : (
                            idx + 1
                          )}
                        </div>
                        <span
                          className={`hidden text-center text-xs leading-tight sm:block ${
                            done
                              ? 'font-medium text-success'
                              : active
                                ? 'font-semibold text-primary'
                                : 'text-muted-foreground'
                          }`}
                        >
                          {step.label}
                        </span>
                      </div>
                    );
                  })}
                </div>

                <div aria-live="polite">
                  <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">{progressLabel}</span>
                    <span className="font-mono font-semibold">{Math.round(progressPct)}%</span>
                  </div>
                  <Progress
                    value={progressPct}
                    indicatorClassName={uploadStatus === 'completed' ? 'bg-success' : undefined}
                    aria-label={progressLabel}
                  />
                </div>

                {originalSize > 0 && compressedSize > 0 && compressedSize < originalSize && (
                  <p className="text-center text-xs text-success">
                    {t('operationalUpload.savings', {
                      mb: ((originalSize - compressedSize) / (1024 * 1024)).toFixed(1),
                    })}
                  </p>
                )}
              </div>
            )}

            {submitError && (
              <Alert variant="error">
                <AlertCircle aria-hidden="true" />
                <AlertTitle>{t('operationalUpload.errorTitle')}</AlertTitle>
                <AlertDescription>{submitError}</AlertDescription>
              </Alert>
            )}

            {uploadStatus === 'completed' && (
              <Alert variant="success">
                <CheckCircle aria-hidden="true" />
                <AlertTitle>{t('operationalUpload.successTitle')}</AlertTitle>
                <AlertDescription>{t('operationalUpload.successDesc')}</AlertDescription>
              </Alert>
            )}

            {/* Botones */}
            <div className="flex gap-4 pt-4">
              <Button
                type="submit"
                variant={uploadStatus === 'completed' ? 'success' : 'default'}
                disabled={uploading || !file || !selectedType || contextOverLimit}
                loading={uploading && uploadStatus !== 'completed'}
                className="flex-1"
              >
                {uploadStatus === 'completed'
                  ? t('operationalUpload.completed')
                  : uploadStatus === 'idle'
                    ? t('operationalUpload.submit')
                    : uploadStatus === 'loading-ffmpeg'
                      ? t('operationalUpload.loadingFfmpeg')
                      : uploadStatus === 'compressing'
                        ? t('operationalUpload.compressing')
                        : uploadStatus === 'uploading'
                          ? t('operationalUpload.uploading')
                          : t('operationalUpload.processing')}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate({ to: '/operational' })}
                disabled={uploading}
              >
                {t('operationalUpload.cancel')}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <h3 className="mb-2 font-semibold text-foreground">{t('operationalUpload.infoTitle')}</h3>
          <ul className="ml-5 list-disc space-y-1 text-sm text-muted-foreground">
            <li>{t('operationalUpload.info1')}</li>
            <li>{t('operationalUpload.info2')}</li>
            <li>{t('operationalUpload.info3')}</li>
            <li>{t('operationalUpload.info4')}</li>
          </ul>
        </CardContent>
      </Card>
    </PageContainer>
  );
}

function getErrorText(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  if (error && typeof error === 'object' && 'message' in error) {
    return String((error as { message: unknown }).message);
  }
  return fallback;
}
