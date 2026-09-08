import { useState, useEffect } from 'react';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { operationalVideoService, OperationalAnalysisType, TimeEstimate } from '../services/operationalVideoService';
import { videoCompressionService, CompressionProgress } from '../services/videoCompressionService';
import { toast } from 'sonner';
import { Upload, Activity, AlertCircle, CheckCircle, Loader2, Clock, BarChart3 } from 'lucide-react';

export default function OperationalUpload() {
  const navigate = useNavigate();
  const search = useSearch({ strict: false }) as { analysisType?: string };

  // Types
  const [types, setTypes] = useState<Record<string, OperationalAnalysisType>>({});
  const [selectedType, setSelectedType] = useState<string>('');
  const [customContext, setCustomContext] = useState('');
  const [maxContextLength] = useState(2000);

  // File
  const [file, setFile] = useState<File | null>(null);
  const [enableCompression, setEnableCompression] = useState(true);

  // Upload state
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'loading-ffmpeg' | 'compressing' | 'uploading' | 'processing' | 'completed'>('idle');
  const [compressionProgress, setCompressionProgress] = useState<CompressionProgress | null>(null);
  const [originalSize, setOriginalSize] = useState(0);
  const [compressedSize, setCompressedSize] = useState(0);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Time estimation
  const [timeEstimate, setTimeEstimate] = useState<TimeEstimate | null>(null);

  useEffect(() => {
    operationalVideoService.listarTipos().then(setTypes).catch(() => {
      toast.error('Error cargando tipos de análisis');
    });
  }, []);

  useEffect(() => {
    if (!search.analysisType || !types || Object.keys(types).length === 0) return;
    if (types[search.analysisType]) {
      setSelectedType(search.analysisType);
    }
  }, [search.analysisType, types]);

  // Estimate processing time when type + file are selected
  useEffect(() => {
    if (selectedType && file) {
      operationalVideoService.estimarTiempo({
        analysis_type: selectedType,
        file_size_mb: file.size / (1024 * 1024),
      }).then(setTimeEstimate).catch(() => setTimeEstimate(null));
    } else {
      setTimeEstimate(null);
    }
  }, [selectedType, file]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      if (!selectedFile.type.startsWith('video/')) {
        toast.error('Por favor selecciona un archivo de video válido');
        return;
      }
      const maxSize = 100 * 1024 * 1024 * 1024;
      if (selectedFile.size > maxSize) {
        toast.error('El archivo es demasiado grande (máximo 100 GB)');
        return;
      }
      if (selectedFile.size > 50 * 1024 * 1024 * 1024) {
        setEnableCompression(false);
      }
      setFile(selectedFile);
      toast.success(`Archivo seleccionado: ${formatFileSize(selectedFile.size)}`);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!file) {
      toast.error('Selecciona un archivo de video');
      return;
    }
    if (!selectedType) {
      toast.error('Selecciona un tipo de análisis');
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setOriginalSize(file.size);
    setSubmitError(null);

    try {
      let fileToUpload = file;

      // Compresión opcional
      if (enableCompression && file.size > 500 * 1024 * 1024) {
        setUploadStatus('loading-ffmpeg');
        await videoCompressionService.initialize((progress) => {
          setCompressionProgress(progress);
        });

        setUploadStatus('compressing');
        toast.info('Comprimiendo video...');
        const result = await videoCompressionService.compressVideo(file, (progress) => {
          setCompressionProgress(progress);
        });
        fileToUpload = result.compressedFile;
        setCompressedSize(result.compressedSize);
        toast.success(`Comprimido: ${result.reductionPercent.toFixed(1)}% reducción`);
      } else {
        setCompressedSize(file.size);
      }

      setUploadStatus('uploading');

      // Paso 1: Iniciar upload
      toast.info('Iniciando upload...');
      const initResponse = await operationalVideoService.iniciarUpload({
        filename: fileToUpload.name,
        content_type: fileToUpload.type,
        analysis_type: selectedType,
        custom_context: customContext,
      });

      if (!initResponse.success) {
        throw new Error(initResponse.error || 'Error iniciando upload');
      }

      toast.success('Upload iniciado');

      // Paso 2: Subir archivo
      toast.info('Subiendo archivo...');
      await operationalVideoService.subirArchivoProxy(
        initResponse.analysis_id,
        fileToUpload,
        (percentage) => setUploadProgress(percentage)
      );

      toast.success('Archivo subido');
      setUploadStatus('processing');

      // Paso 3: Completar e iniciar análisis
      toast.info('Iniciando análisis...');
      const completeResponse = await operationalVideoService.completarUpload(initResponse.analysis_id);

      if (completeResponse.success) {
        setUploadStatus('completed');
        toast.success('¡Video subido! El análisis comenzará automáticamente.');
      } else {
        toast.warning('Video subido pero hubo un problema al iniciar el análisis');
      }

      setTimeout(() => {
        navigate({ to: '/operational' });
      }, 2000);

    } catch (error: any) {
      console.error('Error en upload:', error);
      const msg = error.message || 'Error subiendo el video';
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
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const selectedTypeInfo = selectedType ? types[selectedType] : null;
  const contextOverLimit = customContext.length > maxContextLength;

  // ── Progreso: valores computados fuera del JSX ──
  const hasCompression = enableCompression && !!file && file.size > 500 * 1024 * 1024;
  const allProgressSteps: { key: typeof uploadStatus; label: string }[] = hasCompression
    ? [
      { key: 'loading-ffmpeg', label: 'Preparando' },
      { key: 'compressing', label: 'Comprimiendo' },
      { key: 'uploading', label: 'Subiendo' },
      { key: 'processing', label: 'Procesando' },
      { key: 'completed', label: 'Completado' },
    ]
    : [
      { key: 'uploading', label: 'Subiendo' },
      { key: 'processing', label: 'Procesando' },
      { key: 'completed', label: 'Completado' },
    ];
  const progressCurrentIdx = allProgressSteps.findIndex(s => s.key === uploadStatus);
  const progressPct =
    uploadStatus === 'loading-ffmpeg' ? 5 :
      uploadStatus === 'compressing' ? 5 + (compressionProgress?.percent ?? 0) * 0.25 :
        uploadStatus === 'uploading' ? (hasCompression ? 30 : 0) + uploadProgress * (hasCompression ? 0.5 : 0.8) :
          uploadStatus === 'processing' ? 85 :
            uploadStatus === 'completed' ? 100 : 0;
  const progressLabel =
    uploadStatus === 'loading-ffmpeg' ? 'Cargando compresor...' :
      uploadStatus === 'compressing' ? (compressionProgress?.message ?? 'Comprimiendo video...') :
        uploadStatus === 'uploading' ? `Subiendo video — ${uploadProgress}%` :
          uploadStatus === 'processing' ? 'Iniciando análisis...' :
            uploadStatus === 'completed' ? '¡Listo! Redirigiendo...' : '';

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <div className="flex items-center gap-3 mb-2">
            <Activity className="w-8 h-8 text-tivit-red" />
            <h1 className="text-3xl font-bold text-gray-800">
              Nuevo Análisis Operativo
            </h1>
          </div>
          <p className="text-gray-600">
            Sube un video y define qué quieres saber — la IA analizará el contenido con tu contexto
          </p>
        </div>

        {/* Step indicator */}
        <div className="bg-white rounded-lg shadow-sm p-4 mb-6">
          <div className="flex items-center justify-between">
            {['Tipo de análisis', 'Contexto', 'Video', 'Confirmar'].map((step, idx) => {
              const isComplete = idx === 0 ? !!selectedType : idx === 1 ? true : idx === 2 ? !!file : false;
              return (
                <div key={step} className="flex items-center gap-2">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${isComplete ? 'bg-tivit-red text-white' : 'bg-gray-200 text-gray-500'}`}>
                    {isComplete ? <CheckCircle className="w-4 h-4" /> : idx + 1}
                  </div>
                  <span className={`text-sm hidden md:inline ${isComplete ? 'text-red-700 font-medium' : 'text-gray-400'}`}>{step}</span>
                  {idx < 3 && <div className={`w-8 lg:w-16 h-0.5 ${isComplete ? 'bg-red-400' : 'bg-gray-200'}`} />}
                </div>
              );
            })}
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow-md p-6">
          {/* Banner éxito */}
          {uploadStatus === 'completed' && (
            <div className="mb-6 bg-green-50 border-2 border-green-500 rounded-lg p-4 animate-pulse">
              <div className="flex items-center gap-3">
                <CheckCircle className="w-6 h-6 text-green-600 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-green-900">¡Video subido exitosamente!</p>
                  <p className="text-sm text-green-700 mt-1">El análisis comenzará automáticamente. Redirigiendo...</p>
                </div>
              </div>
            </div>
          )}

          <div className="space-y-6">
            {/* Tipo de análisis */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Tipo de Análisis *
              </label>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(types).map(([key, info]) => (
                  <button
                    key={key}
                    type="button"
                    disabled={uploading}
                    onClick={() => setSelectedType(key)}
                    className={`p-4 border-2 rounded-lg text-center transition-all ${selectedType === key
                        ? 'border-tivit-red bg-red-50 ring-2 ring-red-200'
                        : 'border-gray-200 hover:border-red-300 hover:bg-red-50/50'
                      } ${uploading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                  >
                    <div className="text-2xl mb-1">{info.icon}</div>
                    <div className="text-sm font-semibold text-gray-800">{info.name}</div>
                    <div className="text-xs text-gray-500 mt-1">{info.description}</div>
                  </button>
                ))}
              </div>

              {/* Key metrics for selected type */}
              {selectedTypeInfo && selectedTypeInfo.key_metrics && selectedTypeInfo.key_metrics.length > 0 && (
                <div className="mt-4 p-3 bg-red-50 rounded-lg border border-red-100">
                  <p className="text-xs font-medium text-red-700 mb-2 flex items-center gap-1">
                    <BarChart3 className="w-3 h-3" /> Métricas que obtendrás:
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {selectedTypeInfo.key_metrics.map((metric: string, i: number) => (
                      <span key={i} className="px-2 py-1 bg-white text-red-700 text-xs rounded-full border border-red-200">
                        {metric}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Contexto personalizado */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                ¿Qué quieres saber? (Contexto)
              </label>
              <textarea
                value={customContext}
                onChange={(e) => setCustomContext(e.target.value)}
                disabled={uploading}
                rows={3}
                maxLength={maxContextLength + 100}
                placeholder="Ej: Quiero saber cuántas personas entraron y salieron por la puerta principal, cuántas usaron fotcheck, y si hubo accesos no autorizados"
                className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-tivit-red focus:border-transparent resize-none disabled:opacity-50 transition-colors ${contextOverLimit ? 'border-red-400 bg-red-50' : 'border-gray-300'
                  }`}
              />
              <div className="flex justify-between items-center mt-1">
                <p className="text-xs text-gray-500">
                  Sé específico — entre más detalle des, mejor será el análisis
                </p>
                <span className={`text-xs font-mono ${contextOverLimit ? 'text-red-600 font-semibold' : customContext.length > maxContextLength * 0.8 ? 'text-yellow-600' : 'text-gray-400'}`}>
                  {customContext.length}/{maxContextLength}
                </span>
              </div>
              {contextOverLimit && (
                <p className="text-xs text-red-600 mt-1">
                  El contexto excede el límite de {maxContextLength} caracteres
                </p>
              )}
            </div>

            {/* Selección de archivo */}
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
                <Upload className="w-4 h-4" />
                Archivo de Video *
              </label>
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-red-400 transition-colors">
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
                  className={`cursor-pointer ${uploading ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <Upload className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                  {file ? (
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-gray-700">{file.name}</p>
                      <p className="text-xs text-gray-500">{formatFileSize(file.size)}</p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-sm text-gray-600">Click para seleccionar un video</p>
                      <p className="text-xs text-gray-500 mt-1">MP4, MOV, AVI — hasta 100 GB</p>
                    </div>
                  )}
                </label>
              </div>
            </div>

            {/* Opción de compresión */}
            {file && file.size > 500 * 1024 * 1024 && (
              <div className="border rounded-lg p-4 bg-yellow-50 border-yellow-200">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-yellow-900">Video grande detectado</p>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={enableCompression}
                      onChange={(e) => setEnableCompression(e.target.checked)}
                      disabled={uploading}
                      className="w-4 h-4 text-tivit-red rounded"
                    />
                    <span className="text-sm text-gray-700">Comprimir antes de subir</span>
                  </label>
                </div>
              </div>
            )}

            {/* Time Estimation */}
            {timeEstimate && (
              <div className="p-4 bg-gradient-to-r from-red-50 to-orange-50 rounded-lg border border-red-200">
                <div className="flex items-start gap-3">
                  <Clock className="w-5 h-5 text-tivit-red mt-0.5 flex-shrink-0" />
                  <div className="flex-1">
                    <p className="font-semibold text-red-900 text-sm mb-2">Tiempo estimado de procesamiento</p>
                    <div className="grid grid-cols-3 gap-3">
                      <div className="bg-white/70 rounded-lg p-2 text-center">
                        <p className="text-xl font-bold text-red-700">
                          {timeEstimate.estimated_range.min_minutes.toFixed(0)}–{timeEstimate.estimated_range.max_minutes.toFixed(0)}
                        </p>
                        <p className="text-xs text-gray-500">min. aprox.</p>
                      </div>
                      <div className="bg-white/70 rounded-lg p-2 text-center">
                        <p className="text-lg font-semibold text-gray-700">{timeEstimate.breakdown.upload_minutes.toFixed(1)}</p>
                        <p className="text-xs text-gray-500">min subida</p>
                      </div>
                      <div className="bg-white/70 rounded-lg p-2 text-center">
                        <p className="text-lg font-semibold text-gray-700">{timeEstimate.breakdown.analysis_minutes.toFixed(1)}</p>
                        <p className="text-xs text-gray-500">min análisis</p>
                      </div>
                    </div>
                    <p className="text-xs text-tivit-red mt-2">
                      Puedes cerrar esta ventana — recibirás una notificación al completarse
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* ── Progreso unificado ── */}
            {uploading && (
              <div className="border border-gray-200 rounded-xl p-5 bg-gray-50 space-y-4">
                {/* Pasos */}
                <div className="flex items-center justify-between">
                  {allProgressSteps.map((step, idx) => {
                    const done = idx < progressCurrentIdx;
                    const active = idx === progressCurrentIdx;
                    return (
                      <div key={step.key} className="flex flex-col items-center gap-1 flex-1">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${done ? 'bg-green-500 text-white' :
                            active ? 'bg-tivit-red text-white ring-4 ring-red-100' :
                              'bg-gray-200 text-gray-400'
                          }`}>
                          {done ? <CheckCircle className="w-4 h-4" /> :
                            active ? <Loader2 className="w-4 h-4 animate-spin" /> :
                              idx + 1}
                        </div>
                        <span className={`text-xs text-center leading-tight hidden sm:block ${done ? 'text-green-600 font-medium' :
                            active ? 'text-red-700 font-semibold' :
                              'text-gray-400'
                          }`}>{step.label}</span>
                      </div>
                    );
                  })}
                </div>

                {/* Barra de progreso */}
                <div>
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span className="font-medium text-gray-700">{progressLabel}</span>
                    <span className="font-mono font-semibold">{Math.round(progressPct)}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${uploadStatus === 'completed' ? 'bg-green-500' : 'bg-tivit-red'}`}
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                </div>

                {/* Ahorro de compresión */}
                {originalSize > 0 && compressedSize > 0 && compressedSize < originalSize && (
                  <p className="text-xs text-green-700 text-center">
                    📦 Ahorro: {((originalSize - compressedSize) / (1024 * 1024)).toFixed(1)} MB tras compresión
                  </p>
                )}
              </div>
            )}

            {/* Mensaje de error inline */}
            {submitError && (
              <div className="flex items-start gap-3 bg-red-50 border border-red-300 rounded-lg p-4">
                <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-red-800">Error al subir el video</p>
                  <p className="text-sm text-red-700 mt-0.5">{submitError}</p>
                </div>
              </div>
            )}

            {/* Mensaje de éxito inline */}
            {uploadStatus === 'completed' && (
              <div className="flex items-start gap-3 bg-green-50 border border-green-400 rounded-lg p-4">
                <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-green-800">¡Video subido correctamente!</p>
                  <p className="text-sm text-green-700 mt-0.5">El análisis comenzará automáticamente. Redirigiendo...</p>
                </div>
              </div>
            )}

            {/* Botones */}
            <div className="flex gap-4 pt-4">
              <button
                type="submit"
                disabled={uploading || !file || !selectedType || contextOverLimit}
                className={`flex-1 py-3 px-6 rounded-lg font-medium transition-all flex items-center justify-center gap-2 ${uploadStatus === 'completed'
                    ? 'bg-green-600 hover:bg-green-700 text-white'
                    : 'bg-tivit-red hover:bg-tivit-red-dark text-white disabled:opacity-50 disabled:cursor-not-allowed'
                  }`}
              >
                {uploadStatus === 'loading-ffmpeg' && <><Loader2 className="w-5 h-5 animate-spin" />Cargando FFmpeg...</>}
                {uploadStatus === 'compressing' && <><Loader2 className="w-5 h-5 animate-spin" />Comprimiendo...</>}
                {uploadStatus === 'uploading' && <><Loader2 className="w-5 h-5 animate-spin" />Subiendo...</>}
                {uploadStatus === 'processing' && <><Loader2 className="w-5 h-5 animate-spin" />Procesando...</>}
                {uploadStatus === 'completed' && <><CheckCircle className="w-5 h-5" />Completado</>}
                {uploadStatus === 'idle' && 'Subir y Analizar'}
              </button>
              <button
                type="button"
                onClick={() => navigate({ to: '/operational' })}
                disabled={uploading}
                className="px-6 py-3 border border-gray-300 rounded-lg font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
              >
                Cancelar
              </button>
            </div>
          </div>
        </form>

        {/* Info */}
        <div className="mt-6 bg-gray-50 rounded-lg p-4">
          <h3 className="font-semibold text-gray-800 mb-2">Información importante:</h3>
          <ul className="text-sm text-gray-600 space-y-1 list-disc ml-5">
            <li>Los reportes incluyen capturas HD de cada evento detectado</li>
            <li>Cada evento tiene: descripción, dirección, objetos, timestamp y frames</li>
            <li>El análisis consolida todos los segmentos en un reporte unificado</li>
            <li>Los videos se guardan por 7 días y los reportes por 30 días</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
