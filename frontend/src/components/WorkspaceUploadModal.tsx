import { useState, useRef, useEffect, useCallback } from 'react';
import { getApiBaseUrl } from '../lib/backendUrl';
import { Upload, FileVideo, Trash2, AlertCircle, Plus } from 'lucide-react';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';

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
const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB
const VALID_EXTENSIONS = ['mp4', 'avi', 'mov', 'mkv', 'webm'];

export function WorkspaceUploadModal({
    open,
    onOpenChange,
    workspaceId,
    workspaceName,
    onBatchUploadSuccess,
}: WorkspaceUploadModalProps) {
    const [files, setFiles] = useState<FileWithPreview[]>([]);
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [error, setError] = useState<string | null>(null);
    const [dragActive, setDragActive] = useState(false);

    const inputRef = useRef<HTMLInputElement>(null);

    // Cleanup preview URLs on unmount
    useEffect(() => {
        return () => {
            files.forEach(f => {
                if (f.previewUrl) URL.revokeObjectURL(f.previewUrl);
            });
        };
    }, []);

    // Reset on close
    useEffect(() => {
        if (!open) {
            files.forEach(f => {
                if (f.previewUrl) URL.revokeObjectURL(f.previewUrl);
            });
            setFiles([]);
            setError(null);
            setProgress(0);
            setUploading(false);
        }
    }, [open]);

    const validateFile = useCallback((file: File): string | null => {
        const extension = file.name.split('.').pop()?.toLowerCase();
        if (!VALID_EXTENSIONS.includes(extension || '')) {
            return `"${file.name}": Formato no soportado.`;
        }
        if (file.size > MAX_FILE_SIZE) {
            return `"${file.name}": Excede 100MB.`;
        }
        return null;
    }, []);

    const addFiles = useCallback((newFiles: FileList | File[]) => {
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

        setFiles(prev => {
            const combined = [...prev, ...validFiles];
            if (combined.length > MAX_FILES) {
                errors.push('Ya tiene 5 videos analizando, espere que concluyan para enviar más');
                return combined.slice(0, MAX_FILES);
            }
            return combined;
        });

        if (errors.length > 0) {
            setError(errors.join(' '));
        } else {
            setError(null);
        }
    }, [validateFile]);

    const removeFile = useCallback((id: string) => {
        setFiles(prev => {
            const file = prev.find(f => f.id === id);
            if (file?.previewUrl) URL.revokeObjectURL(file.previewUrl);
            return prev.filter(f => f.id !== id);
        });
        setError(null);
    }, []);

    const handleDrag = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
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
        // Reset input so same file can be re-selected
        if (inputRef.current) inputRef.current.value = '';
    };

    const handleUpload = async () => {
        if (files.length === 0) return;

        setUploading(true);
        setProgress(0);
        setError(null);

        const baseUrl = import.meta.env.VITE_API_BASE_URL || getApiBaseUrl();

        // All uploads go through batch endpoint (single or multiple)
        const formData = new FormData();
        files.forEach(f => formData.append('videos', f.file));
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

        xhr.onload = function () {
            if (xhr.status === 200 || xhr.status === 201 || xhr.status === 202) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    if (response.success && response.batch_id) {
                        const videoIds = response.videos?.map((v: { video_id: string }) => v.video_id) || [];
                        if (onBatchUploadSuccess) {
                            onBatchUploadSuccess(response.batch_id, videoIds);
                        }
                        setFiles([]);
                        setUploading(false);
                        setProgress(0);
                    } else {
                        setError(response.error || 'Error al subir los videos');
                        setUploading(false);
                    }
                } catch {
                    setError('Error al procesar la respuesta');
                    setUploading(false);
                }
            } else if (xhr.status === 401) {
                localStorage.removeItem('accessfan_user');
                localStorage.removeItem('accessfan_token');
                window.dispatchEvent(new Event('auth:unauthorized'));
                setUploading(false);
            } else {
                try {
                    const response = JSON.parse(xhr.responseText);
                    setError(response.error || 'Error al subir los videos');
                } catch {
                    setError('Error al subir los videos');
                }
                setUploading(false);
            }
        };

        xhr.onerror = () => {
            setError('Error de red al subir los videos');
            setUploading(false);
        };

        xhr.send(formData);
    };

    const totalSize = files.reduce((sum, f) => sum + f.file.size, 0);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-3xl bg-white max-h-[90vh] overflow-y-auto sm:rounded-[24px] border-slate-100 shadow-2xl p-8 gap-6 animate-in zoom-in-95 duration-300">
                <DialogHeader className="space-y-3">
                    <DialogTitle className="text-2xl font-bold text-slate-800 flex items-center gap-3">
                        <div className="w-12 h-12 rounded-2xl bg-slate-800 flex items-center justify-center shadow-sm">
                            <Upload className="w-6 h-6 text-white" />
                        </div>
                        Subir Video{files.length > 1 ? 's' : ''} al Proyecto
                    </DialogTitle>
                    <DialogDescription className="text-slate-500 text-[15px] leading-relaxed">
                        Arrastra archivos de video o haz clic para seleccionar. Hasta {MAX_FILES} videos simultáneos hacia el proyecto <span className="font-semibold text-slate-700">"{workspaceName}"</span>.
                    </DialogDescription>
                </DialogHeader>

                <div className="mt-2 text-slate-800">
                    {/* Drop zone */}
                    {files.length < MAX_FILES && (
                        <div
                            className={`relative border-2 border-dashed rounded-[20px] transition-all duration-300 flex flex-col items-center justify-center ${files.length === 0 ? 'p-16' : 'p-8'
                                } ${dragActive
                                    ? 'border-blue-500 bg-blue-50/50 scale-[1.02]'
                                    : 'border-slate-300 bg-slate-50 hover:bg-slate-100/50 hover:border-slate-400'
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
                                accept="video/*"
                                multiple
                                onChange={handleChange}
                            />

                            {files.length === 0 ? (
                                <>
                                    <div className={`mx-auto w-16 h-16 rounded-2xl flex items-center justify-center mb-5 transition-all duration-300 shadow-sm ${dragActive ? 'bg-blue-100 text-blue-600 scale-110' : 'bg-white border border-slate-200 text-slate-500'
                                        }`}>
                                        <Upload size={28} />
                                    </div>
                                    <h3 className="text-[19px] font-bold text-slate-800 mb-2">
                                        {dragActive ? '¡Suelta tus videos aquí!' : 'Arrastra tus videos aquí'}
                                    </h3>
                                    <p className="text-slate-500 text-[15px] mb-6">o utiliza el botón para buscar en tu equipo</p>
                                    <Button
                                        onClick={() => inputRef.current?.click()}
                                        className="bg-slate-800 hover:bg-slate-700 text-white px-8 py-2.5 rounded-full font-medium shadow-md transition-all hover:shadow-lg hover:-translate-y-0.5 text-[15px]"
                                    >
                                        Seleccionar Archivos
                                    </Button>

                                    <div className="mt-8 pt-6 border-t border-slate-200/60 w-full max-w-sm text-center">
                                        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">Formatos Soportados</p>
                                        <div className="flex gap-2 justify-center flex-wrap">
                                            {['MP4', 'AVI', 'MOV', 'MKV', 'WEBM'].map((ext) => (
                                                <span key={ext} className="px-2.5 py-1 bg-white border border-slate-200/80 rounded-lg text-xs font-bold text-slate-500 shadow-sm">
                                                    {ext}
                                                </span>
                                            ))}
                                        </div>
                                        <p className="text-xs text-slate-400 mt-4 font-medium">Límite: {MAX_FILES} videos, 100MB por archivo, 60s máx</p>
                                    </div>
                                </>
                            ) : (
                                <div className="text-center">
                                    <div className="mx-auto w-12 h-12 rounded-xl bg-white border border-slate-200 flex items-center justify-center mb-3 text-slate-400 shadow-sm">
                                        <Plus size={24} />
                                    </div>
                                    <p className="text-[15px] text-slate-600 font-medium mb-4">Arrastra más videos o haz clic</p>
                                    <Button
                                        onClick={() => inputRef.current?.click()}
                                        variant="outline"
                                        className="rounded-full font-medium border-slate-300 text-slate-700 bg-white hover:bg-slate-50"
                                    >
                                        Agregar más archivos
                                    </Button>
                                </div>
                            )}
                        </div>
                    )}

                    {/* File list */}
                    {files.length > 0 && (
                        <div className="mt-6 space-y-3">
                            <div className="flex items-center justify-between mb-3 px-1">
                                <span className="text-[15px] font-bold text-slate-700">
                                    {files.length} video{files.length > 1 ? 's' : ''} seleccionado{files.length > 1 ? 's' : ''}
                                    <span className="text-slate-400 font-medium ml-2">
                                        ({(totalSize / (1024 * 1024)).toFixed(1)} MB)
                                    </span>
                                </span>
                                {files.length >= MAX_FILES && (
                                    <span className="text-[13px] text-amber-600 font-bold bg-amber-50 px-3 py-1 rounded-full border border-amber-200/60">
                                        Límite Completado
                                    </span>
                                )}
                            </div>

                            <div className="max-h-56 overflow-y-auto space-y-2 pr-2 custom-scrollbar">
                                {files.map((f, idx) => (
                                    <div key={f.id} className="flex items-center gap-4 p-4 bg-white rounded-2xl border border-slate-200 flex-row shadow-sm group hover:border-slate-300 transition-colors">
                                        <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center flex-shrink-0">
                                            <FileVideo className="w-5 h-5 text-slate-400" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-[15px] font-semibold text-slate-800 truncate" title={f.file.name}>
                                                {f.file.name}
                                            </p>
                                            <p className="text-xs font-medium text-slate-400 mt-0.5">
                                                {(f.file.size / (1024 * 1024)).toFixed(1)} MB
                                            </p>
                                        </div>
                                        <span className="text-xs font-bold text-slate-300 flex-shrink-0 w-8 text-right">#{idx + 1}</span>
                                        {!uploading && (
                                            <button
                                                onClick={() => removeFile(f.id)}
                                                className="p-2 ml-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-all opacity-0 group-hover:opacity-100 focus:opacity-100"
                                            >
                                                <Trash2 size={18} />
                                            </button>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Upload progress */}
                    {uploading && (
                        <div className="mt-6 space-y-4 p-6 bg-slate-50 rounded-[20px] border border-slate-200 shadow-sm animate-in fade-in slide-in-from-bottom-4 duration-500">
                            <div className="flex justify-between items-end">
                                <div>
                                    <span className="block font-bold text-slate-800 text-lg mb-1">
                                        Analizando...
                                    </span>
                                    <span className="text-sm font-medium text-slate-500">
                                        Subiendo {files.length} video{files.length > 1 ? 's' : ''} a la plataforma
                                    </span>
                                </div>
                                <span className="font-mono text-2xl font-black text-slate-800 tracking-tight">{progress}%</span>
                            </div>
                            <div className="h-3 w-full bg-slate-200/60 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-slate-800 transition-all duration-300 rounded-full"
                                    style={{ width: `${progress}%` }}
                                />
                            </div>
                            <p className="text-[13px] font-medium text-slate-400 flex items-center justify-center gap-2">
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse inline-block" />
                                {progress < 100 ? 'Por favor no cierres esta ventana' : 'Encolando procesamiento en el servidor...'}
                            </p>
                        </div>
                    )}

                    {/* Error display */}
                    {error && (
                        <div className="mt-6 flex items-start gap-3 text-rose-700 bg-rose-50 px-5 py-4 rounded-2xl border border-rose-200 shadow-sm animate-in fade-in">
                            <AlertCircle size={20} className="flex-shrink-0 mt-0.5" />
                            <span className="text-[15px] font-semibold">{error}</span>
                        </div>
                    )}

                    {/* Actions */}
                    {!uploading && files.length > 0 && (
                        <div className="mt-8 flex gap-3 justify-end pt-5 border-t border-slate-100">
                            <Button
                                onClick={() => {
                                    files.forEach(f => { if (f.previewUrl) URL.revokeObjectURL(f.previewUrl); });
                                    setFiles([]);
                                    setError(null);
                                }}
                                variant="ghost"
                                className="px-6 rounded-full font-medium text-slate-500 hover:text-slate-800 hover:bg-slate-100"
                            >
                                Limpiar todo
                            </Button>
                            <Button
                                onClick={handleUpload}
                                className="bg-slate-800 hover:bg-slate-700 text-white px-8 py-2.5 rounded-full font-medium shadow-md transition-all hover:shadow-lg hover:-translate-y-0.5 text-[15px] flex items-center gap-2"
                            >
                                <Upload size={18} />
                                {files.length === 1 ? 'Subir Video' : `Subir ${files.length} Videos`}
                            </Button>
                        </div>
                    )}

                </div>
            </DialogContent>
        </Dialog>
    );
}
