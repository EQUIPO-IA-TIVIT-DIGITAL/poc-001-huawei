import { useState, useRef, useEffect } from 'react';
import { getApiBaseUrl } from '../lib/backendUrl';
import {
    CloudUpload,
    Info,
    Check,
    AlertCircle,
    Video,
    FileVideo,
    Trash2,
    Upload as UploadIcon,
    FolderOpen,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { BatchNotification } from '../components/BatchNotification';
import { workspaceService, type Workspace } from '../services/workspace';

const MAX_UPLOAD_SIZE_MB = 100;
const MAX_DURATION_SECONDS = 60;
const MAX_FILES_PER_UPLOAD = 5;

export default function UploadPage() {
    const navigate = useNavigate();
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
            ? 'General'
            : workspaces.find((ws: Workspace) => ws.id === selectedWorkspace)?.nombre || 'General';

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
            setError('Ya tiene 5 videos analizando, espere que concluyan para enviar más');
            return;
        }

        const validExtensions = ['mp4', 'avi', 'mov', 'mkv', 'webm'];
        const valid: File[] = [];

        for (const file of incomingFiles) {
            const extension = file.name.split('.').pop()?.toLowerCase();
            if (!validExtensions.includes(extension || '')) {
                setError(`Formato no soportado en ${file.name}. Usa MP4, AVI, MOV, MKV o WEBM.`);
                return;
            }

            if (file.size > MAX_UPLOAD_SIZE_MB * 1024 * 1024) {
                setError(`El archivo ${file.name} excede el tamaño máximo de ${MAX_UPLOAD_SIZE_MB}MB.`);
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

        // Native XHR for progress
        const xhr = new XMLHttpRequest();
        const baseUrl = import.meta.env.VITE_API_BASE_URL || getApiBaseUrl();
        xhr.open('POST', `${baseUrl}/socio/batch-upload`, true);
        xhr.withCredentials = true; // Important for session cookies
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
                        toast.info('Videos cargados. El análisis se ejecuta en segundo plano.');
                        setUploading(false);
                    } else {
                        setError(response.error || 'Error al subir los videos');
                        setUploading(false);
                    }
                } catch (e) {
                    console.error('Error parsing response', e);
                    setError('Error al procesar la respuesta del servidor');
                    setUploading(false);
                }
            } else if (xhr.status === 401) {
                // Handle unauthorized directly
                console.warn('Unauthorized upload attempt. Redirecting...');
                localStorage.removeItem('accessfan_user');
                localStorage.removeItem('accessfan_token');
                window.dispatchEvent(new Event('auth:unauthorized'));
                setUploading(false);
                // Return early so we don't show the error message
                return;
            } else {
                try {
                    const response = JSON.parse(xhr.responseText);
                    setError(response.error || 'Error al subir los videos');
                } catch (e) {
                    console.error('Error upload', e);
                    setError('Error al subir los videos');
                }
                setUploading(false);
            }
        };

        xhr.onerror = function () {
            setError('Error de red al subir los videos');
            setUploading(false);
        };

        xhr.send(formData);
    };

    return (
        <div className="space-y-6 max-w-7xl mx-auto">
            <div className="flex items-center gap-3">
                <div className="p-3 bg-linear-to-br from-tivit-red to-red-600 rounded-2xl shadow-lg">
                    <CloudUpload size={28} className="text-white" strokeWidth={2} />
                </div>
                <div>
                    <h1 className="text-3xl font-bold text-gray-900">Subir Video</h1>
                    <p className="text-gray-500 mt-1">
                        Sube videos al proyecto {selectedWorkspaceName}
                    </p>
                </div>
            </div>

            <Card className="border border-gray-200 shadow-sm bg-white">
                <div className="p-4 flex flex-col sm:flex-row sm:items-center gap-3">
                    <label className="text-sm font-semibold text-gray-700 min-w-fit">
                        Proyecto destino
                    </label>
                    <select
                        value={selectedWorkspace}
                        onChange={(e) => setSelectedWorkspace(e.target.value)}
                        className="w-full sm:max-w-md px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-tivit-red/20 focus:border-tivit-red"
                    >
                        <option value="general">General (por defecto)</option>
                        {workspaces.map((ws: Workspace) => (
                            <option key={ws.id} value={ws.id}>
                                {ws.nombre}
                            </option>
                        ))}
                    </select>
                </div>
            </Card>

            {/* Upload Area */}
            <Card
                className={`relative border-2 border-dashed rounded-3xl overflow-hidden transition-all duration-300 ${
                    dragActive
                        ? 'border-tivit-red bg-tivit-red/10 shadow-xl shadow-tivit-red/20 scale-[1.02]'
                        : 'border-gray-300 bg-gray-50 hover:bg-gray-100/50 hover:border-gray-400'
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

                {/* Pulse animation overlay when dragging */}
                {dragActive && (
                    <div className="absolute inset-0 bg-linear-to-br from-tivit-red/5 via-tivit-red/10 to-tivit-red/5 animate-pulse pointer-events-none z-10" />
                )}

                {files.length === 0 ? (
                    <div className="relative z-20 flex flex-col items-center justify-center space-y-4 py-12 px-8">
                        <div
                            className={`relative flex h-20 w-20 items-center justify-center rounded-2xl bg-linear-to-br from-tivit-red to-red-600 text-white shadow-2xl shadow-tivit-red/30 mb-4 transition-all duration-300 cursor-pointer ${
                                dragActive ? 'scale-110 rotate-6' : 'hover:scale-105'
                            }`}
                            onClick={onButtonClick}
                        >
                            <CloudUpload
                                size={36}
                                className={`transition-transform duration-300 ${dragActive ? 'animate-bounce' : ''}`}
                            />
                            {dragActive && (
                                <div className="absolute inset-0 rounded-2xl border-4 border-tivit-red animate-ping opacity-75" />
                            )}
                        </div>
                        <h3 className="text-2xl font-bold text-gray-900">
                            {dragActive ? '¡Suelta el archivo aquí!' : 'Arrastra tu video aquí'}
                        </h3>
                        <p className="text-gray-500 font-medium">
                            o haz clic para seleccionar hasta {MAX_FILES_PER_UPLOAD} archivos
                        </p>

                        <div className="flex flex-wrap gap-2 mt-6 justify-center">
                            {['MP4', 'AVI', 'MOV', 'MKV', 'WEBM'].map((ext) => (
                                <span
                                    key={ext}
                                    className="px-3 py-1.5 bg-white border-2 border-gray-200 rounded-lg text-xs font-bold text-gray-600 shadow-sm hover:border-tivit-red hover:text-tivit-red transition-colors"
                                >
                                    .{ext}
                                </span>
                            ))}
                        </div>

                        <div className="mt-6 flex items-center gap-2 text-xs text-gray-400">
                            <Info size={14} />
                            <span>
                                Máximo {MAX_UPLOAD_SIZE_MB}MB • Duración recomendada hasta {MAX_DURATION_SECONDS}s
                            </span>
                        </div>
                    </div>
                ) : (
                    <div className="flex flex-col lg:flex-row items-center justify-center gap-8 py-8 px-8">
                        {/* Video Preview (first file) */}
                        {videoPreviewUrl && !uploading && !success && (
                            <div className="relative w-full lg:w-80 aspect-video bg-black rounded-xl overflow-hidden shadow-lg border-2 border-gray-200 animate-in fade-in zoom-in duration-500">
                                <video
                                    ref={videoPreviewRef}
                                    src={videoPreviewUrl}
                                    className="w-full h-full object-contain"
                                    controls
                                    muted
                                    playsInline
                                />
                                <div className="absolute top-2 right-2">
                                    <button
                                        onClick={() => setFiles([])}
                                        className="p-2 bg-red-500 hover:bg-red-600 text-white rounded-full shadow-lg transition-colors"
                                        title="Limpiar selección"
                                    >
                                        <Trash2 size={16} />
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* Upload States */}
                        <div className="flex-1 w-full max-w-md">
                            {uploading ? (
                                <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                                    {/* File Info */}
                                    <div className="flex items-center gap-4 p-4 bg-white rounded-xl border border-gray-200 shadow-sm">
                                        <div className="p-3 bg-tivit-red/10 rounded-lg">
                                            <Video className="w-6 h-6 text-tivit-red" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className="font-bold text-gray-900 truncate">
                                                {files.length > 1 ? `${files.length} videos seleccionados` : files[0]?.name}
                                            </p>
                                            <p className="text-sm text-gray-500">
                                                {files.reduce((acc, f) => acc + f.size, 0) / (1024 * 1024) >= 0
                                                    ? `${(files.reduce((acc, f) => acc + f.size, 0) / (1024 * 1024)).toFixed(2)} MB`
                                                    : '0 MB'}
                                            </p>
                                        </div>
                                    </div>

                                    {/* Progress Segmented */}
                                    <div className="space-y-3">
                                        {/* Upload Phase */}
                                        <div className="space-y-2">
                                            <div className="flex items-center justify-between text-sm">
                                                <span className="font-bold text-gray-700">
                                                    📤 Subiendo a servidor
                                                </span>
                                                <span className="font-mono text-tivit-red">
                                                    {progress}%
                                                </span>
                                            </div>
                                            <div className="h-3 w-full bg-gray-200 rounded-full overflow-hidden">
                                                <div
                                                    className="h-full bg-linear-to-r from-tivit-red via-red-500 to-red-600 transition-all duration-300 relative"
                                                    style={{ width: `${progress}%` }}
                                                >
                                                    <div className="absolute inset-0 bg-white/30 animate-pulse" />
                                                </div>
                                            </div>
                                        </div>

                                        {/* Processing Phase (Pending) */}
                                        <div className="space-y-2 opacity-50">
                                            <div className="flex items-center justify-between text-sm">
                                                <span className="font-bold text-gray-600">
                                                    🔍 Análisis con IA
                                                </span>
                                                <span className="text-xs text-gray-500">
                                                    Siguiente
                                                </span>
                                            </div>
                                            <div className="h-3 w-full bg-gray-200 rounded-full" />
                                        </div>
                                    </div>

                                    <p className="text-xs text-center text-gray-500 italic">
                                        Por favor espera, esto puede tomar unos segundos...
                                    </p>
                                </div>
                            ) : success ? (
                                <div className="text-center space-y-4 animate-in fade-in zoom-in duration-500">
                                    <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-linear-to-br from-green-400 to-green-600 text-white mb-4 shadow-xl shadow-green-200">
                                        <Check size={40} strokeWidth={3} />
                                    </div>
                                    <h3 className="text-2xl font-bold text-gray-900">
                                        ¡Subido con Éxito!
                                    </h3>
                                    <p className="text-gray-600">Tus videos se están analizando en segundo plano.</p>
                                    <Button
                                        onClick={() => setSuccess(false)}
                                        variant="outline"
                                        className="mt-4 border-2"
                                    >
                                        Subir más videos
                                    </Button>
                                </div>
                            ) : (
                                <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-500">
                                    {/* File Info Card */}
                                    <div className="p-6 bg-linear-to-br from-gray-50 to-gray-100 rounded-xl border-2 border-gray-200 shadow-sm">
                                        <div className="flex items-start gap-4">
                                            <div className="p-3 bg-tivit-red/10 rounded-xl">
                                                <FileVideo className="w-8 h-8 text-tivit-red" />
                                            </div>
                                            <div className="flex-1">
                                                <h4 className="font-bold text-gray-900 text-lg mb-1">
                                                    Videos Seleccionados
                                                </h4>
                                                <p className="text-sm text-gray-600 font-medium truncate">
                                                    {files.length > 1 ? `${files.length} archivos listos` : files[0]?.name}
                                                </p>
                                                <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
                                                    <span className="flex items-center gap-1">
                                                        <div className="w-2 h-2 bg-blue-500 rounded-full" />
                                                        {(files.reduce((acc, f) => acc + f.size, 0) / (1024 * 1024)).toFixed(2)} MB
                                                    </span>
                                                    <span className="flex items-center gap-1">
                                                        <div className="w-2 h-2 bg-green-500 rounded-full" />
                                                        {files.length} archivo{files.length > 1 ? 's' : ''}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Info Message */}
                                    <div className="p-4 bg-gray-50 rounded-xl border border-gray-200">
                                        <p className="text-sm text-gray-600">
                                            <span className="font-semibold text-gray-900">
                                                Nota:
                                            </span>{' '}
                                            Los videos se guardarán en el proyecto{' '}
                                            <span className="font-semibold">{selectedWorkspaceName}</span>.
                                        </p>
                                    </div>

                                    {/* Action Buttons */}
                                    <div className="flex gap-3">
                                        <Button
                                            onClick={() => setFiles([])}
                                            variant="outline"
                                            className="flex-1 border-2 hover:bg-gray-50"
                                        >
                                            <Trash2 className="w-4 h-4 mr-2" />
                                            Cancelar
                                        </Button>
                                        <Button
                                            onClick={handleUpload}
                                            className="flex-1 bg-linear-to-r from-tivit-red to-red-600 hover:from-red-600 hover:to-red-700 text-white font-bold shadow-lg shadow-tivit-red/30"
                                        >
                                            <CloudUpload className="w-4 h-4 mr-2" />
                                            Subir {files.length} video{files.length > 1 ? 's' : ''}
                                        </Button>
                                    </div>
                                </div>
                            )}
                            {error && (
                                <div className="flex items-center gap-3 text-red-600 bg-red-50 px-4 py-3 rounded-xl border-2 border-red-200 shadow-sm animate-in fade-in shake duration-500">
                                    <AlertCircle size={20} />
                                    <span className="text-sm font-bold">{error}</span>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </Card>

            {/* Info Card */}
            <Card className="border-none shadow-sm bg-white">
                <div className="p-6">
                    <div className="flex items-center gap-2 mb-4 text-blue-600">
                        <Info size={20} fill="currentColor" className="text-blue-600" />
                        <h3 className="font-bold text-gray-900">Información Importante</h3>
                    </div>
                    <ul className="space-y-2 text-sm text-gray-600 list-disc pl-5 marker:text-gray-400">
                        <li>
                            <span className="font-bold text-gray-700">Análisis automático:</span> Tu
                            video será procesado por 5 etapas de IA (preparación, verificación,
                            escaneo rápido, análisis profundo y decisión final)
                        </li>
                        <li>
                            <span className="font-bold text-gray-700">
                                Tiempo de procesamiento:
                            </span>{' '}
                            El análisis completo toma entre 2-5 minutos dependiendo de la duración
                            del video
                        </li>
                        <li>
                            <span className="font-bold text-gray-700">Título automático:</span> Se
                            generará un título inteligente basado en el contenido detectado
                        </li>
                        <li>
                            <span className="font-bold text-gray-700">Notificaciones:</span>{' '}
                            Recibirás una actualización cuando tu video sea revisado por el
                            administrador
                        </li>
                        <li>
                            <span className="font-bold text-gray-700">Límites:</span> Tamaño máximo
                            {' '}{MAX_UPLOAD_SIZE_MB}MB | Duración máxima {MAX_DURATION_SECONDS} segundos
                        </li>
                        <li>
                            <span className="font-bold text-gray-700">Formatos soportados:</span>{' '}
                            MP4, AVI, MOV, MKV, WEBM
                        </li>
                    </ul>
                </div>
            </Card>

            {activeBatchId && showBatchNotification && (
                <BatchNotification
                    batchId={activeBatchId}
                    onClose={() => setShowBatchNotification(false)}
                    onComplete={() => {
                        toast.success('Análisis de lote completado');
                        setActiveBatchId(null);
                    }}
                />
            )}
        </div>
    );
}