/**
 * Servicio TypeScript para API de Security Videos
 * Maneja comunicación con endpoints de análisis de seguridad
 */

import { getApiBaseUrl } from '../lib/backendUrl';
import axios from 'axios';

const API_BASE_URL = getApiBaseUrl();

export enum ClasificacionEvento {
  NORMAL = 'normal',
  SOSPECHOSO = 'sospechoso',
  IMPORTANTE = 'importante'
}

export enum EstadoSecurityVideo {
  UPLOADING = 'uploading',
  UPLOADED = 'uploaded',
  PROCESSING = 'processing',
  DETECTING_MOTION = 'motion_detecting',
  MOTION_DETECTED = 'motion_detected',
  ANALYZING = 'analyzing',
  CLASSIFYING = 'classifying',
  CLASSIFIED = 'classified',
  DEEP_ANALYZING = 'deep_analyzing',
  GENERATING_REPORT = 'generating_report',
  COMPLETED = 'completed',
  ERROR = 'error'
}

export interface SecurityVideo {
  id: string;
  usuario: string;
  nombre_camara: string;
  ubicacion: string;
  fecha_grabacion: string;
  duracion_segundos: number;
  ruta_gcs: string;
  estado: EstadoSecurityVideo;
  metadata_tecnico: Record<string, any>;
  estadisticas: Record<string, any>;
  reporte_txt_url?: string;
  reporte_pdf_url?: string;
  fecha_creacion?: string;
  fecha_procesamiento?: string;
  tiempo_procesamiento_segundos?: number;
  eventos_count?: number;
  tiene_eventos_importantes?: boolean;
}

export interface EventoSeguridad {
  id: string;
  security_video_id: string;
  timestamp_inicio: number;
  timestamp_fin: number;
  duracion: number;
  objetos_detectados: string[];
  acciones_detectadas: string[];
  personas_count: number;
  vehiculos_count: number;
  descripcion: string;
  confianza: number;
  nivel_riesgo?: string;
  razon_riesgo?: string;
  analisis_detallado?: Record<string, any>;
  clip_url?: string;
  frames_urls: string[];
  metadata?: Record<string, any>;
  // Legacy compatibility
  clasificacion?: ClasificacionEvento;
  descripcion_gemini?: string;
  analisis_profundo?: Record<string, any>;
}

export interface Evento {
  id: string;
  timestamp_inicio: number;
  timestamp_fin: number;
  duracion: number;
  objetos_detectados: string[];
  acciones_detectadas: string[];
  personas_count: number;
  vehiculos_count: number;
  descripcion: string;
  confianza: number;
  nivel_riesgo?: string;
  clip_url?: string;
  frames_urls: string[];
  analisis_detallado?: Record<string, any>;
  // Legacy compatibility
  clasificacion?: 'normal' | 'sospechoso' | 'importante';
  descripcion_gemini?: string;
  tiene_analisis_profundo?: boolean;
}

export interface InitUploadRequest {
  nombre_camara?: string;
  ubicacion?: string;
  fecha_grabacion?: string;
  filename: string;
  content_type?: string;
  usuario?: string;
}

export interface InitUploadResponse {
  success: boolean;
  video_id: string;
  upload_url: string;
  gcs_path: string;
  bucket: string;
  blob_name: string;
  expiration_hours: number;
  error?: string;
}

class SecurityVideoService {
  private baseUrl = `${API_BASE_URL}/api/security`;

