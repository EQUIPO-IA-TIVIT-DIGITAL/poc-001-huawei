/**
 * Servicio TypeScript para API de Análisis de Audio
 * Maneja comunicación con endpoints /api/audio/*
 *
 * Funcionalidades:
 * - Upload de video para extracción de audio
 * - Obtener transcripciones con timestamps
 * - Consultas inteligentes sobre el contenido
 * - Búsqueda en transcripción
 */

import { getApiBaseUrl } from '../lib/backendUrl';
import axios from 'axios';

const API_BASE_URL = getApiBaseUrl();

// ═══════════════════════════════════════════════════════
// INTERFACES
// ═══════════════════════════════════════════════════════

export interface AudioAnalysis {
  id: string;
  usuario: string;
  titulo: string;
  descripcion: string;
  video_filename: string;
  video_url: string;
  video_duration: number;
  video_size_mb: number;
  audio_url: string;
  audio_duration: number;
  estado: string;
  progress: number;
  current_phase: string;
  error_message: string;
  full_transcription: string;
  full_transcription_url: string;
  detected_language: string;
  embeddings_generated: boolean;
  total_segments: number;
  detected_languages: string[];
  average_confidence: number;
  speakers_detected: number;
  summary: Record<string, any>;
  created_at: string;
  started_at: string;
  completed_at: string;
  tiempo_procesamiento_segundos: number;
}

export interface AudioSegment {
  id: string;
  analysis_id: string;
  text: string;
  start_time: number;
  end_time: number;
  confidence: number;
  speaker: string;
  language: string;
  words: Array<{
    word: string;
    start_time: number;
    end_time: number;
    confidence: number;
  }>;
  timestamp_formatted?: string;
}

export interface InitAudioUploadRequest {
  filename: string;
  content_type?: string;
  titulo?: string;
  descripcion?: string;
  client_video_duration?: number;
}

export interface InitAudioUploadResponse {
  success: boolean;
  analysis_id: string;
  upload_url: string;
  storage_path: string;
  storage_bucket: string;
  blob_name: string;
  expiration_hours: number;
  error?: string;
}

export interface PaginatedSegments {
  segments: AudioSegment[];
  count: number;
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  next_cursor?: string | null;
}

export interface AudioQueryResult {
  success: boolean;
  respuesta: string;
  momentos_relevantes: Array<{
    timestamp: string;
    timestamp_seconds: number;
    contexto: string;
    relevancia: string;
  }>;
  encontrado: boolean;
  confianza: string;
  segments_found: number;
  text_matches?: Array<{
    text: string;
    start_time: number;
    end_time: number;
    timestamp: string;
  }>;
  error?: string;
}

export interface AudioSearchResult {
  success: boolean;
  query: string;
  results: (AudioSegment & { timestamp_formatted: string })[];
  total: number;
}

export interface AudioStatusResponse {
  success: boolean;
  status: string;
  progress: number;
  current_phase: string;
  error_message: string;
}

export interface TranscriptionResponse {
  success: boolean;
  transcription: string;
  total_segments: number;
  average_confidence: number;
  summary: Record<string, any>;
}

// ═══════════════════════════════════════════════════════
// SERVICIO
// ═══════════════════════════════════════════════════════

