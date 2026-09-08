/**
 * Servicio de Compresión de Video usando FFmpeg.wasm
 * 
 * Comprime videos ANTES de subirlos a GCS para reducir tamaño y tiempo de upload
 * 
 * Resultados esperados:
 * - AVI 30GB → MP4 10GB (66% reducción)
 * - H.264 con CRF 28 (equilibrio calidad/tamaño)
 * - Bitrate aceptable para análisis de seguridad
 */

import { FFmpeg } from '@ffmpeg/ffmpeg';
import { fetchFile, toBlobURL } from '@ffmpeg/util';

export interface CompressionProgress {
  phase: 'loading' | 'compressing' | 'finalizing';
  percent: number;
  message: string;
}

export interface CompressionResult {
  compressedFile: File;
  originalSize: number;
  compressedSize: number;
  reductionPercent: number;
  duration: number; // segundos
}

class VideoCompressionService {
  private ffmpeg: FFmpeg | null = null;
  private isLoaded = false;
  private loadingPromise: Promise<void> | null = null;

  /**
   * Inicializa FFmpeg.wasm (solo se hace una vez)
   */
  async initialize(onProgress?: (progress: CompressionProgress) => void): Promise<void> {
    // Si ya está cargado, retornar
    if (this.isLoaded) return;

    // Si ya está cargando, esperar esa promesa
    if (this.loadingPromise) {
      return this.loadingPromise;
    }

    // Crear nueva promesa de carga
    this.loadingPromise = (async () => {
      try {
        // Timeout de 90s: si FFmpeg.wasm no carga en ese tiempo el worker falló
        const LOAD_TIMEOUT_MS = 90_000;
        const timeoutPromise = new Promise<never>((_, reject) =>
          setTimeout(
            () => reject(new Error('FFmpeg tardó demasiado en cargar (>90s). Recarga la página o desactiva la compresión.')),
            LOAD_TIMEOUT_MS
          )
        );

        await Promise.race([
          (async () => {
        console.log('🎬 Inicializando FFmpeg.wasm...');
        
        onProgress?.({
          phase: 'loading',
          percent: 0,
          message: 'Cargando FFmpeg.wasm...',
        });

        this.ffmpeg = new FFmpeg();

        // Configurar logging VERBOSE
        this.ffmpeg.on('log', ({ message }) => {
          console.log('[FFmpeg LOG]', message);
        });

        // Configurar progreso
        this.ffmpeg.on('progress', ({ progress, time }) => {
          const percent = Math.min(Math.round(progress * 100), 99);
          console.log(`[FFmpeg PROGRESS] ${percent}% - ${Math.round(time / 1000)}s`);
          onProgress?.({
            phase: 'compressing',
            percent,
            message: `Comprimiendo: ${percent}% (tiempo: ${Math.round(time / 1000)}s)`,
          });
        });

        // Cargar FFmpeg desde CDN
        const baseURL = 'https://unpkg.com/@ffmpeg/core@0.12.6/dist/esm';
        
        console.log('📦 Descargando FFmpeg desde CDN:', baseURL);
        
        onProgress?.({
          phase: 'loading',
          percent: 25,
          message: 'Descargando core de FFmpeg...',
        });

        console.log('⬇️ Descargando ffmpeg-core.js...');
        const coreURL = await toBlobURL(
          `${baseURL}/ffmpeg-core.js`,
          'text/javascript'
        );
        console.log('✅ ffmpeg-core.js descargado');

        console.log('⬇️ Descargando ffmpeg-core.wasm (~20MB)...');
        const wasmURL = await toBlobURL(
          `${baseURL}/ffmpeg-core.wasm`,
          'application/wasm'
        );
        console.log('✅ ffmpeg-core.wasm descargado');

        onProgress?.({
          phase: 'loading',
          percent: 75,
          message: 'Inicializando FFmpeg...',
        });

        console.log('🚀 Cargando FFmpeg en memoria...');
        await this.ffmpeg.load({
          coreURL,
          wasmURL,
        });

        this.isLoaded = true;

        onProgress?.({
          phase: 'loading',
          percent: 100,
          message: 'FFmpeg listo',
        });

        console.log('✅ FFmpeg.wasm cargado exitosamente');
          })(),
          timeoutPromise,
        ]);
      } catch (error: any) {
        console.error('❌ ERROR CRÍTICO cargando FFmpeg.wasm:', error);
        console.error('   Tipo de error:', error?.name);
        console.error('   Mensaje:', error?.message);
        console.error('   Stack:', error?.stack);
        this.loadingPromise = null;
        throw new Error(
          `No se pudo cargar FFmpeg: ${error?.message || 'Error desconocido'}. ` +
          'Verifica tu conexión a internet e intenta recargar la página.'
        );
      }
    })();

    return this.loadingPromise;
  }

