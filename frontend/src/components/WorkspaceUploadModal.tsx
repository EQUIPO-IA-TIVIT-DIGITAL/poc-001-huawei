import { useState, useRef, useEffect, useCallback } from 'react';
import { getApiBaseUrl } from '../lib/backendUrl';
import { Upload, FileVideo, Trash2, AlertCircle, Plus } from 'lucide-react';
import { Button } from './ui/button';
import { Progress } from './ui/progress';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { cn } from '../lib/utils';
import { useTranslation } from '../i18n';

interface FileWithPreview {
    file: File;
    id: string;
    previewUrl?: string;
}

interface WorkspaceUploadModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    workspaceId: string;
    workspaceName: string;
    onBatchUploadSuccess?: (batchId: string, videoIds: string[]) => void;
}

const MAX_FILES = 5;
const MAX_FILE_SIZE = 100 * 1024 * 1024;
const VALID_EXTENSIONS = ['mp4', 'avi', 'mov', 'mkv', 'webm'];

export function WorkspaceUploadModal({
    open,
    onOpenChange,
    workspaceId,
    workspaceName,
    onBatchUploadSuccess,
}: WorkspaceUploadModalProps) {
    const { t } = useTranslation();
    const [files, setFiles] = useState<FileWithPreview[]>([]);
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [error, setError] = useState<string | null>(null);
    const [dragActive, setDragActive] = useState(false);

    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        return () => {
            files.forEach((f) => {
                if (f.previewUrl) URL.revokeObjectURL(f.previewUrl);
            });
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        if (!open) {
            files.forEach((f) => {
                if (f.previewUrl) URL.revokeObjectURL(f.previewUrl);
            });
            setFiles([]);
            setError(null);
            setProgress(0);
            setUploading(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    const validateFile = useCallback(
        (file: File): string | null => {
            const extension = file.name.split('.').pop()?.toLowerCase();
            if (!VALID_EXTENSIONS.includes(extension || '')) {
                return t('uploadModal.unsupportedFormat', { name: file.name });
            }
            if (file.size > MAX_FILE_SIZE) {
                return t('uploadModal.exceedsSize', { name: file.name });
            }
            return null;
        },
        [t],
    );

    const addFiles = useCallback(
        (newFiles: FileList | File[]) => {
            const fileArray = Array.from(newFiles);
            const errors: string[] = [];
            const validFiles: FileWithPreview[] = [];

            for (const file of fileArray) {
                const validationError = validateFile(file);
                if (validationError) {
                    errors.push(validationError);
                    continue;
                }
                validFiles.push({
                    file,
                    id: crypto.randomUUID(),
                    previewUrl: URL.createObjectURL(file),
                });
            }

            setFiles((prev) => {
                const combined = [...prev, ...validFiles];
                if (combined.length > MAX_FILES) {
                    errors.push(t('uploadModal.maxFiles'));
                    return combined.slice(0, MAX_FILES);
                }
                return combined;
            });

            if (errors.length > 0) {
                setError(errors.join(' '));
            } else {
                setError(null);
            }
        },
        [validateFile, t],
    );

    const removeFile = useCallback((id: string) => {
        setFiles((prev) => {
            const file = prev.find((f) => f.id === id);
            if (file?.previewUrl) URL.revokeObjectURL(file.previewUrl);
            return prev.filter((f) => f.id !== id);
        });
        setError(null);
    }, []);

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
            addFiles(e.dataTransfer.files);
        }
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        e.preventDefault();
        if (e.target.files && e.target.files.length > 0) {
            addFiles(e.target.files);
        }
        if (inputRef.current) inputRef.current.value = '';
    };

    const handleUpload = async () => {
        if (files.length === 0) return;

        setUploading(true);
        setProgress(0);
        setError(null);

        const baseUrl = import.meta.env.VITE_API_BASE_URL || getApiBaseUrl();

        const formData = new FormData();
        files.forEach((f) => formData.append('videos', f.file));
        formData.append('workspace_id', workspaceId);

        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${baseUrl}/socio/batch-upload`, true);
        xhr.withCredentials = true;
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');

        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                setProgress(Math.round((e.loaded / e.total) * 100));
            }
        };

        xhr.onload = () => {
            if (xhr.status === 200 || xhr.status === 201 || xhr.status === 202) {
                try {
                    const response = JSON.parse(xhr.responseText) as {
                        success?: boolean;
                        batch_id?: string;
                        videos?: Array<{ video_id: string }>;
                        error?: string;
                    };
                    if (response.success && response.batch_id) {
                        const videoIds = response.videos?.map((v) => v.video_id) || [];
                        if (onBatchUploadSuccess) {
                            onBatchUploadSuccess(response.batch_id, videoIds);
                        }
                        setFiles([]);
                        setUploading(false);
                        setProgress(0);
                    } else {
                        setError(response.error || t('uploadModal.uploadError'));
                        setUploading(false);
                    }
                } catch {
                    setError(t('uploadModal.parseError'));
                    setUploading(false);
                }
            } else if (xhr.status === 401) {
                localStorage.removeItem('accessfan_user');
                localStorage.removeItem('accessfan_token');
                window.dispatchEvent(new Event('auth:unauthorized'));
                setUploading(false);
            } else {
                try {
                    const response = JSON.parse(xhr.responseText) as { error?: string };
                    setError(response.error || t('uploadModal.uploadError'));
                } catch {
                    setError(t('uploadModal.uploadError'));
                }
                setUploading(false);
            }
        };

        xhr.onerror = () => {
            setError(t('uploadModal.networkError'));
            setUploading(false);
        };

        xhr.send(formData);
    };

    const totalSize = files.reduce((sum, f) => sum + f.file.size, 0);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[90vh] max-w-3xl gap-6 overflow-y-auto p-8">
                <DialogHeader className="space-y-3">
                    <DialogTitle className="flex items-center gap-3 text-2xl font-bold">
                        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-foreground shadow-sm">
                            <Upload className="h-6 w-6 text-primary-foreground" aria-hidden="true" />
                        </div>
                        {files.length > 1
                            ? t('uploadModal.titleWithCount', { count: files.length })
                            : t('uploadModal.title')}
                    </DialogTitle>
                    <DialogDescription className="text-[15px] leading-relaxed text-muted-foreground">
                        {t('uploadModal.description', { max: MAX_FILES, name: workspaceName })}
                    </DialogDescription>
                </DialogHeader>

                <div>
                    {files.length < MAX_FILES && (
                        <div
                            className={cn(
                                'relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed transition-all duration-300',
                                files.length === 0 ? 'p-16' : 'p-8',
                                dragActive
                                    ? 'scale-[1.02] border-primary bg-brand-soft'
                                    : 'border-border bg-muted/40 hover:border-primary/50 hover:bg-muted/60',
                            )}
                            onDragEnter={handleDrag}
                            onDragLeave={handleDrag}
                            onDragOver={handleDrag}
                            onDrop={handleDrop}
                        >
                            <input
                                ref={inputRef}
                                type="file"
                                className="hidden"
                                accept="video/*"
                                multiple
                                onChange={handleChange}
                            />

                            {files.length === 0 ? (
                                <>
                                    <div
                                        className={cn(
                                            'mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl shadow-sm transition-all duration-300',
                                            dragActive
                                                ? 'scale-110 bg-brand-soft text-primary'
                                                : 'border border-border bg-card text-muted-foreground',
                                        )}
                                    >
                                        <Upload size={28} aria-hidden="true" />
                                    </div>
                                    <h3 className="mb-2 text-[19px] font-bold text-foreground">
                                        {dragActive ? t('uploadModal.dropActive') : t('uploadModal.dropTitle')}
                                    </h3>
                                    <p className="mb-6 text-[15px] text-muted-foreground">{t('uploadModal.orClick')}</p>
                                    <Button onClick={() => inputRef.current?.click()}>
                                        {t('uploadModal.selectFiles')}
                                    </Button>

                                    <div className="mt-8 w-full max-w-sm border-t border-border pt-6 text-center">
                                        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                                            {t('uploadModal.supportedFormats')}
                                        </p>
                                        <div className="flex flex-wrap justify-center gap-2">
                                            {['MP4', 'AVI', 'MOV', 'MKV', 'WEBM'].map((ext) => (
                                                <span
                                                    key={ext}
                                                    className="rounded-lg border border-border bg-card px-2.5 py-1 text-xs font-bold text-muted-foreground shadow-sm"
                                                >
                                                    {ext}
                                                </span>
                                            ))}
                                        </div>
                                        <p className="mt-4 text-xs font-medium text-muted-foreground">
                                            {t('uploadModal.limitInfo', { max: MAX_FILES })}
                                        </p>
                                    </div>
                                </>
                            ) : (
                                <div className="text-center">
                                    <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl border border-border bg-card text-muted-foreground shadow-sm">
                                        <Plus size={24} aria-hidden="true" />
                                    </div>
                                    <p className="mb-4 text-[15px] font-medium text-muted-foreground">
                                        {t('uploadModal.addMore')}
                                    </p>
                                    <Button variant="outline" onClick={() => inputRef.current?.click()}>
                                        {t('uploadModal.addMoreButton')}
                                    </Button>
                                </div>
                            )}
                        </div>
                    )}

                    {files.length > 0 && (
                        <div className="mt-6 space-y-3">
                            <div className="mb-3 flex items-center justify-between px-1">
                                <span className="text-[15px] font-bold text-foreground">
                                    {t('uploadModal.selectedCount', {
                                        count: files.length,
                                        size: (totalSize / (1024 * 1024)).toFixed(1),
                                    })}
                                </span>
                                {files.length >= MAX_FILES && (
                                    <span className="rounded-full border border-warning-border bg-warning-surface px-3 py-1 text-[13px] font-bold text-warning">
                                        {t('uploadModal.limitReached')}
                                    </span>
                                )}
                            </div>

                            <div className="max-h-56 space-y-2 overflow-y-auto pr-2">
                                {files.map((f, idx) => (
                                    <div
                                        key={f.id}
                                        className="group flex items-center gap-4 rounded-2xl border border-border bg-card p-4 shadow-sm transition-colors hover:border-primary/50"
                                    >
                                        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border border-border bg-muted/40">
                                            <FileVideo className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
                                        </div>
                                        <div className="min-w-0 flex-1">
                                            <p className="truncate text-[15px] font-semibold text-foreground" title={f.file.name}>
                                                {f.file.name}
                                            </p>
                                            <p className="mt-0.5 text-xs font-medium text-muted-foreground">
                                                {t('uploadModal.sizeMb', {
                                                    size: (f.file.size / (1024 * 1024)).toFixed(1),
                                                })}
                                            </p>
                                        </div>
                                        <span className="w-8 flex-shrink-0 text-right text-xs font-bold text-muted-foreground">
                                            #{idx + 1}
                                        </span>
                                        {!uploading && (
                                            <Button
                                                variant="ghost"
                                                size="icon-sm"
                                                onClick={() => removeFile(f.id)}
                                                aria-label={t('audioUpload.remove')}
                                                className="opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                                            >
                                                <Trash2 aria-hidden="true" />
                                            </Button>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {uploading && (
                        <div className="mt-6 space-y-4 rounded-2xl border border-border bg-muted/40 p-6 shadow-sm">
                            <div className="flex items-end justify-between">
                                <div>
                                    <span className="mb-1 block text-lg font-bold text-foreground">
                                        {t('uploadModal.analyzing')}
                                    </span>
                                    <span className="text-sm font-medium text-muted-foreground">
                                        {t('uploadModal.uploadingDesc', { count: files.length })}
                                    </span>
                                </div>
                                <span className="font-mono text-2xl font-black tracking-tight text-foreground">
                                    {progress}%
                                </span>
                            </div>
                            <Progress value={progress} aria-label={t('uploadModal.analyzing')} />
                            <p className="flex items-center justify-center gap-2 text-[13px] font-medium text-muted-foreground" aria-live="polite">
                                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-warning" />
                                {progress < 100 ? t('uploadModal.doNotClose') : t('uploadModal.queuing')}
                            </p>
                        </div>
                    )}

                    {error && (
                        <Alert variant="error" className="mt-6">
                            <AlertCircle aria-hidden="true" />
                            <AlertTitle>{t('common.error')}</AlertTitle>
                            <AlertDescription>{error}</AlertDescription>
                        </Alert>
                    )}

                    {!uploading && files.length > 0 && (
                        <div className="mt-8 flex justify-end gap-3 border-t border-border pt-5">
                            <Button
                                variant="ghost"
                                onClick={() => {
                                    files.forEach((f) => {
                                        if (f.previewUrl) URL.revokeObjectURL(f.previewUrl);
                                    });
                                    setFiles([]);
                                    setError(null);
                                }}
                            >
                                {t('uploadModal.clearAll')}
                            </Button>
                            <Button onClick={() => void handleUpload()}>
                                <Upload aria-hidden="true" />
                                {files.length === 1
                                    ? t('uploadModal.uploadOne')
                                    : t('uploadModal.uploadMany', { count: files.length })}
                            </Button>
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
