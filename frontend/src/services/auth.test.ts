import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { authService } from './auth';
import { AuthError } from '../lib/api';

function jsonResponse(status: number, body: unknown): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}

const sampleUser = {
    id: 'u-1',
    username: 'ana',
    email: 'ana@test.local',
    nombre: 'Ana',
    rol: 'socio' as const,
    foto_url: 'https://signed.example/expiring',
};

describe('authService', () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
        vi.stubGlobal('fetch', fetchMock);
        fetchMock.mockReset();
        localStorage.clear();
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        localStorage.clear();
    });

    describe('login', () => {
        it('guarda usuario sanitizado en localStorage (sin foto_url)', async () => {
            fetchMock.mockResolvedValue(jsonResponse(200, { success: true, user: sampleUser }));
            const user = await authService.login({ username: 'ana', password: 'Secret#123' });
            expect(user?.username).toBe('ana');

            const stored = JSON.parse(localStorage.getItem('accessfan_user')!);
            expect(stored.id).toBe('u-1');
            expect(stored.foto_url).toBeUndefined();
        });

        it('devuelve null si la respuesta no trae usuario', async () => {
            fetchMock.mockResolvedValue(jsonResponse(200, { success: true }));
            const user = await authService.login({ username: 'ana' });
            expect(user).toBeNull();
            expect(localStorage.getItem('accessfan_user')).toBeNull();
        });

        it('lanza AuthError con credenciales inválidas (401 corta-circuito)', async () => {
            fetchMock.mockResolvedValue(jsonResponse(401, { error: 'Credenciales inválidas' }));
            await expect(
                authService.login({ username: 'ana', password: 'mala' }),
            ).rejects.toBeInstanceOf(AuthError);
        });
    });

    describe('verifySession', () => {
        it('autenticado: guarda usuario y lo devuelve', async () => {
            fetchMock.mockResolvedValue(
                jsonResponse(200, { authenticated: true, user: sampleUser }),
            );
            const user = await authService.verifySession();
            expect(user?.id).toBe('u-1');
            expect(authService.isAuthenticated()).toBe(true);
            expect(localStorage.getItem('accessfan_user')).not.toBeNull();
        });

        it('no autenticado: limpia sesión y devuelve null (logout sin await)', async () => {
            localStorage.setItem('accessfan_user', JSON.stringify(sampleUser));
            fetchMock.mockResolvedValue(jsonResponse(200, { authenticated: false, user: null }));
            const user = await authService.verifySession();
            expect(user).toBeNull();
            // logout() se invoca sin await: la limpieza ocurre tras el tick de red
            await vi.waitFor(() => {
                expect(localStorage.getItem('accessfan_user')).toBeNull();
            });
        });

        it('error de red: devuelve undefined y NO limpia la sesión', async () => {
            localStorage.setItem('accessfan_user', JSON.stringify(sampleUser));
            fetchMock.mockRejectedValue(new TypeError('network down'));
            const user = await authService.verifySession();
            expect(user).toBeUndefined();
            expect(localStorage.getItem('accessfan_user')).not.toBeNull();
        });
    });

    describe('logout', () => {
        it('limpia localStorage aunque el servidor falle', async () => {
            localStorage.setItem('accessfan_user', JSON.stringify(sampleUser));
            fetchMock.mockRejectedValue(new TypeError('network down'));
            await authService.logout();
            expect(localStorage.getItem('accessfan_user')).toBeNull();
        });
    });

    describe('getUser / updateLocalUser', () => {
        it('getUser parsea localStorage y devuelve null con JSON inválido', () => {
            expect(authService.getUser()).toBeNull();
            localStorage.setItem('accessfan_user', 'no-json{');
            expect(authService.getUser()).toBeNull();
            localStorage.setItem('accessfan_user', JSON.stringify(sampleUser));
            expect(authService.getUser()?.username).toBe('ana');
        });

        it('updateLocalUser persiste cambios sanitizados', async () => {
            fetchMock.mockResolvedValue(jsonResponse(200, { success: true, user: sampleUser }));
            await authService.login({ username: 'ana' });

            authService.updateLocalUser({ nombre: 'Ana Modificada' });
            const stored = JSON.parse(localStorage.getItem('accessfan_user')!);
            expect(stored.nombre).toBe('Ana Modificada');
            expect(stored.rol).toBe('socio');
        });

        it('updateLocalUser no falla sin usuario en localStorage', () => {
            expect(() => authService.updateLocalUser({ nombre: 'x' })).not.toThrow();
        });
    });
});
