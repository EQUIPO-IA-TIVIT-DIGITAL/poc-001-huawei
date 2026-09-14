import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getApiBaseUrl } from './backendUrl';

describe('getApiBaseUrl', () => {
    beforeEach(() => {
        vi.unstubAllEnvs();
        // Limpiar window.__ENV__ entre tests
        delete (window as { __ENV__?: unknown }).__ENV__;
    });

    it('usa window.__ENV__ (runtime env.js) con prioridad', () => {
        (window as { __ENV__?: { VITE_API_BASE_URL?: string } }).__ENV__ = {
            VITE_API_BASE_URL: 'http://runtime:9999',
        };
        expect(getApiBaseUrl()).toBe('http://runtime:9999');
    });

    it('elimina slash final de la URL', () => {
        (window as { __ENV__?: { VITE_API_BASE_URL?: string } }).__ENV__ = {
            VITE_API_BASE_URL: 'http://api:5001/',
        };
        expect(getApiBaseUrl()).toBe('http://api:5001');
    });

    it('cae al default localhost:5001 sin runtime ni build env', () => {
        expect(getApiBaseUrl()).toBe('http://localhost:5001');
    });
});
