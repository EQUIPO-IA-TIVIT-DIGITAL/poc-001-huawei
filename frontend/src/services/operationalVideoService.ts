/**
 * Servicio TypeScript para API de Análisis Operativo v2.0
 * Maneja comunicación con endpoints /api/operational/*
 *
 * v2.0 Mejoras:
 * - Paginación de eventos
 * - SSE (Server-Sent Events) para progreso en tiempo real
 * - Reprocesamiento de análisis fallidos
 * - Comparativa entre análisis
 */

import { getApiBaseUrl } from '../lib/backendUrl';
import axios from 'axios';

const API_BASE_URL = getApiBaseUrl();

export interface OperationalAnalysisType {
  name: string;
  description: string;
  icon: string;
  key_metrics: string[];
  estimated_minutes_per_hour: number;
}

export interface OperationalAnalysis {
  id: string;
  usuario: string;
  analysis_type: string;
  custom_context: string;
  custom_questions: string[];
  nombre_camara: string;
  ubicacion: string;
  video_filename: string;
  video_url: string;
  video_duration: number;
  video_size_mb: number;
  estado: string;
  progress: number;
  current_phase: string;
  summary: Record<string, any>;
  scan_stats: Record<string, any>;
  phase_timings: Record<string, number>;
  report_txt_url: string;
  report_pdf_url: string;
  error_message: string;
  created_at: string;
  started_at: string;
  completed_at: string;
  tiempo_procesamiento_segundos: number;
}

export interface OperationalEvent {
  id: string;
  analysis_id: string;
  timestamp_start: number;
  timestamp_end: number;
  event_type: string;
  scanner_event_type: string;
  person_description: string;
  carried_objects: string;
  direction: string;
  zone: string;
  confidence: string;
  details: Record<string, any>;
  frame_urls: string[];
}

export interface InitOperationalUploadRequest {
  filename: string;
  content_type?: string;
  analysis_type: string;
  custom_context?: string;
  custom_questions?: string[];
  nombre_camara?: string;
  ubicacion?: string;
}

export interface InitOperationalUploadResponse {
  success: boolean;
  analysis_id: string;
  upload_url: string;
  storage_path: string;
  storage_bucket: string;
  blob_name: string;
  expiration_hours: number;
  error?: string;
}

export interface PaginatedEvents {
  events: OperationalEvent[];
  count: number;
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  cursor?: string;
  next_cursor?: string | null;
  has_more?: boolean;
}

export interface SSEProgressData {
  status: string;
  progress: number;
  current_phase: string;
  summary?: Record<string, any>;
  error_message?: string;
  scan_stats?: Record<string, any>;
  eta_seconds?: number | null;
  final?: boolean;
  error?: string;
}

export interface TimeEstimate {
  estimated_minutes: number;
  estimated_range: { min_minutes: number; max_minutes: number };
  breakdown: { upload_minutes: number; analysis_minutes: number };
}

export interface HeatmapData {
  buckets: number[];
  bucket_size: number;
  max_count: number;
  total_events: number;
  video_duration: number;
}

export interface AnalysisComparison {
  analysis_type: string;
  analysis_a: {
    id: string;
    video_filename: string;
    video_duration: number;
    created_at: string;
    total_events: number;
    summary: Record<string, any>;
  };
  analysis_b: {
    id: string;
    video_filename: string;
    video_duration: number;
    created_at: string;
    total_events: number;
    summary: Record<string, any>;
  };
  deltas: Record<string, {
    analysis_a: number;
    analysis_b: number;
    delta: number;
    delta_pct: number;
  }>;
  event_count_delta: number;
}

class OperationalVideoService {
  private baseUrl = `${API_BASE_URL}/api/operational`;

  // Axios instance with CSRF header required by backend JSON endpoints
  private api = axios.create({
    withCredentials: true,
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  });

  async listarTipos(): Promise<Record<string, OperationalAnalysisType>> {
    try {
      const response = await this.api.get(`${this.baseUrl}/types`);
      return response.data.types;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error obteniendo tipos');
    }
  }

  /**
   * Inicia un upload y crea el análisis operativo
   */
  async iniciarUpload(data: InitOperationalUploadRequest): Promise<InitOperationalUploadResponse> {
    try {
      const response = await this.api.post(`${this.baseUrl}/upload/init`, data);
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error iniciando upload');
    }
  }