  /**
   * Verifica si FFmpeg está listo para usar
   */
  isReady(): boolean {
    return this.isLoaded && this.ffmpeg !== null;
  }

  /**
   * Comprime un video usando H.264
   * 
   * Configuración optimizada para videos de seguridad:
   * - Codec: H.264 (libx264) - máxima compatibilidad
   * - CRF: 28 (equilibrio calidad/tamaño para seguridad)
   * - Preset: medium (equilibrio velocidad/compresión)
   * - Audio: AAC 128k (suficiente para seguridad)
   * 
   * @param file Archivo de video original
   * @param onProgress Callback de progreso
   * @returns Archivo comprimido y estadísticas
   */
  async compressVideo(
    file: File,
    onProgress?: (progress: CompressionProgress) => void
  ): Promise<CompressionResult> {
    if (!this.ffmpeg) {
      throw new Error('FFmpeg no está inicializado. Llama a initialize() primero.');
    }

    const startTime = Date.now();
    const originalSize = file.size;

    try {
      onProgress?.({
        phase: 'loading',
        percent: 0,
        message: 'Preparando video...',
      });

      // Escribir archivo de entrada en el filesystem de FFmpeg
      const inputName = 'input' + this.getFileExtension(file.name);
      const outputName = 'output.mp4';

      const sizeMB = (originalSize / (1024 * 1024)).toFixed(1);
      console.log(`📦 Cargando archivo en FFmpeg: ${file.name} (${sizeMB} MB)`);
      
      onProgress?.({
        phase: 'loading',
        percent: 2,
        message: `Cargando video (${sizeMB} MB)...`,
      });

      const fileData = await fetchFile(file);
      console.log(`✅ Archivo leído: ${fileData.byteLength} bytes`);
      
      await this.ffmpeg.writeFile(inputName, fileData);
      console.log(`✅ Archivo escrito en FFmpeg filesystem: ${inputName}`);

      onProgress?.({
        phase: 'compressing',
        percent: 5,
        message: 'Iniciando compresión...',
      });

      // Ejecutar FFmpeg con configuración optimizada
      console.log('🔄 Iniciando compresión FFmpeg con H.264 CRF 28...');
      console.log('   Codec: H.264 (libx264)');
      console.log('   CRF: 28 (equilibrio calidad/tamaño)');
      console.log('   Preset: medium');
      
      const ffmpegCommand = [
        '-i', inputName,              // Input file
        '-c:v', 'libx264',            // Video codec: H.264
        '-crf', '28',                 // Quality: 28 (18=alta, 28=equilibrada, 32=baja)
        '-preset', 'medium',          // Speed preset (faster=rápido, medium=equilibrado, slower=mejor compresión)
        '-c:a', 'aac',                // Audio codec: AAC
        '-b:a', '128k',               // Audio bitrate: 128kbps
        '-movflags', '+faststart',    // Optimizar para streaming web
        '-y',                         // Sobrescribir output sin preguntar
        outputName
      ];
      
      console.log('🎬 Comando FFmpeg:', ffmpegCommand.join(' '));
      
      await this.ffmpeg.exec(ffmpegCommand);
      
      console.log('✅ Compresión FFmpeg completada');

      onProgress?.({
        phase: 'finalizing',
        percent: 95,
        message: 'Finalizando...',
      });

      // Leer archivo de salida
      console.log(`📖 Leyendo archivo comprimido: ${outputName}`);
      const data = await this.ffmpeg.readFile(outputName);
      const blobPart: BlobPart = typeof data === 'string' ? data : new Uint8Array(data) as BlobPart;
      const compressedBlob = new Blob([blobPart], { type: 'video/mp4' });
      const compressedSize = compressedBlob.size;
      
      console.log(`✅ Archivo comprimido leído: ${(compressedSize / (1024 * 1024)).toFixed(1)} MB`);
      
      const compressedFile = new File(
        [compressedBlob],
        file.name.replace(/\.[^.]+$/, '.mp4'),
        { type: 'video/mp4' }
      );

      // Limpiar archivos temporales
      console.log('🧹 Limpiando archivos temporales...');
      await this.ffmpeg.deleteFile(inputName);
      await this.ffmpeg.deleteFile(outputName);

      const duration = (Date.now() - startTime) / 1000;
      const reductionPercent = ((originalSize - compressedSize) / originalSize) * 100;

      console.log(`✅ Compresión completada en ${duration.toFixed(1)}s`);
      console.log(`   Original: ${(originalSize / (1024 * 1024)).toFixed(1)} MB`);
      console.log(`   Comprimido: ${(compressedSize / (1024 * 1024)).toFixed(1)} MB`);
      console.log(`   Reducción: ${reductionPercent.toFixed(1)}%`);

      onProgress?.({
        phase: 'finalizing',
        percent: 100,
        message: `Compresión exitosa: ${reductionPercent.toFixed(0)}% reducción`,
      });

      return {
        compressedFile,
        originalSize,
        compressedSize,
        reductionPercent,
        duration,
      };
    } catch (error) {
      console.error('❌ Error comprimiendo video:', error);
      throw new Error('Error al comprimir el video. El archivo podría estar corrupto.');
    }
  }

