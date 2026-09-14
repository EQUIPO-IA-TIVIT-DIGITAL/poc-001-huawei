import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { apiRequest, AuthError } from './api';

function jsonResponse(status: number, body: unknown): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}

describe('apiRequest', () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
        vi.stubGlobal('fetch', fetchMock);
        fetchMock.mockReset();
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('añade X-Requested-With y credentials include', async () => {
        fetchMock.mockResolvedValue(jsonResponse(200, { ok: true }));
        await apiRequest('/test');
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toContain('/test');
        expect(init.credentials).toBe('include');
        expect(new Headers(init.headers).get('X-Requested-With')).toBe('XMLHttpRequest');
    });

    it('parsea JSON en respuesta exitosa', async () => {
        fetchMock.mockResolvedValue(jsonResponse(200, { data: [1, 2] }));
        const data = await apiRequest<{ data: number[] }>('/test');
        expect(data.data).toEqual([1, 2]);
    });

    it('lanza AuthError y dispara auth:unauthorized con 401', async () => {
        const listener = vi.fn();
        window.addEventListener('auth:unauthorized', listener);
        fetchMock.mockResolvedValue(jsonResponse(401, { error: 'no auth' }));
        await expect(apiRequest('/test')).rejects.toBeInstanceOf(AuthError);
        expect(listener).toHaveBeenCalledTimes(1);
        window.removeEventListener('auth:unauthorized', listener);
    });

    it('lanza Error con el message del backend en errores 4xx/5xx', async () => {
        fetchMock.mockResolvedValue(jsonResponse(400, { error: 'Datos inválidos' }));
        await expect(apiRequest('/test')).rejects.toThrow('Datos inválidos');
    });

    it('usa message si no hay error, y HTTP <status> como fallback', async () => {
        fetchMock.mockResolvedValue(jsonResponse(500, { message: 'fallo interno' }));
        await expect(apiRequest('/test')).rejects.toThrow('fallo interno');

        fetchMock.mockResolvedValue(new Response('plain text', { status: 502 }));
        await expect(apiRequest('/test')).rejects.toThrow('HTTP 502');
    });

    it('devuelve undefined con 204', async () => {
        fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
        const data = await apiRequest('/test');
        expect(data).toBeUndefined();
    });

    it('establece Content-Type json cuando hay body string', async () => {
        fetchMock.mockResolvedValue(jsonResponse(200, {}));
        await apiRequest('/test', { method: 'POST', body: JSON.stringify({ a: 1 }) });
        const [, init] = fetchMock.mock.calls[0];
        expect(new Headers(init.headers).get('Content-Type')).toBe('application/json');
    });
});
