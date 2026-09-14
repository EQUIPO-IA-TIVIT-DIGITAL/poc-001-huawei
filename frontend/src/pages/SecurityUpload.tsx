import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { securityVideoService } from '../services/securityVideoService';
import {
  videoCompressionService,
  type CompressionProgress,
} from '../services/videoCompressionService';
import { toast } from 'sonner';
import {
  Upload,
  Video,
  CheckCircle,
  Loader2,
  Info,
  TriangleAlert,
} from 'lucide-react';
import { PageContainer } from '../components/ui/page-container';
import { PageHeader } from '../components/ui/page-header';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Label } from '../components/ui/label';
import { Checkbox } from '../components/ui/checkbox';
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

const LARGE_VIDEO_THRESHOLD = 50 * 1024 * 1024 * 1024; // 50GB
const MAX_SIZE = 100 * 1024 * 1024 * 1024; // 100GB

export default function SecurityUpload() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [file, setFile] = useState<File | null>(null);
  const [enableCompression, setEnableCompression] = useState(true);

  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentVideoId, setCurrentVideoId] = useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle');

  const [compressionProgress, setCompressionProgress] = useState<CompressionProgress | null>(null);
  const [originalSize, setOriginalSize] = useState<number>(0);
  const [compressedSize, setCompressedSize] = useState<number>(0);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];

      if (!selectedFile.type.startsWith('video/')) {
        toast.error(t('securityUpload.toastInvalid'));
        return;
      }

      if (selectedFile.size > MAX_SIZE) {
        toast.error(t('securityUpload.toastTooLarge'));
        return;
      }

      if (selectedFile.size > LARGE_VIDEO_THRESHOLD) {
        toast.warning(t('securityUpload.toastLargeWarning'), { duration: 8000 });
        setEnableCompression(false);
      }

      setFile(selectedFile);

      const sizeGB = selectedFile.size / (1024 * 1024 * 1024);
      const sizeDisplay =
        sizeGB >= 1
          ? `${sizeGB.toFixed(2)} GB`
          : `${(selectedFile.size / (1024 * 1024)).toFixed(0)} MB`;

      toast.success(t('securityUpload.toastSelected', { size: sizeDisplay }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!file) {
      toast.error(t('securityUpload.toastNoFile'));
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setOriginalSize(file.size);

    try {
      let fileToUpload = file;

      if (enableCompression) {
        const COMPRESS_THRESHOLD = 500 * 1024 * 1024;
        const shouldCompress = file.size > COMPRESS_THRESHOLD;

        if (shouldCompress) {
          toast.info(t('securityUpload.toastCompressStart'));
          setUploadStatus('loading-ffmpeg');

          await videoCompressionService.initialize((progress) => {
            setCompressionProgress(progress);
            if (progress.phase === 'loading') {
              setUploadStatus('loading-ffmpeg');
            }
          });

          setUploadStatus('compressing');
          toast.info(t('securityUpload.toastCompressing'));

          const result = await videoCompressionService.compressVideo(file, (progress) => {
            setCompressionProgress(progress);
          });

          fileToUpload = result.compressedFile;
          setCompressedSize(result.compressedSize);

          const reductionMB = (result.originalSize - result.compressedSize) / (1024 * 1024);
          toast.success(
            t('securityUpload.toastCompressed', {
              percent: result.reductionPercent.toFixed(1),
              mb: reductionMB.toFixed(1),
            }),
            { duration: 5000 },
          );
        } else {
          toast.info(t('securityUpload.toastNoCompress'));
          setCompressedSize(file.size);
        }
      } else {
        setCompressedSize(file.size);
      }

      setUploadStatus('uploading');

      toast.info(t('securityUpload.toastInit'));

      const initResponse = await securityVideoService.iniciarUpload({
        filename: fileToUpload.name,
        content_type: fileToUpload.type,
      });

      if (!initResponse.success) {
        throw new Error(initResponse.error || t('securityUpload.initError'));
      }

      setCurrentVideoId(initResponse.video_id);
      toast.success(t('securityUpload.toastInitSuccess'));

      toast.info(t('securityUpload.toastUploading'));

      await securityVideoService.subirArchivoProxy(
        initResponse.video_id,
        fileToUpload,
        (percentage) => {
          setUploadProgress(percentage);
        },
      );

      toast.success(t('securityUpload.toastUploaded'));
      setUploadStatus('processing');

      toast.info(t('securityUpload.toastAnalyzing'));

      const completeResponse = await securityVideoService.completarUpload(initResponse.video_id);

      if (completeResponse.success) {
        setUploadStatus('completed');
        toast.success(t('securityUpload.toastCompleted'));
      } else {
        toast.warning(t('securityUpload.toastAnalysisWarn'));
      }

      setTimeout(() => {
        navigate({ to: '/security' });
      }, 2000);
    } catch (error) {
      toast.error(getErrorText(error, t('securityUpload.error')));
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

  const isVeryLarge = !!file && file.size > LARGE_VIDEO_THRESHOLD;

  const statusButtonContent = () => {
    switch (uploadStatus) {
      case 'loading-ffmpeg':
        return (
          <>
            <Loader2 className="animate-spin" aria-hidden="true" />
            {t('securityUpload.loadingFfmpeg')}
          </>
        );
      case 'compressing':
        return (
          <>
            <Loader2 className="animate-spin" aria-hidden="true" />
            {t('securityUpload.compressing')}
          </>
        );
      case 'uploading':
        return (
          <>
            <Loader2 className="animate-spin" aria-hidden="true" />
            {t('securityUpload.uploading')}
          </>
        );
      case 'processing':
        return (
          <>
            <Loader2 className="animate-spin" aria-hidden="true" />
            {t('securityUpload.processing')}
          </>
        );
      case 'completed':
        return (
          <>
            <CheckCircle aria-hidden="true" />
            {t('securityUpload.completed')}
          </>
        );
      default:
        return t('securityUpload.submit');
    }
  };

  return (
    <PageContainer className="max-w-4xl pb-16">
      <PageHeader
        icon={Video}
        title={t('securityUpload.title')}
        description={t('securityUpload.description')}
      />

      {/* Información del proceso */}
      <Alert>
        <Info aria-hidden="true" />
        <AlertTitle>{t('securityUpload.processTitle')}</AlertTitle>
        <AlertDescription>
          <ol className="ml-4 list-decimal space-y-1">
            <li>{t('securityUpload.processStep1')}</li>
            <li>{t('securityUpload.processStep2')}</li>
            <li>{t('securityUpload.processStep3')}</li>
          </ol>
          <p className="mt-2 text-xs">{t('securityUpload.processTime')}</p>
          <p className="mt-2 text-xs">{t('securityUpload.processNotify')}</p>
        </AlertDescription>
      </Alert>

      <Card variant="elevated">
        <CardContent className="p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            {uploadStatus === 'completed' && (
              <Alert variant="success">
                <CheckCircle aria-hidden="true" />
                <AlertTitle>{t('securityUpload.successBannerTitle')}</AlertTitle>
                <AlertDescription>{t('securityUpload.successBannerDesc')}</AlertDescription>
              </Alert>
            )}

            {/* Selección de archivo */}
            <div>
              <Label className="mb-2 flex items-center gap-2">
                <Upload className="h-4 w-4" aria-hidden="true" />
                {t('securityUpload.fileLabel')}
              </Label>
              <div className="rounded-lg border-2 border-dashed border-border p-8 text-center transition-colors hover:border-brand-border">
                <input
                  type="file"
                  accept="video/*"
                  onChange={handleFileChange}
                  className="hidden"
                  id="security-video-file"
                  disabled={uploading}
                />
                <label
                  htmlFor="security-video-file"
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
                        {t('securityUpload.selectPrompt')}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {t('securityUpload.selectHint')}
                      </p>
                    </div>
                  )}
                </label>
              </div>
            </div>

            {/* Opción de compresión */}
            {file && file.size > 500 * 1024 * 1024 && (
              <Alert variant={isVeryLarge ? 'error' : 'warning'}>
                <TriangleAlert aria-hidden="true" />
                <AlertTitle className="flex items-center justify-between gap-4">
                  <span>
                    {isVeryLarge
                      ? t('securityUpload.veryLargeTitle')
                      : t('securityUpload.largeTitle')}
                  </span>
                  <label className="flex cursor-pointer items-center gap-2">
                    <Checkbox
                      checked={enableCompression}
                      onCheckedChange={(checked) => setEnableCompression(checked === true)}
                      disabled={uploading}
                      aria-label={t('securityUpload.compressLabel')}
                    />
                    <span className="text-sm font-medium text-foreground">
                      {t('securityUpload.compressLabel')}
                    </span>
                  </label>
                </AlertTitle>
                <AlertDescription>
                  <p>
                    {isVeryLarge
                      ? enableCompression
                        ? t('securityUpload.veryLargeCompress')
                        : t('securityUpload.veryLargeNoCompress')
                      : enableCompression
                        ? t('securityUpload.largeCompress')
                        : t('securityUpload.largeNoCompress')}
                  </p>
                  {originalSize > 0 && compressedSize > 0 && compressedSize < originalSize && (
                    <p className="mt-2 flex items-center gap-1.5 font-medium">
                      <CheckCircle className="h-4 w-4" aria-hidden="true" />
                      {t('securityUpload.savings', {
                        mb: ((originalSize - compressedSize) / (1024 * 1024)).toFixed(1),
                        percent: ((1 - compressedSize / originalSize) * 100).toFixed(1),
                      })}
                    </p>
                  )}
                </AlertDescription>
              </Alert>
            )}

            {/* Progress de compresión */}
            {compressionProgress && uploadStatus !== 'uploading' && (
              <div className="space-y-2" aria-live="polite">
                <div className="flex justify-between text-sm text-muted-foreground">
                  <span>{compressionProgress.message}</span>
                  <span>{compressionProgress.percent}%</span>
                </div>
                <Progress
                  value={compressionProgress.percent}
                  aria-label={compressionProgress.message}
                />
              </div>
            )}

            {/* Progress bar de upload */}
            {uploading && uploadStatus === 'uploading' && (
              <div className="space-y-2" aria-live="polite">
                <div className="flex justify-between text-sm text-muted-foreground">
                  <span>{t('securityUpload.uploadingProgress')}</span>
                  <span>{uploadProgress}%</span>
                </div>
                <Progress value={uploadProgress} aria-label={t('securityUpload.uploadingProgress')} />
                {currentVideoId && (
                  <p className="text-xs text-muted-foreground">ID: {currentVideoId}</p>
                )}
              </div>
            )}

            {/* Progress bar de processing */}
            {uploading && (uploadStatus === 'processing' || uploadStatus === 'completed') && (
              <div className="space-y-2" aria-live="polite">
                <div className="flex justify-between text-sm text-muted-foreground">
                  <span>
                    {uploadStatus === 'processing' && t('securityUpload.processingProgress')}
                    {uploadStatus === 'completed' && t('securityUpload.completedProgress')}
                  </span>
                  <span>100%</span>
                </div>
                <Progress
                  value={100}
                  indicatorClassName={uploadStatus === 'completed' ? 'bg-success' : 'bg-warning'}
                  aria-label={t('securityUpload.processingProgress')}
                />
              </div>
            )}

            {/* Botones */}
            <div className="flex gap-4 pt-4">
              <Button
                type="submit"
                variant={uploadStatus === 'completed' ? 'success' : 'default'}
                disabled={uploading || !file}
                loading={uploading && uploadStatus !== 'completed'}
                className="flex-1"
              >
                {statusButtonContent()}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate({ to: '/security' })}
                disabled={uploading}
              >
                {t('securityUpload.cancel')}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Información adicional */}
      <Card>
        <CardContent className="p-4">
          <h3 className="mb-2 font-semibold text-foreground">{t('securityUpload.infoTitle')}</h3>
          <ul className="ml-5 list-disc space-y-1 text-sm text-muted-foreground">
            <li>{t('securityUpload.info1')}</li>
            <li>{t('securityUpload.info2')}</li>
            <li>{t('securityUpload.info3')}</li>
            <li>{t('securityUpload.info4')}</li>
            <li>{t('securityUpload.info5')}</li>
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
