import { useEffect, useState, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { audioAnalysisService } from '../services/audioAnalysisService';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowLeft,
  Upload,
  Headphones,
  FileVideo,
  Loader2,
  CircleHelp,
  FileAudio,
  CheckCircle2,
  X,
  CloudUpload,
  Music2,
} from 'lucide-react';

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
      event.returnValue = 'Se esta subiendo un archivo. Si sales de esta pagina, la carga se cancelara.';
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [uploading]);

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
      const readDuration = (elementType: 'audio' | 'video') => new Promise<number>((resolve, reject) => {
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
      toast.error('Solo se permiten archivos de audio o video compatibles');
      return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      toast.error(`El archivo excede el maximo permitido de ${MAX_PROXY_UPLOAD_GB} GB`);
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
      toast.error('Selecciona un archivo de audio o video');
      return;
    }

    setUploading(true);
    setUploadProgress(0);

    try {
      setUploadPhase('Leyendo metadata del archivo...');
      const clientVideoDuration = await getMediaDurationSeconds(selectedFile);
      if (clientVideoDuration > MAX_DURATION_HOURS * 3600) {
        toast.error(`El archivo excede el máximo de ${MAX_DURATION_HOURS} horas`);
        return;
      }

      // Fase 1: Inicializar upload
      setUploadPhase('Inicializando...');
      const initResponse = await audioAnalysisService.iniciarUpload({
        filename: selectedFile.name,
        content_type: selectedFile.type || 'application/octet-stream',
        titulo: titulo.trim() || undefined,
        descripcion: descripcion.trim() || undefined,
        client_video_duration: clientVideoDuration,
      });

      if (!initResponse.success) {
        throw new Error(initResponse.error || 'Error inicializando upload');
      }

      const analysisId = initResponse.analysis_id;

      // Fase 2: Subir archivo
      // El upload directo requiere CORS configurado en el almacenamiento para el
      // origen actual. En desarrollo (localhost) y en producción con proxy, se
      // usa siempre la ruta segura a través del backend.
      setUploadPhase('Subiendo archivo...');

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
            (progress) => setUploadProgress(progress)
          );
        } catch {
          await audioAnalysisService.subirArchivoProxy(
            analysisId,
            selectedFile,
            (progress) => setUploadProgress(progress)
          );
        }
      } else {
        await audioAnalysisService.subirArchivoProxy(
          analysisId,
          selectedFile,
          (progress) => setUploadProgress(progress)
        );
      }

      // Fase 3: Completar upload e iniciar procesamiento
      setUploadPhase('Iniciando procesamiento de audio...');
      setUploadProgress(100);

      const completeResponse = await audioAnalysisService.completarUpload(
        analysisId,
        true,
        clientVideoDuration,
      );

      if (!completeResponse.success) {
        throw new Error('Error completando upload');
      }

      // Verificar duración
      if (completeResponse.video_duration > MAX_DURATION_HOURS * 3600) {
        toast.error(`El archivo excede el máximo de ${MAX_DURATION_HOURS} horas`);
        return;
      }

      toast.success('Archivo subido correctamente. El audio se está procesando...');
      navigate({ to: '/audio' });

    } catch (error: any) {
      const msg = error.response?.data?.error || error.message || 'Error subiendo archivo';
      toast.error(msg);
    } finally {
      setUploading(false);
      setUploadPhase('');
    }
  };

  const fileSizeMB = selectedFile ? (selectedFile.size / (1024 * 1024)).toFixed(1) : '0';
  const fileExt = selectedFile ? selectedFile.name.split('.').pop()?.toUpperCase() || '' : '';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-gray-50 to-stone-100">
      {/* Decorative top bar */}
      <div className="h-1 bg-gradient-to-r from-tivit-red via-red-400 to-rose-500" />

      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8">
        {/* Back navigation */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.3 }}
          className="mb-6"
        >
          <button
            onClick={() => navigate({ to: '/audio' })}
            className="flex items-center gap-2 text-gray-500 hover:text-gray-800 transition-colors group"
          >
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
            <span className="text-sm font-medium">Volver a Análisis de Audio</span>
          </button>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-sm border border-gray-100 overflow-hidden"
        >
          <div className="p-6 lg:p-8 space-y-7">
            {/* Header */}
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-tivit-red to-rose-600 flex items-center justify-center shadow-lg shadow-red-200/50">
                <Headphones className="w-6 h-6 text-white" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Nuevo Análisis de Audio</h1>
                  <details className="group">
                    <summary className="list-none cursor-pointer text-gray-400 hover:text-gray-600 inline-flex items-center transition-colors">
                      <CircleHelp className="w-4 h-4" />
                    </summary>
                    <div className="mt-2 p-3 text-sm text-gray-600 bg-gray-50 border border-gray-200 rounded-xl max-w-xl leading-relaxed">
                      Sube un archivo de audio o video, transcribimos su contenido con timestamps,
                      generamos un resumen y habilitamos consultas con IA.
                    </div>
                  </details>
                </div>
                <p className="text-sm text-gray-500 mt-0.5">Sube un archivo y lo procesaremos automáticamente</p>
              </div>
            </div>

            {/* File upload */}
            <div>
              <label className="flex items-center gap-1.5 text-sm font-semibold text-gray-700 mb-3">
                <FileAudio className="w-4 h-4 text-gray-400" />
                Archivo (audio o video) <span className="text-tivit-red">*</span>
              </label>

              <AnimatePresence mode="wait">
                {!selectedFile ? (
                  <motion.div
                    key="dropzone"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    onClick={() => fileInputRef.current?.click()}
                    onDragOver={(event) => {
                      event.preventDefault();
                      setIsDraggingFile(true);
                    }}
                    onDragLeave={() => setIsDraggingFile(false)}
                    onDrop={handleDrop}
                    className={`relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-300 ${isDraggingFile
                        ? 'border-tivit-red bg-red-50/50 scale-[1.01]'
                        : 'border-gray-200 hover:border-tivit-red/50 hover:bg-red-50/30'
                      }`}
                  >
                    <div className="flex flex-col items-center">
                      <div className={`w-16 h-16 rounded-2xl flex items-center justify-center mb-4 transition-colors duration-300 ${isDraggingFile ? 'bg-tivit-red/10' : 'bg-gray-100'
                        }`}>
                        <CloudUpload className={`w-8 h-8 transition-colors duration-300 ${isDraggingFile ? 'text-tivit-red' : 'text-gray-400'
                          }`} />
                      </div>
                      <p className="text-gray-800 font-semibold text-base">
                        {isDraggingFile ? '¡Suelta el archivo aquí!' : 'Arrastra y suelta tu archivo'}
                      </p>
                      <p className="text-sm text-gray-500 mt-1">
                        o <span className="text-tivit-red font-medium hover:underline">haz clic para seleccionar</span>
                      </p>
                      <div className="flex flex-wrap gap-1.5 justify-center mt-4">
                        {['MP4', 'MP3', 'WAV', 'M4A', 'MOV', 'FLAC', 'OGG'].map(ext => (
                          <span key={ext} className="px-2 py-0.5 bg-gray-100 text-gray-500 rounded text-[11px] font-medium">
                            {ext}
                          </span>
                        ))}
                        <span className="px-2 py-0.5 text-gray-400 text-[11px]">y más</span>
                      </div>
                      <p className="text-xs text-gray-400 mt-3">
                        Máximo {MAX_DURATION_HOURS} horas y {MAX_PROXY_UPLOAD_GB} GB por archivo
                      </p>
                    </div>
                  </motion.div>
                ) : (
                  <motion.div
                    key="file-selected"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="border border-gray-200 rounded-2xl p-4 flex items-center gap-4 bg-gray-50/50"
                  >
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-tivit-red/10 to-rose-100 flex items-center justify-center flex-shrink-0">
                      <Music2 className="w-6 h-6 text-tivit-red" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-gray-800 truncate">{selectedFile.name}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-xs text-gray-500">{fileSizeMB} MB</span>
                        {fileExt && (
                          <span className="px-1.5 py-0.5 bg-gray-200 text-gray-600 rounded text-[10px] font-semibold uppercase">
                            {fileExt}
                          </span>
                        )}
                        <span className="flex items-center gap-1 text-xs text-emerald-600">
                          <CheckCircle2 className="w-3 h-3" />
                          Listo para subir
                        </span>
                      </div>
                    </div>
                    {!uploading && (
                      <button
                        onClick={() => {
                          setSelectedFile(null);
                          if (fileInputRef.current) fileInputRef.current.value = '';
                        }}
                        className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:bg-red-100 hover:text-red-500 transition-all duration-200"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

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
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                Título <span className="text-gray-400 font-normal">(opcional)</span>
              </label>
              <input
                type="text"
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                placeholder="Se completa automaticamente con el nombre del archivo"
                className="w-full px-4 py-3 bg-gray-50/50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-tivit-red/20 focus:border-tivit-red/50 outline-none transition-all text-gray-800 placeholder:text-gray-400"
                disabled={uploading}
              />
            </div>

            {/* Descripción */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                Descripción <span className="text-gray-400 font-normal">(opcional)</span>
              </label>
              <textarea
                value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
                placeholder="Describe brevemente el contexto para mejorar las respuestas"
                rows={3}
                className="w-full px-4 py-3 bg-gray-50/50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-tivit-red/20 focus:border-tivit-red/50 outline-none transition-all resize-none text-gray-800 placeholder:text-gray-400"
                disabled={uploading}
              />
            </div>

            {/* Upload progress */}
            <AnimatePresence>
              {uploading && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="space-y-3 overflow-hidden"
                >
                  <div className="flex items-center gap-3 px-4 py-3 bg-red-50/50 rounded-xl border border-red-100">
                    <Loader2 className="w-5 h-5 text-tivit-red animate-spin" />
                    <span className="text-sm font-medium text-gray-700">{uploadPhase}</span>
                  </div>
                  <div className="relative">
                    <div className="w-full bg-gray-100 rounded-full h-3 overflow-hidden">
                      <motion.div
                        className="h-full bg-gradient-to-r from-tivit-red to-rose-500 rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${uploadProgress}%` }}
                        transition={{ duration: 0.3, ease: 'easeOut' }}
                      />
                    </div>
                    <p className="text-xs text-gray-500 text-right mt-1.5 font-medium">{uploadProgress}%</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Submit */}
            <div className="flex gap-3 pt-5 border-t border-gray-100">
              <button
                onClick={() => navigate({ to: '/audio' })}
                className="px-6 py-3 text-sm font-medium border border-gray-200 rounded-xl text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-all duration-200"
                disabled={uploading}
              >
                Cancelar
              </button>
              <motion.button
                whileHover={!uploading && selectedFile ? { scale: 1.01 } : {}}
                whileTap={!uploading && selectedFile ? { scale: 0.98 } : {}}
                onClick={handleUpload}
                disabled={!selectedFile || uploading}
                title={!selectedFile && !uploading ? 'Selecciona un archivo primero' : undefined}
                className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r from-tivit-red to-rose-600 text-white rounded-xl font-semibold shadow-lg shadow-red-200/40 hover:shadow-red-300/50 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none"
              >
                {uploading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Procesando...
                  </>
                ) : (
                  <>
                    <Upload className="w-5 h-5" />
                    Subir y Analizar Audio
                  </>
                )}
              </motion.button>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
