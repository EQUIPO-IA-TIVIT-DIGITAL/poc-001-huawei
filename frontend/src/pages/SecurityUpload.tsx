import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { securityVideoService } from '../services/securityVideoService';
import { videoCompressionService, CompressionProgress } from '../services/videoCompressionService';
import { toast } from 'sonner';
import { Upload, Video, AlertCircle, CheckCircle, Loader2 } from 'lucide-react';

export default function SecurityUpload() {
  const navigate = useNavigate();

  // Form data
  const [file, setFile] = useState<File | null>(null);
  const [enableCompression, setEnableCompression] = useState(true); // Compresión activada por defecto

  // Upload state
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentVideoId, setCurrentVideoId] = useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'loading-ffmpeg' | 'compressing' | 'uploading' | 'processing' | 'completed'>('idle');
  
  // Compression state
  const [compressionProgress, setCompressionProgress] = useState<CompressionProgress | null>(null);
  const [originalSize, setOriginalSize] = useState<number>(0);
  const [compressedSize, setCompressedSize] = useState<number>(0);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];

      // Validar que sea un video
      if (!selectedFile.type.startsWith('video/')) {
        toast.error('Por favor selecciona un archivo de video válido');
        return;
      }

      // Validar tamaño máximo (100 GB)
      const maxSize = 100 * 1024 * 1024 * 1024; // 100 GB
      if (selectedFile.size > maxSize) {
        toast.error('El archivo es demasiado grande (máximo 100 GB)');
        return;
      }

      // Warning para videos muy grandes (>50GB ≈ >12h)
      const LARGE_VIDEO_THRESHOLD = 50 * 1024 * 1024 * 1024; // 50GB
      if (selectedFile.size > LARGE_VIDEO_THRESHOLD) {
        toast.warning(
          'Video muy grande detectado (>50GB). La compresión en navegador puede ser muy lenta. ' +
          'Se recomienda deshabilitar la compresión y subir directamente.',
          { duration: 8000 }
        );
        // Deshabilitar compresión automáticamente para videos muy grandes
        setEnableCompression(false);
      }

      setFile(selectedFile);
      
      const sizeGB = selectedFile.size / (1024 * 1024 * 1024);
      const sizeDisplay = sizeGB >= 1 
        ? `${sizeGB.toFixed(2)} GB`
        : `${(selectedFile.size / (1024 * 1024)).toFixed(0)} MB`;
      
      toast.success(`Archivo seleccionado: ${sizeDisplay}`);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!file) {
      toast.error('Por favor selecciona un archivo de video');
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setOriginalSize(file.size);

    try {
      let fileToUpload = file;

      // Paso 0 (opcional): Comprimir video si está habilitado
      if (enableCompression) {
        const COMPRESS_THRESHOLD = 500 * 1024 * 1024; // 500MB
        const shouldCompress = file.size > COMPRESS_THRESHOLD;

        if (shouldCompress) {
          toast.info('Video grande detectado. Iniciando compresión...');
          setUploadStatus('loading-ffmpeg');

          // Inicializar FFmpeg
          await videoCompressionService.initialize((progress) => {
            setCompressionProgress(progress);
            if (progress.phase === 'loading') {
              setUploadStatus('loading-ffmpeg');
            }
          });

          // Comprimir video
          setUploadStatus('compressing');
          toast.info('Comprimiendo video para acelerar el upload...');

          const result = await videoCompressionService.compressVideo(file, (progress) => {
            setCompressionProgress(progress);
          });

          fileToUpload = result.compressedFile;
          setCompressedSize(result.compressedSize);
          
          const reductionMB = (result.originalSize - result.compressedSize) / (1024 * 1024);
          toast.success(
            `Video comprimido: ${result.reductionPercent.toFixed(1)}% reducción (ahorro: ${reductionMB.toFixed(1)} MB)`,
            { duration: 5000 }
          );
        } else {
          toast.info('Video de tamaño moderado, no requiere compresión');
          setCompressedSize(file.size);
        }
      } else {
        setCompressedSize(file.size);
      }

      setUploadStatus('uploading');

      // Paso 1: Iniciar upload y crear registro
      toast.info('Iniciando upload...');

      const initResponse = await securityVideoService.iniciarUpload({
        filename: fileToUpload.name,
        content_type: fileToUpload.type,
      });

      if (!initResponse.success) {
        throw new Error(initResponse.error || 'Error iniciando upload');
      }

      setCurrentVideoId(initResponse.video_id);
      toast.success('Upload iniciado correctamente');

      // Paso 2: Subir archivo via backend (proxy) para evitar CORS
      toast.info('Subiendo archivo via servidor...');

      await securityVideoService.subirArchivoProxy(
        initResponse.video_id,
        fileToUpload,
        (percentage) => {
          setUploadProgress(percentage);
        }
      );

      toast.success('Archivo subido correctamente');
      setUploadStatus('processing');

      // Paso 3: Confirmar upload y iniciar procesamiento automático
      toast.info('Iniciando análisis del video...');

      const completeResponse = await securityVideoService.completarUpload(initResponse.video_id);

      if (completeResponse.success) {
        setUploadStatus('completed');
        toast.success('¡Video de seguridad subido! El análisis comenzará automáticamente.');
      } else {
        toast.warning('Video subido pero hubo un problema al iniciar el análisis');
      }

      // Esperar 2 segundos antes de redirigir
      setTimeout(() => {
        navigate({ to: '/security' });
      }, 2000);

    } catch (error: any) {
      console.error('Error en upload:', error);
      toast.error(error.message || 'Error subiendo el video');
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <div className="flex items-center gap-3 mb-2">
            <Video className="w-8 h-8 text-blue-600" />
            <h1 className="text-3xl font-bold text-gray-800">
              Subir Video de Seguridad
            </h1>
          </div>
          <p className="text-gray-600">
            Sube un video y deja que el sistema haga el análisis completo automaticamente
          </p>
        </div>

        {/* Información del proceso */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
            <div className="text-sm text-blue-800">
              <p className="font-semibold mb-2">Proceso de análisis automático:</p>
              <ol className="list-decimal ml-4 space-y-1">
                <li>Detección de movimiento y filtrado de segmentos</li>
                <li>Analisis profundo del contenido con IA</li>
                <li>Generacion de reporte final</li>
              </ol>
              <p className="mt-2 text-xs">
                ⏱️ Tiempo estimado: 35-45 minutos para un video de 12 horas
              </p>
              <p className="mt-2 text-xs">
                Te avisamos en la app cuando el reporte este listo
              </p>
            </div>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow-md p-6">
          {/* Banner de éxito */}
          {uploadStatus === 'completed' && (
            <div className="mb-6 bg-green-50 border-2 border-green-500 rounded-lg p-4 animate-pulse">
              <div className="flex items-center gap-3">
                <CheckCircle className="w-6 h-6 text-green-600 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-green-900">¡Video subido exitosamente!</p>
                  <p className="text-sm text-green-700 mt-1">
                    El análisis comenzará automáticamente. Redirigiendo...
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="space-y-6">
            {/* Selección de archivo */}
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
                <Upload className="w-4 h-4" />
                Archivo de Video
              </label>
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-400 transition-colors">
                <input
                  type="file"
                  accept="video/*"
                  onChange={handleFileChange}
                  className="hidden"
                  id="video-file"
                  disabled={uploading}
                />
                <label
                  htmlFor="video-file"
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
                      <p className="text-sm text-gray-600">
                        Click para seleccionar un video
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        Soporta videos de hasta 100 GB (MP4, MOV, AVI, etc.)
                      </p>
                    </div>
                  )}
                </label>
              </div>
            </div>

            {/* Opción de compresión */}
            {file && file.size > 500 * 1024 * 1024 && (
              <div className={`border rounded-lg p-4 ${
                file.size > 50 * 1024 * 1024 * 1024 
                  ? 'bg-red-50 border-red-200' 
                  : 'bg-yellow-50 border-yellow-200'
              }`}>
                <div className="flex items-start gap-3">
                  <AlertCircle className={`w-5 h-5 mt-0.5 flex-shrink-0 ${
                    file.size > 50 * 1024 * 1024 * 1024 
                      ? 'text-red-600' 
                      : 'text-yellow-600'
                  }`} />
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-2">
                      <p className={`font-semibold ${
                        file.size > 50 * 1024 * 1024 * 1024 
                          ? 'text-red-900' 
                          : 'text-yellow-900'
                      }`}>
                        {file.size > 50 * 1024 * 1024 * 1024 
                          ? '⚠️ Video muy grande (>50GB ≈ >12h)' 
                          : 'Video grande detectado'}
                      </p>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={enableCompression}
                          onChange={(e) => setEnableCompression(e.target.checked)}
                          disabled={uploading}
                          className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500"
                        />
                        <span className="text-sm font-medium text-gray-700">
                          Comprimir antes de subir
                        </span>
                      </label>
                    </div>
                    <p className={`text-sm ${
                      file.size > 50 * 1024 * 1024 * 1024 
                        ? 'text-red-800' 
                        : 'text-yellow-800'
                    }`}>
                      {file.size > 50 * 1024 * 1024 * 1024 ? (
                        <>
                          {enableCompression ? (
                            <>
                              ⚠️ <strong>Compresión en navegador será MUY LENTA</strong> para videos tan grandes 
                              (puede tardar 30-60+ minutos). Se recomienda <strong>desactivar compresión</strong> y 
                              subir directamente, o contactar al equipo técnico para implementar procesamiento en servidor.
                            </>
                          ) : (
                            <>
                              ✅ Subirás el video sin comprimir. El upload será más lento pero evitarás 
                              el procesamiento largo en el navegador. Tiempo estimado: 45-90 minutos.
                            </>
                          )}
                        </>
                      ) : (
                        <>
                          {enableCompression ? (
                            <>
                              ✅ El video será comprimido antes de subir, reduciendo el tamaño hasta 70% 
                              y acelerando el upload 3x. Tomará unos minutos adicionales.
                            </>
                          ) : (
                            <>
                              ⚠️ Subirás el video sin comprimir. El upload será más lento pero el
                              video mantendrá la calidad original.
                            </>
                          )}
                        </>
                      )}
                    </p>
                    {originalSize > 0 && compressedSize > 0 && compressedSize < originalSize && (
                      <p className="text-sm  text-green-700 mt-2 font-medium">
                        📦 Ahorro: {((originalSize - compressedSize) / (1024*1024)).toFixed(1)} MB 
                        ({((1 - compressedSize/originalSize) * 100).toFixed(1)}% reducción)
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Progress de compresión */}
            {compressionProgress && uploadStatus !== 'uploading' && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm text-gray-600">
                  <span>{compressionProgress.message}</span>
                  <span>{compressionProgress.percent}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                  <div
                    className="h-full bg-purple-600 transition-all duration-300 ease-out"
                    style={{ width: `${compressionProgress.percent}%` }}
                  />
                </div>
              </div>
            )}

            {/* Progress bar de upload */}
            {uploading && uploadStatus === 'uploading' && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm text-gray-600">
                  <span>Subiendo video...</span>
                  <span>{uploadProgress}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                  <div
                    className="h-full bg-blue-600 transition-all duration-300 ease-out"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                {currentVideoId && (
                  <p className="text-xs text-gray-500">ID: {currentVideoId}</p>
                )}
              </div>
            )}

            {/* Progress bar de processing */}
            {uploading && (uploadStatus === 'processing' || uploadStatus === 'completed') && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm text-gray-600">
                  <span>
                    {uploadStatus === 'processing' && 'Procesando e iniciando análisis...'}
                    {uploadStatus === 'completed' && '✓ Completado exitosamente'}
                  </span>
                  <span>100%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                  <div
                    className={`h-full transition-all duration-300 ease-out ${
                      uploadStatus === 'completed' ? 'bg-green-600' : 'bg-yellow-500'
                    }`}
                    style={{ width: '100%' }}
                  />
                </div>
              </div>
            )}

            {/* Botones */}
            <div className="flex gap-4 pt-4">
              <button
                type="submit"
                disabled={uploading || !file}
                className={`flex-1 py-3 px-6 rounded-lg font-medium transition-all flex items-center justify-center gap-2 ${
                  uploadStatus === 'completed'
                    ? 'bg-green-600 hover:bg-green-700 text-white'
                    : 'bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 disabled:cursor-not-allowed'
                }`}
              >
                {uploadStatus === 'loading-ffmpeg' && (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Cargando FFmpeg...
                  </>
                )}
                {uploadStatus === 'compressing' && (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Comprimiendo...
                  </>
                )}
                {uploadStatus === 'uploading' && (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Subiendo...
                  </>
                )}
                {uploadStatus === 'processing' && (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Procesando...
                  </>
                )}
                {uploadStatus === 'completed' && (
                  <>
                    <CheckCircle className="w-5 h-5" />
                    Completado
                  </>
                )}
                {uploadStatus === 'idle' && 'Subir Video'}
              </button>
              <button
                type="button"
                onClick={() => navigate({ to: '/security' })}
                disabled={uploading}
                className="px-6 py-3 border border-gray-300 rounded-lg font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Cancelar
              </button>
            </div>
          </div>
        </form>

        {/* Información adicional */}
        <div className="mt-6 bg-gray-50 rounded-lg p-4">
          <h3 className="font-semibold text-gray-800 mb-2">Información importante:</h3>
          <ul className="text-sm text-gray-600 space-y-1 list-disc ml-5">
            <li>Los videos se guardan por 7 días y luego se eliminan automáticamente</li>
            <li>Los reportes se conservan por 30 días</li>
            <li>El reconocimiento facial está habilitado para máxima precisión</li>
            <li>Recibirás un email si se detectan eventos importantes o críticos</li>
            <li>El procesamiento puede tardar 35-45 minutos para videos de 12 horas</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
