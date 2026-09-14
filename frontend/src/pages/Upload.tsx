import { useState, useRef, useEffect } from 'react';
import { getApiBaseUrl } from '../lib/backendUrl';
import {
  Upload as UploadIcon,
  Info,
  Check,
  AlertCircle,
  Video,
  FileVideo,
  Trash2,
  Loader2,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Progress } from '../components/ui/progress';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { BatchNotification } from '../components/BatchNotification';
import { workspaceService, type Workspace } from '../services/workspace';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { useTranslation } from '../i18n';

const MAX_UPLOAD_SIZE_MB = 100;
const MAX_DURATION_SECONDS = 60;
const MAX_FILES_PER_UPLOAD = 5;

export default function UploadPage() {
  const { t } = useTranslation();
  const [dragActive, setDragActive] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null);
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>('general');

  const { data: workspaces = [] } = useQuery({
    queryKey: ['upload-workspaces'],
    queryFn: () => workspaceService.listWorkspaces('alfabetico'),
  });

  const selectedWorkspaceName =
    selectedWorkspace === 'general'
      ? t('upload.general')
      : workspaces.find((ws: Workspace) => ws.id === selectedWorkspace)?.nombre ||
        t('upload.general');

  // Background batch tracking
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [showBatchNotification, setShowBatchNotification] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const videoPreviewRef = useRef<HTMLVideoElement>(null);

  // Create preview URL for selected video
  useEffect(() => {
    if (files.length > 0 && !uploading && !success) {
      const url = URL.createObjectURL(files[0]);
      setVideoPreviewUrl(url);
      return () => URL.revokeObjectURL(url);
    } else {
      setVideoPreviewUrl(null);
    }
  }, [files, uploading, success]);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(Array.from(e.target.files));
    }
  };

  const handleFiles = (incomingFiles: File[]) => {
    if (incomingFiles.length > MAX_FILES_PER_UPLOAD) {
      setError(t('upload.maxFilesError'));
      return;
    }

    const validExtensions = ['mp4', 'avi', 'mov', 'mkv', 'webm'];
    const valid: File[] = [];

    for (const file of incomingFiles) {
      const extension = file.name.split('.').pop()?.toLowerCase();
      if (!validExtensions.includes(extension || '')) {
        setError(t('upload.invalidFormat', { name: file.name }));
        return;
      }

      if (file.size > MAX_UPLOAD_SIZE_MB * 1024 * 1024) {
        setError(t('upload.tooLarge', { name: file.name, size: MAX_UPLOAD_SIZE_MB }));
        return;
      }

      valid.push(file);
    }

    setFiles(valid);
    setError(null);
    setSuccess(false);
  };

  const onButtonClick = () => {
    inputRef.current?.click();
  };

  const handleUpload = async () => {
    if (files.length === 0) return;

    setUploading(true);
    setProgress(0);
    setError(null);

    const formData = new FormData();
    files.forEach((file) => formData.append('videos', file));
    formData.append('workspace_id', selectedWorkspace);

    const xhr = new XMLHttpRequest();
    const baseUrl = import.meta.env.VITE_API_BASE_URL || getApiBaseUrl();
    xhr.open('POST', `${baseUrl}/socio/batch-upload`, true);
    xhr.withCredentials = true;
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const percentComplete = (e.loaded / e.total) * 100;
        setProgress(Math.round(percentComplete));
      }
    };

    xhr.onload = function () {
      if (xhr.status === 200 || xhr.status === 201 || xhr.status === 202) {
        try {
          const response = JSON.parse(xhr.responseText);
          if (response.success && response.batch_id) {
            setSuccess(true);
            setFiles([]);
            setActiveBatchId(response.batch_id);
            setShowBatchNotification(true);
            toast.info(t('upload.uploadSuccessToast'));
            setUploading(false);
          } else {
            setError(response.error || t('upload.uploadError'));
            setUploading(false);
          }
        } catch {
          setError(t('upload.parseError'));
          setUploading(false);
        }
      } else if (xhr.status === 401) {
        localStorage.removeItem('accessfan_user');
        localStorage.removeItem('accessfan_token');
        window.dispatchEvent(new Event('auth:unauthorized'));
        setUploading(false);
        return;
      } else {
        try {
          const response = JSON.parse(xhr.responseText);
          setError(response.error || t('upload.uploadError'));
        } catch {
          setError(t('upload.uploadError'));
        }
        setUploading(false);
      }
    };

    xhr.onerror = function () {
      setError(t('upload.networkError'));
      setUploading(false);
    };

    xhr.send(formData);
  };

  const totalSizeMB = files.reduce((acc, f) => acc + f.size, 0) / (1024 * 1024);

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6">
      <div className="flex items-center gap-3">
        <div className="rounded-2xl bg-primary p-3 text-primary-foreground shadow-lg">
          <UploadIcon size={28} strokeWidth={2} aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-3xl font-bold text-foreground">{t('upload.title')}</h1>
          <p className="mt-1 text-muted-foreground">
            {t('upload.description', { project: selectedWorkspaceName })}
          </p>
        </div>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
          <label className="min-w-fit text-sm font-semibold text-foreground">
            {t('upload.destination')}
          </label>
          <div className="w-full sm:max-w-md">
            <Select value={selectedWorkspace} onValueChange={setSelectedWorkspace}>
              <SelectTrigger aria-label={t('upload.destination')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="general">{t('upload.generalDefault')}</SelectItem>
                {workspaces.map((ws: Workspace) => (
                  <SelectItem key={ws.id} value={ws.id}>
                    {ws.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Upload Area */}
      <Card
        className={`relative overflow-hidden rounded-2xl border-2 border-dashed transition-all duration-300 ${
          dragActive
            ? 'border-primary bg-brand-soft'
            : 'border-border bg-muted/40 hover:border-gray-400'
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          multiple
          accept="video/*"
          onChange={handleChange}
        />

        {files.length === 0 ? (
          <div className="relative z-20 flex flex-col items-center justify-center space-y-4 px-8 py-12">
            <button
              type="button"
              onClick={onButtonClick}
              aria-label={t('upload.dropTitle')}
              className={`mb-4 flex h-20 w-20 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-xl transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                dragActive ? 'scale-110 rotate-6' : 'hover:scale-105'
              }`}
            >
              <UploadIcon
                size={36}
                className={dragActive ? 'animate-bounce' : ''}
                aria-hidden="true"
              />
            </button>
            <h3 className="text-2xl font-bold text-foreground">
              {dragActive ? t('upload.dropActive') : t('upload.dropTitle')}
            </h3>
            <p className="font-medium text-muted-foreground">
              {t('upload.clickHint', { count: MAX_FILES_PER_UPLOAD })}
            </p>

            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {['MP4', 'AVI', 'MOV', 'MKV', 'WEBM'].map((ext) => (
                <span
                  key={ext}
                  className="rounded-lg border-2 border-border bg-card px-3 py-1.5 text-xs font-bold text-muted-foreground transition-colors hover:border-primary hover:text-primary"
                >
                  .{ext}
                </span>
              ))}
            </div>

            <div className="mt-6 flex items-center gap-2 text-xs text-muted-foreground">
              <Info size={14} aria-hidden="true" />
              <span>
                {t('upload.maxInfo', {
                  size: MAX_UPLOAD_SIZE_MB,
                  duration: MAX_DURATION_SECONDS,
                })}
              </span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center gap-8 px-8 py-8 lg:flex-row">
            {videoPreviewUrl && !uploading && !success && (
              <div className="relative aspect-video w-full overflow-hidden rounded-xl border-2 border-border bg-black lg:w-80">
                <video
                  ref={videoPreviewRef}
                  src={videoPreviewUrl}
                  className="h-full w-full object-contain"
                  controls
                  muted
                  playsInline
                />
                <div className="absolute right-2 top-2">
                  <Button
                    variant="danger"
                    size="icon-sm"
                    onClick={() => setFiles([])}
                    aria-label={t('upload.clearSelection')}
                  >
                    <Trash2 aria-hidden="true" />
                  </Button>
                </div>
              </div>
            )}

            <div className="w-full max-w-md flex-1">
              {uploading ? (
                <div className="space-y-6">
                  <div className="flex items-center gap-4 rounded-xl border border-border bg-card p-4">
                    <div className="rounded-lg bg-brand-soft p-3">
                      <Video className="h-6 w-6 text-primary" aria-hidden="true" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-bold text-foreground">
                        {files.length > 1
                          ? t('upload.filesSelected', { count: files.length })
                          : files[0]?.name}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {t('upload.sizeMB', { size: totalSizeMB.toFixed(2) })}
                      </p>
                    </div>
                  </div>

                  <div className="space-y-3" aria-live="polite">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="flex items-center gap-1.5 font-bold text-foreground">
                          <UploadIcon size={14} aria-hidden="true" />
                          {t('upload.uploadPhase')}
                        </span>
                        <span className="font-mono text-primary">{progress}%</span>
                      </div>
                      <Progress value={progress} aria-label={t('upload.uploadPhase')} />
                    </div>

                    <div className="space-y-2 opacity-50">
                      <div className="flex items-center justify-between text-sm">
                        <span className="flex items-center gap-1.5 font-bold text-muted-foreground">
                          <Loader2 size={14} aria-hidden="true" />
                          {t('upload.analysisPhase')}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {t('upload.nextPhase')}
                        </span>
                      </div>
                      <Progress value={0} aria-hidden="true" />
                    </div>
                  </div>

                  <p className="text-center text-xs italic text-muted-foreground">
                    {t('upload.waitHint')}
                  </p>
                </div>
              ) : success ? (
                <div className="space-y-4 text-center">
                  <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-success text-success-foreground shadow-xl">
                    <Check size={40} strokeWidth={3} aria-hidden="true" />
                  </div>
                  <h3 className="text-2xl font-bold text-foreground">
                    {t('upload.successTitle')}
                  </h3>
                  <p className="text-muted-foreground">{t('upload.successDesc')}</p>
                  <Button variant="outline" onClick={() => setSuccess(false)} className="mt-4">
                    {t('upload.uploadMore')}
                  </Button>
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="rounded-xl border-2 border-border bg-muted/50 p-6">
                    <div className="flex items-start gap-4">
                      <div className="rounded-xl bg-brand-soft p-3">
                        <FileVideo className="h-8 w-8 text-primary" aria-hidden="true" />
                      </div>
                      <div className="flex-1">
                        <h4 className="mb-1 text-lg font-bold text-foreground">
                          {t('upload.selectedVideos')}
                        </h4>
                        <p className="truncate text-sm font-medium text-muted-foreground">
                          {files.length > 1
                            ? t('upload.filesReady', { count: files.length })
                            : files[0]?.name}
                        </p>
                        <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <span className="h-2 w-2 rounded-full bg-info" aria-hidden="true" />
                            {t('upload.sizeMB', { size: totalSizeMB.toFixed(2) })}
                          </span>
                          <span className="flex items-center gap-1">
                            <span className="h-2 w-2 rounded-full bg-success" aria-hidden="true" />
                            {files.length === 1
                              ? t('upload.submitOne', { count: files.length })
                              : t('upload.submitMany', { count: files.length })}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-xl border border-border bg-muted/50 p-4">
                    <p className="text-sm text-muted-foreground">
                      <span className="font-semibold text-foreground">{t('upload.note')}</span>{' '}
                      {t('upload.infoNote', { project: selectedWorkspaceName })}
                    </p>
                  </div>

                  <div className="flex gap-3">
                    <Button
                      variant="outline"
                      className="flex-1"
                      onClick={() => setFiles([])}
                    >
                      <Trash2 aria-hidden="true" />
                      {t('upload.cancel')}
                    </Button>
                    <Button className="flex-1" onClick={handleUpload}>
                      <UploadIcon aria-hidden="true" />
                      {files.length === 1
                        ? t('upload.submitOne', { count: files.length })
                        : t('upload.submitMany', { count: files.length })}
                    </Button>
                  </div>
                </div>
              )}

              {error && (
                <Alert variant="error" className="mt-4">
                  <AlertCircle aria-hidden="true" />
                  <AlertDescription className="font-bold">{error}</AlertDescription>
                </Alert>
              )}
            </div>
          </div>
        )}
      </Card>

      {/* Info Card */}
      <Card>
        <CardContent className="p-6">
          <div className="mb-4 flex items-center gap-2 text-info">
            <Info size={20} aria-hidden="true" />
            <h3 className="font-bold text-foreground">{t('upload.infoTitle')}</h3>
          </div>
          <ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground marker:text-muted-foreground">
            <li>
              <span className="font-bold text-foreground">{t('upload.infoAuto')}</span>
              {t('upload.infoAutoDesc')}
            </li>
            <li>
              <span className="font-bold text-foreground">{t('upload.infoTime')}</span>
              {t('upload.infoTimeDesc')}
            </li>
            <li>
              <span className="font-bold text-foreground">{t('upload.infoAutoTitle')}</span>
              {t('upload.infoAutoTitleDesc')}
            </li>
            <li>
              <span className="font-bold text-foreground">{t('upload.infoNotifications')}</span>
              {t('upload.infoNotificationsDesc')}
            </li>
            <li>
              <span className="font-bold text-foreground">{t('upload.infoLimits')}</span>
              {t('upload.infoLimitsDesc', {
                size: MAX_UPLOAD_SIZE_MB,
                duration: MAX_DURATION_SECONDS,
              })}
            </li>
            <li>
              <span className="font-bold text-foreground">{t('upload.infoFormats')}</span>
              {t('upload.infoFormatsDesc')}
            </li>
          </ul>
        </CardContent>
      </Card>

      {activeBatchId && showBatchNotification && (
        <BatchNotification
          batchId={activeBatchId}
          onClose={() => setShowBatchNotification(false)}
          onComplete={() => {
            toast.success(t('upload.batchComplete'));
            setActiveBatchId(null);
          }}
        />
      )}
    </div>
  );
}
