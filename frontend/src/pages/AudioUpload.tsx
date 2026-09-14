import { useEffect, useState, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { audioAnalysisService } from '../services/audioAnalysisService';
import { toast } from 'sonner';
import {
  ArrowLeft,
  Upload,
  Headphones,
  Loader2,
  CircleHelp,
  FileAudio,
  CheckCircle2,
  X,
  CloudUpload,
  Music2,
} from 'lucide-react';
import { PageContainer } from '../components/ui/page-container';
import { PageHeader } from '../components/ui/page-header';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Progress } from '../components/ui/progress';
import { useTranslation } from '../i18n';

const MAX_DURATION_HOURS = 2;
const MAX_PROXY_UPLOAD_GB = 10;
const MAX_FILE_SIZE_BYTES = MAX_PROXY_UPLOAD_GB * 1024 * 1024 * 1024;
const ALLOWED_MEDIA_EXTENSIONS = new Set([
  '.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.wmv', '.flv', '.mpeg', '.mpg', '.3gp', '.ts',
  '.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg', '.oga', '.opus', '.wma', '.amr', '.aiff', '.aif',
  '.mp2', '.mka',
]);
const ACCEPTED_MEDIA_INPUT =
  'video/*,audio/*,.mp4,.mov,.avi,.mkv,.webm,.m4v,.wmv,.flv,.mpeg,.mpg,.3gp,.ts,.mp3,.wav,.aac,.m4a,.flac,.ogg,.oga,.opus,.wma,.amr,.aiff,.aif,.mp2,.mka';

