/**
 * Servicio de Upload con Signed URLs
 * Implementa subida directa a Google Cloud Storage sin pasar archivos por el backend
 */

import { fetchWithBaseFallback, getApiBaseUrl } from '../lib/backendUrl';

export interface VideoMetadata {
  title: string;
  description?: string;
}

export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

export interface UploadResponse {
  video_id: number;
  upload_url: string;
  blob_name: string;
  bucket: string;
  expires_at: string;
}

export interface VideoUrlResponse {
  video_id: number;
  url: string;
  expires_in_minutes: number;
}

export class UploadService {
  private apiUrl: string;

  constructor() {
    this.apiUrl = getApiBaseUrl();
  }

  /**
   * Sube un video usando el flujo de Signed URLs
   * 
   * Flujo:
   * 1. Solicita URL firmada al backend
   * 2. Sube archivo directo a GCS
   * 3. Confirma al backend que la subida finalizó
   * 
   * @param file Archivo de video a subir
   * @param metadata Título y descripción del video
   * @param onProgress Callback para reportar progreso
   * @returns ID del video creado
   */
  async uploadVideo(
    file: File,
    metadata: VideoMetadata,
    onProgress: (progress: UploadProgress) => void
  ): Promise<number> {
    // Validaciones cliente
    this.validateFile(file);

    try {
      // 1. Solicitar URL firmada
      const uploadData = await this.requestUploadUrl(file, metadata);

      // 2. Subir a GCS
      await this.uploadToGCS(file, uploadData.upload_url, onProgress);

      // 3. Confirmar
      await this.confirmUpload(uploadData.video_id);

      return uploadData.video_id;
    } catch (error) {
      console.error('Upload error:', error);
      throw error;
    }
  }

  /**
   * Valida el archivo antes de subir
   */
  private validateFile(file: File): void {
    const MAX_SIZE = 5 * 1024 * 1024 * 1024; // 5GB
    const ALLOWED_TYPES = ['video/mp4', 'video/webm', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska'];

    if (file.size > MAX_SIZE) {
      throw new Error('El archivo es demasiado grande. Máximo 5GB');
    }

    if (!ALLOWED_TYPES.includes(file.type)) {
      throw new Error('Tipo de archivo no permitido. Solo se permiten videos MP4, WebM, MOV, AVI, MKV');
    }
  }

  /**
   * Solicita URL firmada al backend
   */
  private async requestUploadUrl(file: File, metadata: VideoMetadata): Promise<UploadResponse> {
    const response = await fetchWithBaseFallback('/api/v1/videos/upload-url', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      credentials: 'include', // Importante para enviar cookies de sesión
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type,
        size: file.size,
        title: metadata.title,
        description: metadata.description || '',
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Error al solicitar URL de subida');
    }

    const result = await response.json();
    return result.data;
  }

  /**
   * Sube archivo directo a GCS usando XHR (para progress tracking)
   */
  private uploadToGCS(
    file: File,
    url: string,
    onProgress: (progress: UploadProgress) => void
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      // Progress tracking
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          onProgress({
            loaded: e.loaded,
            total: e.total,
            percentage: Math.round((e.loaded / e.total) * 100),
          });
        }
      });

      // Success
      xhr.addEventListener('load', () => {
        if (xhr.status === 200) {
          resolve();
        } else {
          reject(new Error(`Upload failed with status: ${xhr.status}`));
        }
      });

      // Error
      xhr.addEventListener('error', () => {
        reject(new Error('Network error during upload'));
      });

      // Abort
      xhr.addEventListener('abort', () => {
        reject(new Error('Upload cancelled'));
      });

      // Send
      xhr.open('PUT', url);
      xhr.setRequestHeader('Content-Type', file.type);
      xhr.send(file);
    });
  }

  /**
   * Confirma al backend que la subida finalizó
   */
  private async confirmUpload(videoId: number): Promise<void> {
    const response = await fetchWithBaseFallback(`/api/v1/videos/${videoId}/confirm`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      credentials: 'include',
      body: JSON.stringify({}),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Error al confirmar subida');
    }
  }

  /**
   * Obtiene URL firmada para ver/descargar un video
   */
  async getVideoUrl(videoId: number): Promise<string> {
    const response = await fetchWithBaseFallback(`/api/v1/videos/${videoId}/url`, {
      method: 'GET',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
      },
      credentials: 'include',
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Error al obtener URL del video');
    }

    const result = await response.json();
    return result.data.url;
  }
}

export default UploadService;