  /**
   * Comprime solo si el archivo es grande (>500MB) y tiene formato sin comprimir
   */
  async compressIfNeeded(
    file: File,
    onProgress?: (progress: CompressionProgress) => void
  ): Promise<File> {
    const COMPRESS_THRESHOLD = 500 * 1024 * 1024; // 500MB
    const UNCOMPRESSED_FORMATS = ['.avi', '.mov', '.mkv'];

    const extension = this.getFileExtension(file.name).toLowerCase();
    const isUncompressed = UNCOMPRESSED_FORMATS.some(fmt => extension === fmt);
    const isLarge = file.size > COMPRESS_THRESHOLD;

    // Si el archivo es MP4 pequeño, no comprimir
    if (!isUncompressed && !isLarge) {
      console.log(`ℹ️ Archivo ${file.name} no requiere compresión`);
      return file;
    }

    console.log(`🔧 Archivo grande o sin comprimir, iniciando compresión...`);
    
    const result = await this.compressVideo(file, onProgress);
    return result.compressedFile;
  }

  /**
   * Obtiene la extensión del archivo incluyendo el punto
   */
  private getFileExtension(filename: string): string {
    const match = filename.match(/\.[^.]+$/);
    return match ? match[0] : '';
  }

  /**
   * Limpia recursos (llamar cuando ya no se necesite)
   */
  async cleanup(): Promise<void> {
    if (this.ffmpeg) {
      // FFmpeg.wasm no tiene método explicit de cleanup
      // El GC se encargará
      this.ffmpeg = null;
      this.isLoaded = false;
      this.loadingPromise = null;
      console.log('🧹 FFmpeg limpiado');
    }
  }
}

// Exportar instancia singleton
export const videoCompressionService = new VideoCompressionService();