export default function AudioUpload() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [titulo, setTitulo] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadPhase, setUploadPhase] = useState('');

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!uploading) return;
      event.preventDefault();
      event.returnValue = t('audioUpload.beforeUnload');
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [uploading, t]);

  const buildTitleFromFilename = (filename: string): string => {
    const nameWithoutExt = filename.replace(/\.[^/.]+$/, '');
    const cleaned = nameWithoutExt
      .replace(/[._-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    if (!cleaned) return '';
    return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  };

  const getMediaDurationSeconds = async (file: File): Promise<number> => {
    const objectUrl = URL.createObjectURL(file);
    try {
      const readDuration = (elementType: 'audio' | 'video') =>
        new Promise<number>((resolve, reject) => {
          const media = document.createElement(elementType);
          media.preload = 'metadata';

          media.onloadedmetadata = () => {
            const result = Number.isFinite(media.duration) ? media.duration : 0;
            resolve(result > 0 ? result : 0);
          };

          media.onerror = () => reject(new Error(`No se pudo leer la duración del ${elementType}`));
          media.src = objectUrl;
        });

      const preferredType: 'audio' | 'video' = file.type.startsWith('audio/') ? 'audio' : 'video';
      const fallbackType: 'audio' | 'video' = preferredType === 'audio' ? 'video' : 'audio';
      let duration = 0;

      try {
        duration = await readDuration(preferredType);
      } catch {
        duration = await readDuration(fallbackType);
      }

      return duration;
    } finally {
      URL.revokeObjectURL(objectUrl);
    }
  };

  const isSupportedMediaFile = (file: File): boolean => {
    if (file.type.startsWith('video/') || file.type.startsWith('audio/')) {
      return true;
    }
    const dotIndex = file.name.lastIndexOf('.');
    const extension = dotIndex >= 0 ? file.name.slice(dotIndex).toLowerCase() : '';
    return ALLOWED_MEDIA_EXTENSIONS.has(extension);
  };

  const selectMediaFile = (file: File) => {
    if (!isSupportedMediaFile(file)) {
      toast.error(t('audioUpload.toastUnsupported'));
      return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      toast.error(t('audioUpload.toastTooLarge', { size: MAX_PROXY_UPLOAD_GB }));
      return;
    }

    setSelectedFile(file);

    if (!titulo.trim()) {
      const suggestedTitle = buildTitleFromFilename(file.name);
      if (suggestedTitle) {
        setTitulo(suggestedTitle);
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    selectMediaFile(file);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDraggingFile(false);

    const file = event.dataTransfer.files?.[0];
    if (!file) return;
    selectMediaFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      toast.error(t('audioUpload.toastSelectFile'));
      return;
    }

    setUploading(true);
    setUploadProgress(0);

    try {
      setUploadPhase(t('audioUpload.phaseMetadata'));
      const clientVideoDuration = await getMediaDurationSeconds(selectedFile);
      if (clientVideoDuration > MAX_DURATION_HOURS * 3600) {
        toast.error(t('audioUpload.toastDuration', { hours: MAX_DURATION_HOURS }));
        return;
      }

      setUploadPhase(t('audioUpload.phaseInit'));
      const initResponse = await audioAnalysisService.iniciarUpload({
        filename: selectedFile.name,
        content_type: selectedFile.type || 'application/octet-stream',
        titulo: titulo.trim() || undefined,
        descripcion: descripcion.trim() || undefined,
        client_video_duration: clientVideoDuration,
      });

      if (!initResponse.success) {
        throw new Error(initResponse.error || t('audioUpload.initError'));
      }

      const analysisId = initResponse.analysis_id;

      setUploadPhase(t('audioUpload.phaseUploading'));

      const uploadUrl: string = initResponse.upload_url ?? '';
      const isDirectUploadAllowed =
        uploadUrl.startsWith(window.location.origin) ||
        (!window.location.hostname.includes('localhost') &&
          !window.location.hostname.includes('127.0.0.1'));

      if (isDirectUploadAllowed) {
        try {
          await audioAnalysisService.subirArchivoDirectoResumable(
            uploadUrl,
            selectedFile,
            (progress) => setUploadProgress(progress),
          );
        } catch {
          await audioAnalysisService.subirArchivoProxy(
            analysisId,
            selectedFile,
            (progress) => setUploadProgress(progress),
          );
        }
      } else {
        await audioAnalysisService.subirArchivoProxy(
          analysisId,
          selectedFile,
          (progress) => setUploadProgress(progress),
        );
      }

      setUploadPhase(t('audioUpload.phaseProcessing'));
      setUploadProgress(100);

      const completeResponse = await audioAnalysisService.completarUpload(
        analysisId,
        true,
        clientVideoDuration,
      );

      if (!completeResponse.success) {
        throw new Error(t('audioUpload.completeError'));
      }

      if (completeResponse.video_duration > MAX_DURATION_HOURS * 3600) {
        toast.error(t('audioUpload.toastDuration', { hours: MAX_DURATION_HOURS }));
        return;
      }

      toast.success(t('audioUpload.toastSuccess'));
      navigate({ to: '/audio' });
    } catch (error) {
      const msg = getErrorText(error, t('audioUpload.toastError'));
      toast.error(msg);
    } finally {
      setUploading(false);
      setUploadPhase('');
    }
  };

  const fileSizeMB = selectedFile ? (selectedFile.size / (1024 * 1024)).toFixed(1) : '0';
  const fileExt = selectedFile ? selectedFile.name.split('.').pop()?.toUpperCase() || '' : '';

  return (
    <PageContainer className="max-w-3xl pb-16">
      <Button
        variant="ghost"
        onClick={() => navigate({ to: '/audio' })}
        className="w-fit px-0 hover:bg-transparent"
      >
        <ArrowLeft aria-hidden="true" />
        {t('audioUpload.back')}
      </Button>

      <PageHeader
        icon={Headphones}
        title={t('audioUpload.title')}
        description={t('audioUpload.subtitle')}
        actions={
          <div className="group relative">
            <Button
              variant="ghost"
              size="icon"
              aria-label={t('audioUpload.help')}
              className="peer"
            >
              <CircleHelp aria-hidden="true" />
            </Button>
            <div className="pointer-events-none absolute right-0 top-full z-30 mt-2 w-72 rounded-xl border border-border bg-popover p-3 text-sm leading-relaxed text-muted-foreground opacity-0 shadow-popover transition-opacity peer-hover:opacity-100 peer-focus-visible:opacity-100">
              {t('audioUpload.help')}
            </div>
          </div>
        }
      />

      <Card variant="elevated">
        <CardContent className="space-y-7 p-6 lg:p-8">
          {/* File upload */}
          <div>
            <Label className="mb-3 flex items-center gap-1.5">
              <FileAudio className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              {t('audioUpload.fileLabel')} <span className="text-primary">*</span>
            </Label>

            {!selectedFile ? (
              <div
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    fileInputRef.current?.click();
                  }
                }}
                role="button"
                tabIndex={0}
                aria-label={t('audioUpload.fileLabel')}
                onDragOver={(event) => {
                  event.preventDefault();
                  setIsDraggingFile(true);
                }}
                onDragLeave={() => setIsDraggingFile(false)}
                onDrop={handleDrop}
                className={`relative cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  isDraggingFile
                    ? 'border-primary bg-brand-soft'
                    : 'border-border hover:border-brand-border hover:bg-brand-soft/40'
                }`}
              >
                <div className="flex flex-col items-center">
                  <div
                    className={`mb-4 flex h-16 w-16 items-center justify-center rounded-2xl transition-colors duration-300 ${
                      isDraggingFile ? 'bg-brand-soft' : 'bg-muted'
                    }`}
                  >
                    <CloudUpload
                      className={`h-8 w-8 transition-colors duration-300 ${
                        isDraggingFile ? 'text-primary' : 'text-muted-foreground'
                      }`}
                      aria-hidden="true"
                    />
                  </div>
                  <p className="text-base font-semibold text-foreground">
                    {isDraggingFile ? t('audioUpload.dropActive') : t('audioUpload.dropTitle')}
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {t('audioUpload.clickHint')}
                  </p>
                  <div className="mt-4 flex flex-wrap justify-center gap-1.5">
                    {['MP4', 'MP3', 'WAV', 'M4A', 'MOV', 'FLAC', 'OGG'].map((ext) => (
                      <Badge key={ext} variant="muted">
                        {ext}
                      </Badge>
                    ))}
                    <span className="px-2 py-0.5 text-[11px] text-muted-foreground">
                      {t('audioUpload.andMore')}
                    </span>
                  </div>
                  <p className="mt-3 text-xs text-muted-foreground">
                    {t('audioUpload.limits', {
                      hours: MAX_DURATION_HOURS,
                      size: MAX_PROXY_UPLOAD_GB,
                    })}
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-4 rounded-2xl border border-border bg-muted/50 p-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-brand-soft">
                  <Music2 className="h-6 w-6 text-primary" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-foreground">{selectedFile.name}</p>
                  <div className="mt-0.5 flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">{fileSizeMB} MB</span>
                    {fileExt && (
                      <Badge variant="secondary" className="uppercase">
                        {fileExt}
                      </Badge>
                    )}
                    <span className="flex items-center gap-1 text-xs text-success">
                      <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                      {t('audioUpload.readyToUpload')}
                    </span>
                  </div>
                </div>
                {!uploading && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t('audioUpload.remove')}
                    onClick={() => {
                      setSelectedFile(null);
                      if (fileInputRef.current) fileInputRef.current.value = '';
                    }}
                    className="text-muted-foreground hover:bg-error-surface hover:text-error"
                  >
                    <X aria-hidden="true" />
                  </Button>
                )}
              </div>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_MEDIA_INPUT}
              onChange={handleFileSelect}
              className="hidden"
              disabled={uploading}
            />
          </div>

          {/* Título */}
          <div>
            <Label htmlFor="audio-title" className="mb-2 block">
              {t('audioUpload.titleLabel')}{' '}
              <span className="font-normal text-muted-foreground">({t('common.optional')})</span>
            </Label>
            <Input
              id="audio-title"
              type="text"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder={t('audioUpload.titlePlaceholder')}
              disabled={uploading}
            />
          </div>

          {/* Descripción */}
          <div>
            <Label htmlFor="audio-description" className="mb-2 block">
              {t('audioUpload.descriptionLabel')}{' '}
              <span className="font-normal text-muted-foreground">({t('common.optional')})</span>
            </Label>
            <Textarea
              id="audio-description"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              placeholder={t('audioUpload.descriptionPlaceholder')}
              rows={3}
              disabled={uploading}
            />
          </div>

          {/* Upload progress */}
          {uploading && (
            <div className="space-y-3" aria-live="polite">
              <Alert variant="info" className="items-center">
                <Loader2 className="animate-spin" aria-hidden="true" />
                <AlertDescription className="font-medium">{uploadPhase}</AlertDescription>
              </Alert>
              <div>
                <Progress value={uploadProgress} aria-label={uploadPhase} />
                <p className="mt-1.5 text-right text-xs font-medium text-muted-foreground">
                  {uploadProgress}%
                </p>
              </div>
            </div>
          )}

          {/* Submit */}
          <div className="flex gap-3 border-t border-border pt-5">
            <Button
              variant="outline"
              onClick={() => navigate({ to: '/audio' })}
              disabled={uploading}
            >
              {t('audioUpload.cancel')}
            </Button>
            <Button
              onClick={handleUpload}
              disabled={!selectedFile || uploading}
              loading={uploading}
              className="flex-1"
              title={
                !selectedFile && !uploading ? t('audioUpload.toastSelectFile') : undefined
              }
            >
              {!uploading && <Upload aria-hidden="true" />}
              {uploading ? t('audioUpload.uploading') : t('audioUpload.submit')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </PageContainer>
  );
}

function getErrorText(error: unknown, fallback: string): string {
  if (error && typeof error === 'object') {
    const withResponse = error as {
      response?: { data?: { error?: string } };
      message?: string;
    };
    return withResponse.response?.data?.error || withResponse.message || fallback;
  }
  return fallback;
}
