// backendUrl — resuelve VITE_API_BASE_URL con fallback runtime env.js

declare global { interface Window { __ENV__?: { VITE_API_BASE_URL?: string } } }

export function getApiBaseUrl(): string {
    // runtime env.js inyectado por Nginx (ver frontend/entrypoint.sh)
    const runtime = typeof window !== 'undefined' ? window.__ENV__?.VITE_API_BASE_URL : undefined;
    const vite = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE_URL;
    return (runtime || vite || 'http://localhost:5001').replace(/\/$/, '');
}

export async function fetchWithBaseFallback(path: string, init?: RequestInit): Promise<Response> {
    const url = path.startsWith('http') ? path : `${getApiBaseUrl()}${path.startsWith('/') ? '' : '/'}${path}`;
    return fetch(url, init);
}
