import { apiRequest } from '../lib/api';
import { getApiBaseUrl } from '../lib/backendUrl';

const API_BASE_URL = getApiBaseUrl();

// ==================== INTERFACES ====================

export interface Video {
    id: string;
    descripcion: string;
    estado: string;
    resultado_ia: string;
    fecha_procesamiento: string;
    titulo?: string;
    video_url?: string;
    thumbnail_url?: string;
    duracion_segundos?: number;
    gcs_uri?: string;
    metadatos_ia?: any;
    razon_rechazo?: string;
}

export interface RequestRevisionResponse {
    success: boolean;
    message: string;
    video: {
        id: string;
        estado: string;
    };
}

export interface ProcessingStatusResponse {
    status: 'pending' | 'processing' | 'completed' | 'error' | 'cancelled';
    step?: number;
    message?: string;
    details?: any;
    final_result?: {
        video: any;
        finalStatus: 'approved' | 'rejected' | 'review' | 'unknown';
    };
    error?: any;
}

export interface UploadResponse {
    success: boolean;
    video_id: string;
    message: string;
}

// ==================== SERVICE ====================

export const videoService = {
    // ==================== VIDEOS DEL USUARIO ====================

    /**
     * GET /socio/mis-videos - Listar videos del usuario
     * GET /api/v1/videos - Alternativa versionada
     */
    async getMyVideos(username?: string) {
        const path = username ? `/socio/mis-videos?usuario=${username}` : '/socio/mis-videos';
        return apiRequest<{ success: boolean; videos: Video[]; count: number }>(path);
    },

    /**
     * GET /socio/video/{video_id}/details - Obtener detalle de video
     * GET /api/v1/videos/{video_id} - Alternativa versionada
     */
    async getVideo(videoId: string) {
        return apiRequest<{ success: boolean; video: Video }>(`/socio/video/${videoId}/details`);
    },

    /**
     * GET /api/v1/storage/video/{video_id}/url - Obtener URL firmada
     */
    async getSignedUrl(videoId: string) {
        return apiRequest<{ success: boolean; signed_url: string; expires_in_minutes: number }>(
            `/api/v1/storage/video/${videoId}/url`,
        );
    },

    /**
     * POST /upload - Subir video (usa FormData, no JSON)
     * Nota: Este método retorna el XMLHttpRequest para poder manejar progreso externamente
     */
    uploadVideo(
        file: File,
        descripcion?: string,
        onProgress?: (percent: number) => void,
        workspaceId?: string,
    ): Promise<UploadResponse> {
        return new Promise((resolve, reject) => {
            const formData = new FormData();
            formData.append('video', file);
            if (descripcion) {
                formData.append('descripcion', descripcion);
            }
            if (workspaceId) {
                formData.append('workspace_id', workspaceId);
            }

            const xhr = new XMLHttpRequest();
            const _API_BASE_URL = getApiBaseUrl();

            xhr.open('POST', `${_API_BASE_URL}/socio/upload`);
            xhr.withCredentials = true;

            if (onProgress) {
                xhr.upload.onprogress = (e) => {
                    if (e.lengthComputable) {
                        onProgress(Math.round((e.loaded / e.total) * 100));
                    }
                };
            }

            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        resolve(response);
                    } catch (e) {
                        reject(new Error('Invalid JSON response'));
                    }
                } else {
                    reject(new Error(xhr.statusText || 'Upload failed'));
                }
            };

            xhr.onerror = () => reject(new Error('Network error'));
            xhr.send(formData);
        });
    },

    // ==================== ACCIONES DEL USUARIO ====================

    /**
     * POST /video/{video_id}/solicitar-revision - Solicitar revisión manual
     * POST /socio/video/{video_id}/solicitar-revision - Alternativa
     */
    async requestRevision(videoId: string, motivo: string) {
        return apiRequest<RequestRevisionResponse>(`/socio/video/${videoId}/solicitar-revision`, {
            method: 'POST',
            body: JSON.stringify({ motivo }),
        });
    },

    /**
     * DELETE /socio/videos/{video_id} - Eliminar video
     */
    async deleteVideo(videoId: string) {
        return apiRequest<{ success: boolean; message: string }>(`/socio/videos/${videoId}`, {
            method: 'DELETE',
        });
    },

    // ==================== PROCESAMIENTO ====================

    /**
     * GET /socio/video/{video_id}/status - Obtener estado de procesamiento
     */
    async getVideoStatus(videoId: string) {
        return apiRequest<ProcessingStatusResponse>(`/socio/video/${videoId}/status`, {
            method: 'GET',
        });
    },

    /**
     * SSE /socio/video/{video_id}/stream_status - Stream de estado en tiempo real
     */
    getVideoStatusStream(videoId: string): EventSource {
        return new EventSource(`${API_BASE_URL}/socio/video/${videoId}/stream_status`);
    },

    /**
     * POST /socio/video/{video_id}/start_processing - Iniciar procesamiento
     */
    async startProcessing(videoId: string) {
        return apiRequest<{ success: boolean; message: string }>(
            `/socio/video/${videoId}/start_processing`,
            {
                method: 'POST',
            },
        );
    },

    /**
     * POST /socio/video/{video_id}/cancel - Cancelar procesamiento
     */
    async cancelProcessing(videoId: string) {
        return apiRequest<{ success: boolean; message: string }>(`/socio/video/${videoId}/cancel`, {
            method: 'POST',
        });
    },

    /**
     * POST /socio/video/{video_id}/clarify - Enviar respuestas a preguntas de clarificación
     */
    async submitClarification(videoId: string, answers: Record<string, string>) {
        return apiRequest<{ success: boolean; message: string; video_id: string }>(
            `/socio/video/${videoId}/clarify`,
            {
                method: 'POST',
                body: JSON.stringify({ answers }),
            },
        );
    },
};
