import { apiRequest, AuthError } from '../lib/api';

export interface User {
    id: string;
    username?: string;
    email: string;
    nombre: string;
    nombre_completo?: string;
    rol: 'socio';
    foto_url?: string;
    [key: string]: any;
}

interface AuthResponse {
    success: boolean;
    user: User;
}

interface LoginApiResponse {
    success: boolean;
    user?: User;
}

interface RegisterData {
    username: string;
    password: string;
    password_confirm: string;
    nombre_completo: string;
    email: string;
}

/**
 * Only persist the minimum non-sensitive fields to localStorage.
 * foto_url is intentionally excluded: it contains expiring GCS signed URLs
 * that should be fetched fresh from the server on each session.
 * Arbitrary extra fields ([key: string]: any) are excluded to avoid
 * accidentally caching sensitive data that might be added in the future.
 */
function _sanitizeForStorage(user: User): Pick<User, 'id' | 'username' | 'email' | 'nombre' | 'nombre_completo' | 'rol'> {
    return {
        id: user.id,
        username: user.username,
        email: user.email,
        nombre: user.nombre,
        nombre_completo: user.nombre_completo,
        rol: user.rol,
    };
}

export const authService = {
    // ==================== AUTENTICACIÓN ====================

    /**
     * POST /login - Iniciar sesión con usuario y contraseña
     */
    async login(credentials: { username: string; password?: string }): Promise<User | null> {
        const response = await apiRequest<LoginApiResponse>('/login', {
            method: 'POST',
            body: JSON.stringify(credentials),
        });

        if (response?.user) {
            localStorage.setItem('accessfan_user', JSON.stringify(_sanitizeForStorage(response.user)));
            return response.user;
        }
        return null;
    },

    /**
     * GET /api/auth/microsoft/login - Iniciar sesión con Microsoft (Azure AD)
     * Redirige al portal de Microsoft — el backend maneja todo el flujo OAuth2.
     */
    loginWithMicrosoft(): void {
        const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001';
        window.location.href = `${apiBase}/api/auth/microsoft/login`;
    },

    /**
     * POST /logout - Cerrar sesión
     */
    async logout() {
        try {
            await apiRequest('/logout', { method: 'POST' });
        } catch (error) {
            console.error('Logout failed on server', error);
        }
        localStorage.removeItem('accessfan_user');
    },

    /**
     * GET /api/check-auth - Verificar autenticación
     */
    async verifySession(): Promise<User | null | undefined> {
        try {
            const response = await apiRequest<{ authenticated: boolean; user: User | null }>('/api/check-auth');
            if (response.authenticated && response.user) {
                localStorage.setItem('accessfan_user', JSON.stringify(_sanitizeForStorage(response.user)));
                return response.user;
            } else {
                this.logout();
                return null;
            }
        } catch (error) {
            // AuthError means 401 — session expired, treat as logged out
            if (error instanceof AuthError) {
                this.logout();
                return null;
            }
            console.error('Session verification failed (network/server error)', error);
            return undefined;
        }
    },

    /**
     * POST /registro/socio - Registrar nuevo usuario socio
     */
    async register(data: RegisterData) {
        return apiRequest<AuthResponse>('/registro/socio', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    // ==================== PERFIL ====================

    /**
     * GET /api/v1/auth/me - Obtener perfil actual del backend
     */
    async getProfile() {
        return apiRequest<{ success: boolean; user: User }>('/api/v1/auth/me');
    },

    /**
     * PUT /api/v1/auth/profile - Actualizar perfil
     */
    async updateProfile(data: { nombre_completo: string; email: string }) {
        return apiRequest<{ success: boolean; user: User }>('/api/v1/auth/profile', {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    },

    /**
     * POST /api/v1/auth/change-password - Cambiar contraseña
     */
    async changePassword(data: { current_password: string; new_password: string }) {
        return apiRequest<{ success: boolean; message: string }>('/api/v1/auth/change-password', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    // ==================== UTILIDADES ====================

    getUser(): User | null {
        const userStr = localStorage.getItem('accessfan_user');
        if (!userStr) return null;
        try {
            return JSON.parse(userStr);
        } catch {
            return null;
        }
    },

    isAuthenticated(): boolean {
        return !!localStorage.getItem('accessfan_user');
    },

    updateLocalUser(updates: Partial<User>) {
        const user = this.getUser();
        if (user) {
            const updated = { ...user, ...updates };
            localStorage.setItem('accessfan_user', JSON.stringify(_sanitizeForStorage(updated as User)));
        }
    }
};