  /**
   * Inicia un upload resumable
   */
  async iniciarUpload(data: InitUploadRequest): Promise<InitUploadResponse> {
    try {
      const response = await axios.post(`${this.baseUrl}/upload/init`, data, {
        withCredentials: true,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error iniciando upload');
    }
  }

  /**
   * Sube un archivo al backend (proxy para evitar CORS)
   */
  async subirArchivoProxy(
    videoId: string,
    file: File,
    onProgress?: (percentage: number) => void
  ): Promise<boolean> {
    try {
      const formData = new FormData();
      formData.append('video_id', videoId);
      formData.append('file', file);

      const response = await axios.post(`${this.baseUrl}/upload/stream`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        withCredentials: true,
        onUploadProgress: (progressEvent) => {
          if (onProgress && progressEvent.total) {
            const percentage = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            onProgress(percentage);
          }
        },
      });

      return response.data.success;
    } catch (error: any) {
      console.error('Error subiendo archivo vía proxy:', error);
      throw new Error('Error subiendo archivo al servidor');
    }
  }

  /**
   * Sube un archivo a GCS usando resumable upload
   */
  async subirArchivo(
    uploadUrl: string,
    file: File,
    onProgress?: (percentage: number) => void
  ): Promise<boolean> {
    try {
      const endByte = file.size - 1;
      await axios.put(uploadUrl, file, {
        headers: {
          'Content-Type': file.type,
          'Content-Range': `bytes 0-${endByte}/${file.size}`,
        },
        withCredentials: false,
        onUploadProgress: (progressEvent) => {
          if (onProgress && progressEvent.total) {
            const percentage = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            onProgress(percentage);
          }
        },
      });
      return true;
    } catch (error: any) {
      console.error('Error subiendo archivo:', error);
      throw new Error('Error subiendo archivo a Cloud Storage');
    }
  }

  /**
   * Completa el upload y marca el video como listo para procesar
   */
  async completarUpload(videoId: string): Promise<{ success: boolean; metadata?: any }> {
    try {
      const response = await axios.post(
        `${this.baseUrl}/upload/complete`,
        { video_id: videoId },
        { withCredentials: true }
      );
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error completando upload');
    }
  }

  /**
   * Obtiene la lista de videos de seguridad
   */
  async listarVideos(params?: {
    limit?: number;
    estado?: string;
    usuario?: string;
  }): Promise<{ videos: SecurityVideo[]; total: number }> {
    try {
      const response = await axios.get(`${this.baseUrl}/videos`, {
        params,
        withCredentials: true,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error listando videos');
    }
  }

  /**
   * Obtiene detalles de un video específico
   */
  async obtenerVideo(videoId: string): Promise<SecurityVideo> {
    try {
      const response = await axios.get(`${this.baseUrl}/videos/${videoId}`, {
        withCredentials: true,
      });
      return response.data.video;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error obteniendo video');
    }
  }

  /**
   * Obtiene eventos de un video
   */
  async obtenerEventos(
    videoId: string,
    clasificacion?: string
  ): Promise<{ eventos: Evento[]; total: number }> {
    try {
      const params: Record<string, string> = {};
      if (clasificacion) params.clasificacion = clasificacion;
      const response = await axios.get(`${this.baseUrl}/videos/${videoId}/eventos`, {
        params,
        withCredentials: true,
      });
      const pagination = response.data.pagination;
      return {
        eventos: response.data.eventos || [],
        total: pagination?.total ?? (response.data.eventos?.length || 0),
      };
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error obteniendo eventos');
    }
  }

  /**
   * Elimina un video de seguridad
   */
  async eliminarVideo(videoId: string): Promise<boolean> {
    try {
      const response = await axios.delete(`${this.baseUrl}/videos/${videoId}`, {
        withCredentials: true,
      });
      return response.data.success;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error eliminando video');
    }
  }

  /**
   * Inicia el procesamiento de un video
   */
  async procesarVideo(videoId: string): Promise<boolean> {
    try {
      const response = await axios.post(
        `${this.baseUrl}/videos/${videoId}/process`,
        {},
        { withCredentials: true }
      );
      return response.data.success;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error iniciando procesamiento');
    }
  }

  /**
   * Reintenta el análisis de un video que falló (sin re-subir)
   */
  async reintentarAnalisis(videoId: string): Promise<{ success: boolean; message?: string; estimated_time_minutes?: number }> {
    try {
      const response = await axios.post(
        `${this.baseUrl}/videos/${videoId}/reprocess`,
        {},
        { withCredentials: true }
      );
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error reintentando análisis');
    }
  }

  /**
   * Verifica el estado de los servicios
   */
  async healthCheck(): Promise<{ repository: boolean; upload_service: boolean }> {
    try {
      const response = await axios.get(`${this.baseUrl}/health`);
      return response.data.services;
    } catch (error) {
      return { repository: false, upload_service: false };
    }
  }

  /**
   * Formatea duración en segundos a formato legible
   */
  formatDuration(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
      return `${hours}h ${minutes}min ${secs}s`;
    } else if (minutes > 0) {
      return `${minutes}min ${secs}s`;
    } else {
      return `${secs}s`;
    }
  }

  /**
   * Obtiene el color del estado
   */
  getEstadoColor(estado: string): string {
    const colores: Record<string, string> = {
      uploading: 'bg-blue-100 text-blue-800 border border-blue-300',
      uploaded: 'bg-green-100 text-green-800 border border-green-300',
      motion_detecting: 'bg-yellow-100 text-yellow-800 border border-yellow-300',
      motion_detected: 'bg-yellow-100 text-yellow-800 border border-yellow-300',
      analyzing: 'bg-indigo-100 text-indigo-800 border border-indigo-300',
      classifying: 'bg-purple-100 text-purple-800 border border-purple-300',
      classified: 'bg-purple-100 text-purple-800 border border-purple-300',
      deep_analyzing: 'bg-indigo-100 text-indigo-800 border border-indigo-300',
      generating_report: 'bg-pink-100 text-pink-800 border border-pink-300',
      completed: 'bg-green-600 text-white font-semibold',
      error: 'bg-red-100 text-red-800 border border-red-300',
    };
    return colores[estado] || 'bg-gray-100 text-gray-800';
  }

  /**
   * Obtiene el texto del estado en español
   */
  getEstadoTexto(estado: string): string {
    const textos: Record<string, string> = {
      uploading: 'Subiendo',
      uploaded: 'Analizando',
      motion_detecting: 'Analizando',
      motion_detected: 'Analizando',
      analyzing: 'Analizando',
      classifying: 'Analizando',
      classified: 'Analizando',
      deep_analyzing: 'Analizando',
      generating_report: 'Analizando',
      completed: 'Finalizado',
      error: 'Error',
    };
    return textos[estado] || estado;
  }

  // ==========================================
  // ANÁLISIS CONTEXTUAL
  // ==========================================

  /**
   * Inicia un análisis contextual de seguridad
   */
  async iniciarAnalisisContextual(
    videoId: string,
    contexto: string,
    modo: 'ESTANDAR' | 'PROFUNDO' = 'ESTANDAR'
  ): Promise<{ success: boolean; analysis_id: string; message?: string }> {
    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/v1/security/analyze-context`,
        { video_id: videoId, contexto, modo },
        { withCredentials: true }
      );
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error iniciando análisis contextual');
    }
  }

  /**
   * Lista todos los análisis contextuales del usuario
   */
  async listarAnalisis(): Promise<{ analyses: ContextualAnalysis[]; total: number }> {
    try {
      const response = await axios.get(
        `${API_BASE_URL}/api/v1/security/analyses`,
        { withCredentials: true }
      );
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error listando análisis');
    }
  }

  /**
   * Obtiene detalles de un análisis específico
   */
  async obtenerAnalisis(analysisId: string): Promise<ContextualAnalysis> {
    try {
      const response = await axios.get(
        `${API_BASE_URL}/api/v1/security/analyses/${analysisId}`,
        { withCredentials: true }
      );
      return response.data.analysis;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error obteniendo análisis');
    }
  }

  /**
   * Descarga el reporte de un análisis
   */
  async descargarReporte(
    analysisId: string,
    formato: 'pdf' | 'json' | 'txt' = 'pdf'
  ): Promise<Blob> {
    try {
      const response = await axios.get(
        `${API_BASE_URL}/api/v1/security/analyses/${analysisId}/report`,
        {
          params: { formato },
          responseType: 'blob',
          withCredentials: true,
        }
      );
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error descargando reporte');
    }
  }

  /**
   * Obtiene el texto del estado del análisis
   */
  getAnalysisEstadoTexto(estado: string): string {
    const textos: Record<string, string> = {
      pending: 'Pendiente',
      processing: 'Procesando',
      completed: 'Completado',
      error: 'Error',
    };
    return textos[estado] || estado;
  }

  /**
   * Obtiene el color del estado del análisis
   */
  getAnalysisEstadoColor(estado: string): string {
    const colores: Record<string, string> = {
      pending: 'bg-yellow-100 text-yellow-800',
      processing: 'bg-blue-100 text-blue-800',
      completed: 'bg-green-100 text-green-800',
      error: 'bg-red-100 text-red-800',
    };
    return colores[estado] || 'bg-gray-100 text-gray-800';
  }
}

// Interface para Análisis Contextual
export interface ContextualAnalysis {
  id: string;
  video_id: string;
  usuario: string;
  contexto: string;
  modo: 'ESTANDAR' | 'PROFUNDO';
  estado: 'pending' | 'processing' | 'completed' | 'error';
  resultado?: {
    estado: string;
    respuesta_consulta: string;
    estadisticas: {
      total_movimientos: number;
      relevantes_contexto: number;
      porcentaje_relevancia: number;
    };
    timeline: Array<{
      timestamp: number;
      timestamp_formatted: string;
      analisis: Record<string, any>;
    }>;
    analisis_profundo?: Record<string, any>;
  };
  reporte_url?: string;
  fecha_creacion: string;
  fecha_completado?: string;
  error?: string;
}

export const securityVideoService = new SecurityVideoService();

// Funciones de exportación para uso directo
export const obtenerVideo = (videoId: string) => securityVideoService.obtenerVideo(videoId);
export const obtenerEventosVideo = (videoId: string, clasificacion?: ClasificacionEvento) =>
  securityVideoService.obtenerEventos(videoId, clasificacion as any).then(res => res.eventos as unknown as EventoSeguridad[]);