  /**
   * Sube un archivo al backend (proxy para evitar CORS)
   */
  async subirArchivoProxy(
    analysisId: string,
    file: File,
    onProgress?: (percentage: number) => void
  ): Promise<boolean> {
    try {
      const formData = new FormData();
      formData.append('analysis_id', analysisId);
      formData.append('file', file);

      const response = await this.api.post(`${this.baseUrl}/upload/stream`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          if (onProgress && progressEvent.total) {
            const percentage = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            onProgress(percentage);
          }
        },
      });

      return response.data.success;
    } catch (error: any) {
      throw new Error('Error subiendo archivo al servidor');
    }
  }

  /**
   * Completa el upload e inicia análisis automáticamente
   */
  async completarUpload(analysisId: string): Promise<{ success: boolean; job_id?: string }> {
    try {
      const response = await this.api.post(
        `${this.baseUrl}/upload/complete`,
        { analysis_id: analysisId }
      );
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error completando upload');
    }
  }

  /**
   * Lista los análisis operativos del usuario autenticado
   */
  async listarAnalisis(params?: {
    analysis_type?: string;
    limit?: number;
  }): Promise<{ analyses: OperationalAnalysis[]; count: number }> {
    try {
      const response = await this.api.get(`${this.baseUrl}/analyses`, { params });
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error listando análisis');
    }
  }

  /**
   * Obtiene un análisis por ID
   */
  async obtenerAnalisis(analysisId: string): Promise<OperationalAnalysis> {
    try {
      const response = await this.api.get(`${this.baseUrl}/analyses/${analysisId}`);
      return response.data.analysis;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error obteniendo análisis');
    }
  }

  /**
   * Obtiene el estado actual (polling fallback)
   */
  async obtenerEstado(analysisId: string): Promise<{
    status: string;
    progress: number;
    current_phase: string;
  }> {
    try {
      const response = await this.api.get(`${this.baseUrl}/analyses/${analysisId}/status`);
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error obteniendo estado');
    }
  }

  /**
   * Obtiene los eventos con paginación
   */
  async obtenerEventos(
    analysisId: string,
    page: number = 1,
    perPage: number = 20
  ): Promise<PaginatedEvents> {
    try {
      const response = await this.api.get(`${this.baseUrl}/analyses/${analysisId}/events`, {
        params: { page, per_page: perPage },
      });
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error obteniendo eventos');
    }
  }

  /**
   * Reprocesa un análisis que falló (error)
   */
  async reprocesarAnalisis(analysisId: string): Promise<{
    success: boolean;
    job_id?: string;
    message: string;
  }> {
    try {
      const response = await this.api.post(
        `${this.baseUrl}/analyses/${analysisId}/reprocess`,
        {}
      );
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error reprocesando análisis');
    }
  }

  /**
   * Compara dos análisis del mismo tipo
   */
  async compararAnalisis(
    analysisIdA: string,
    analysisIdB: string
  ): Promise<AnalysisComparison> {
    try {
      const response = await this.api.post(
        `${this.baseUrl}/analyses/compare`,
        { analysis_id_a: analysisIdA, analysis_id_b: analysisIdB }
      );
      return response.data.comparison;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error comparando análisis');
    }
  }

  /**
   * Abre un SSE stream para recibir progreso en tiempo real
   * Reemplaza polling HTTP para mejor rendimiento
   */
  connectSSE(
    analysisId: string,
    onMessage: (data: SSEProgressData) => void,
    onError?: (error: Event) => void
  ): EventSource {
    const url = `${this.baseUrl}/analyses/${analysisId}/stream`;
    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      try {
        const data: SSEProgressData = JSON.parse(event.data);
        onMessage(data);

        // Auto-cerrar si es el mensaje final
        if (data.final) {
          eventSource.close();
        }
      } catch (e) {
        console.error('Error parsing SSE data:', e);
      }
    };

    eventSource.onerror = (event) => {
      if (onError) onError(event);
      eventSource.close();
    };

    return eventSource;
  }

  /**
   * Elimina un análisis
   */
  async eliminarAnalisis(analysisId: string): Promise<boolean> {
    try {
      const response = await this.api.delete(`${this.baseUrl}/analyses/${analysisId}`);
      return response.data.success;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error eliminando análisis');
    }
  }

  /**
   * Cancela un análisis en progreso
   */
  async cancelarAnalisis(analysisId: string): Promise<{ success: boolean; message: string }> {
    try {
      const response = await this.api.post(
        `${this.baseUrl}/analyses/${analysisId}/cancel`,
        {}
      );
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error cancelando análisis');
    }
  }

  /**
   * Estima el tiempo de procesamiento
   */
  async estimarTiempo(params: {
    analysis_type: string;
    video_duration_seconds?: number;
    file_size_mb?: number;
  }): Promise<TimeEstimate> {
    try {
      const response = await this.api.post(`${this.baseUrl}/estimate-time`, params);
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error estimando tiempo');
    }
  }

  /**
   * Retorna la URL del endpoint de streaming de video (proxied por backend).
   * El navegador envía la cookie de sesión automáticamente — sin CORS.
   */
  getVideoStreamUrl(analysisId: string): string {
    return `${API_BASE_URL}/api/operational/analyses/${analysisId}/stream-video`;
  }

  /**
   * Obtiene una URL firmada temporal para reproducir el video en el navegador
   * @deprecated Usar getVideoStreamUrl que evita problemas de CORS con el almacenamiento directo
   */
  async obtenerVideoUrl(analysisId: string): Promise<string> {
    try {
      const response = await this.api.get(`${this.baseUrl}/analyses/${analysisId}/video-url`);
      return response.data.url;
    } catch (error: any) {
      throw new Error(error.response?.data?.error || 'Error obteniendo URL de video');
    }
  }

  /**
   * Obtiene los datos del heatmap calculados con TODOS los eventos del servidor
   */
  async obtenerHeatmap(analysisId: string): Promise<HeatmapData | null> {
    try {
      const response = await this.api.get(`${this.baseUrl}/analyses/${analysisId}/heatmap`);
      return response.data.heatmap || null;
    } catch (error: any) {
      console.error('Error obteniendo heatmap:', error);
      return null;
    }
  }

  // ===== UTILIDADES =====

  /**
   * Descarga un blob como archivo
   */
  downloadBlob(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    window.URL.revokeObjectURL(url);
  }

  formatDuration(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hours > 0) return `${hours}h ${minutes}min ${secs}s`;
    if (minutes > 0) return `${minutes}min ${secs}s`;
    return `${secs}s`;
  }

  formatETA(seconds: number | null | undefined): string {
    if (!seconds || seconds <= 0) return '';
    if (seconds < 60) return `~${Math.ceil(seconds)}s restantes`;
    if (seconds < 3600) return `~${Math.ceil(seconds / 60)}min restantes`;
    return `~${(seconds / 3600).toFixed(1)}h restantes`;
  }

  getEstadoColor(estado: string): string {
    const colores: Record<string, string> = {
      pending: 'bg-yellow-100 text-yellow-800 border border-yellow-300',
      downloading: 'bg-blue-100 text-blue-800 border border-blue-300',
      scanning: 'bg-indigo-100 text-indigo-800 border border-indigo-300',
      analyzing: 'bg-red-100 text-red-800 border border-red-300',
      cross_analyzing: 'bg-pink-100 text-pink-800 border border-pink-300',
      generating_report: 'bg-orange-100 text-orange-800 border border-orange-300',
      completed: 'bg-green-600 text-white font-semibold',
      cancelled: 'bg-gray-500 text-white font-semibold',
      error: 'bg-red-100 text-red-800 border border-red-300',
    };
    return colores[estado] || 'bg-gray-100 text-gray-800';
  }

  getEstadoTexto(estado: string): string {
    const textos: Record<string, string> = {
      pending: 'Pendiente',
      downloading: 'Descargando',
      scanning: 'Escaneando',
      analyzing: 'Analizando',
      cross_analyzing: 'Consolidando',
      generating_report: 'Generando reporte',
      completed: 'Finalizado',
      cancelled: 'Cancelado',
      error: 'Error',
    };
    return textos[estado] || estado;
  }

  isProcessing(estado: string): boolean {
    return ['pending', 'downloading', 'scanning', 'analyzing', 'cross_analyzing', 'generating_report'].includes(estado);
  }

  isCancellable(estado: string): boolean {
    return this.isProcessing(estado);
  }
}

export const operationalVideoService = new OperationalVideoService();
