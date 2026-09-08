import { apiRequest } from '../lib/api';

export interface Workspace {
    id: string;
    nombre: string;
    descripcion: string;
    contexto: string;
    color: string;
    icono_url?: string;
    es_general: boolean;
    es_exhaustivo?: boolean;
    estadisticas: {
        total_videos: number;
        aprobados: number;
        rechazados: number;
        en_revision: number;
        duracion_total_segundos: number;
        ultima_actividad: string;
    };
    fecha_creacion: string;
    fecha_modificacion?: string;
    metadatos?: any;
}

export interface CreateWorkspaceRequest {
    nombre: string;
    descripcion?: string;
    contexto?: string;
    color?: string;
    categoria?: string;
    tipo_contenido?: string;
    elementos_visuales?: string;
    nivel_tolerancia?: string;
    icono_url?: string;
    es_exhaustivo?: boolean;
}

export const workspaceService = {
    // CRUD
    async createWorkspace(data: CreateWorkspaceRequest): Promise<Workspace> {
        const response = await apiRequest<{ success: boolean; workspace: Workspace }>(
            '/workspaces',
            {
                method: 'POST',
                body: JSON.stringify(data),
            },
        );
        if (!response?.workspace) throw new Error('No se pudo crear el proyecto');
        return response.workspace;
    },

    async listWorkspaces(ordenarPor: string = 'fecha_creacion'): Promise<Workspace[]> {
        const response = await apiRequest<{ success: boolean; workspaces: Workspace[] }>(
            `/workspaces?ordenar_por=${ordenarPor}`,
        );
        return response?.workspaces || [];
    },

    async getWorkspace(id: string): Promise<Workspace> {
        const response = await apiRequest<{ success: boolean; workspace: Workspace }>(
            `/workspaces/${id}`,
        );
        if (!response?.workspace) throw new Error('Proyecto no encontrado');
        return response.workspace;
    },

    async updateWorkspace(id: string, data: Partial<CreateWorkspaceRequest>): Promise<void> {
        await apiRequest(`/workspaces/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    },

    async deleteWorkspace(
        id: string,
        accion: 'mover_general' | 'prohibir' = 'mover_general',
    ): Promise<void> {
        await apiRequest(`/workspaces/${id}?accion=${accion}`, {
            method: 'DELETE',
        });
    },

    async duplicateWorkspace(id: string, nuevoNombre: string): Promise<Workspace> {
        const response = await apiRequest<{ success: boolean; workspace: Workspace }>(
            `/workspaces/${id}/duplicate`,
            {
                method: 'POST',
                body: JSON.stringify({ nuevo_nombre: nuevoNombre }),
            },
        );
        if (!response?.workspace) throw new Error('No se pudo duplicar el proyecto');
        return response.workspace;
    },

    async getWorkspaceVideos(id: string): Promise<any[]> {
        const response = await apiRequest<{ success: boolean; videos: any[] }>(
            `/workspaces/${id}/videos`,
        );
        return response?.videos || [];
    },

    // Búsqueda
    async searchWorkspaces(query: string): Promise<Workspace[]> {
        if (!query.trim()) return [];
        const response = await apiRequest<{
            success: boolean;
            resultados: Workspace[];
            total: number;
        }>(`/workspaces/search?q=${encodeURIComponent(query)}`);
        return response?.resultados || [];
    },

    // AI Context Validation
    async validateWorkspaceContext(id: string): Promise<{ validacion: { suficiente: boolean; preguntas?: string[] } }> {
        const response = await apiRequest<{ validacion: { suficiente: boolean; preguntas?: string[] } }>(
            `/workspaces/${id}/chat/validate`,
            { method: 'POST' }
        );
        return response;
    },

    async improveWorkspaceContext(id: string, respuestas: string[]): Promise<void> {
        await apiRequest(`/workspaces/${id}/chat/improve`, {
            method: 'POST',
            body: JSON.stringify({ respuestas }),
        });
    },

    // Helpers
    getLastUsedWorkspace(): string | null {
        return localStorage.getItem('lastWorkspaceId');
    },

    setLastUsedWorkspace(id: string): void {
        localStorage.setItem('lastWorkspaceId', id);
    },

    clearLastUsedWorkspace(): void {
        localStorage.removeItem('lastWorkspaceId');
    },
};