class AudioAnalysisService {
  private api = axios.create({
    baseURL: `${API_BASE_URL}/api/audio`,
    withCredentials: true,
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    },
  });

  constructor() {
    // La autenticación se gestiona exclusivamente mediante cookies de sesión HttpOnly.
    // No se usa localStorage para tokens (previene XSS token theft).

    // Interceptor para 401
    this.api.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          window.dispatchEvent(new CustomEvent('auth:unauthorized'));
        }
        return Promise.reject(error);
      }
    );
  }

  // ═══ UPLOAD ═══

  async iniciarUpload(data: InitAudioUploadRequest): Promise<InitAudioUploadResponse> {
    const res = await this.api.post('/upload/init', data);
    return res.data;
  }

  async subirArchivoProxy(
    analysisId: string,
    file: File,
    onProgress?: (progress: number) => void
  ): Promise<{ success: boolean; bytes_uploaded: number }> {
    const formData = new FormData();
    formData.append('analysis_id', analysisId);
    formData.append('file', file);

    const res = await this.api.post('/upload/stream', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 0,
      maxContentLength: Infinity,
      maxBodyLength: Infinity,
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          onProgress(Math.round((e.loaded * 100) / e.total));
        }
      },
    });
    return res.data;
  }

  async subirArchivoDirectoResumable(
    uploadUrl: string,
    file: File,
    onProgress?: (progress: number) => void
  ): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('PUT', uploadUrl, true);
      xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');

      xhr.upload.onprogress = (event: ProgressEvent<EventTarget>) => {
        if (!onProgress || !event.lengthComputable) return;
        const progress = Math.round((event.loaded * 100) / event.total);
        onProgress(progress);
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve();
          return;
        }
        reject(new Error(`Upload directo falló (${xhr.status})`));
      };

      xhr.onerror = () => reject(new Error('Error de red en upload directo'));
      xhr.ontimeout = () => reject(new Error('Timeout en upload directo'));
      xhr.timeout = 0;

      xhr.send(file);
    });
  }

  async completarUpload(analysisId: string, autoProcess = true, clientVideoDuration?: number): Promise<{
    success: boolean;
    processing_started: boolean;
    job_id: string | null;
    video_duration: number;
    video_size_mb: number;
  }> {
    const res = await this.api.post('/upload/complete', {
      analysis_id: analysisId,
      auto_process: autoProcess,
      client_video_duration: clientVideoDuration,
    });
    return res.data;
  }

  // ═══ GESTIÓN ═══

  async listarAnalisis(limit = 50): Promise<{ analyses: AudioAnalysis[]; total: number }> {
    const res = await this.api.get('/analyses', { params: { limit } });
    return res.data;
  }

  async obtenerAnalisis(analysisId: string): Promise<{ analysis: AudioAnalysis }> {
    const res = await this.api.get(`/analyses/${analysisId}`);
    return res.data;
  }

  async eliminarAnalisis(analysisId: string): Promise<{ success: boolean }> {
    const res = await this.api.delete(`/analyses/${analysisId}`);
    return res.data;
  }

  async obtenerEstado(analysisId: string): Promise<AudioStatusResponse> {
    const res = await this.api.get(`/analyses/${analysisId}/status`);
    return res.data;
  }

  async reprocesarAnalisis(analysisId: string): Promise<{ success: boolean; job_id?: string }> {
    const res = await this.api.post(`/analyses/${analysisId}/reprocess`);
    return res.data;
  }

  // ═══ TRANSCRIPCIÓN ═══

  async obtenerSegmentos(
    analysisId: string,
    page = 1,
    perPage = 50,
    cursor?: string
  ): Promise<PaginatedSegments & { success: boolean }> {
    const res = await this.api.get(`/analyses/${analysisId}/segments`, {
      params: { page, per_page: perPage, cursor },
    });
    return res.data;
  }

  getEstadoStreamUrl(analysisId: string): string {
    return `${API_BASE_URL}/api/audio/analyses/${analysisId}/status/stream`;
  }

  async obtenerTranscripcion(analysisId: string): Promise<TranscriptionResponse> {
    const res = await this.api.get(`/analyses/${analysisId}/transcription`);
    return res.data;
  }

  // ═══ CONSULTAS ═══

  async consultarContenido(analysisId: string, question: string): Promise<AudioQueryResult> {
    const res = await this.api.post(`/analyses/${analysisId}/query`, { question });
    return res.data;
  }

  async buscarEnTranscripcion(analysisId: string, query: string): Promise<AudioSearchResult> {
    const res = await this.api.get(`/analyses/${analysisId}/search`, {
      params: { q: query },
    });
    return res.data;
  }

  // ═══ UTILIDADES ═══

  formatTimestamp(seconds: number): string {
    const total = Math.floor(seconds);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) {
      return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }

  formatDuration(seconds: number): string {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
  }

  getEstadoLabel(estado: string): string {
    const labels: Record<string, string> = {
      pending: 'Pendiente',
      uploading: 'Subiendo',
      extracting_audio: 'Extrayendo audio',
      audio_ready: 'Audio listo',
      transcribing: 'Transcribiendo',
      transcribed: 'Transcrito',
      indexing: 'Indexando',
      completed: 'Completado',
      cancelled: 'Cancelado',
      error: 'Error',
    };
    return labels[estado] || estado;
  }

  getEstadoColor(estado: string): string {
    const colors: Record<string, string> = {
      pending: 'text-yellow-500',
      uploading: 'text-blue-400',
      extracting_audio: 'text-blue-500',
      audio_ready: 'text-cyan-500',
      transcribing: 'text-indigo-500',
      transcribed: 'text-purple-500',
      indexing: 'text-purple-500',
      completed: 'text-green-500',
      cancelled: 'text-gray-500',
      error: 'text-red-500',
    };
    return colors[estado] || 'text-gray-400';
  }

  isProcessing(estado: string): boolean {
    return ['pending', 'uploading', 'extracting_audio', 'audio_ready', 'transcribing', 'transcribed', 'indexing'].includes(estado);
  }
}

export const audioAnalysisService = new AudioAnalysisService();
