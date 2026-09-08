/*** lib/api — fetch wrapper usado por 15+ servicios (artículo 33 imports) ***/
import { getApiBaseUrl } from './backendUrl';

export class AuthError extends Error {
    status = 401;
    constructor(msg = 'Unauthorized') { super(msg); this.name = 'AuthError'; }
}

type ApiOpts = Omit<RequestInit, 'body'> & { body?: BodyInit | null };

function buildUrl(path: string): string {
    if (/^https?:\/\//.test(path)) return path;
    const base = getApiBaseUrl().replace(/\/$/, '');
    const p = path.startsWith('/') ? path : `/${path}`;
    return `${base}${p}`;
}

export async function apiRequest<T>(path: string, opts: ApiOpts = {}): Promise<T> {
    const headers = new Headers(opts.headers as HeadersInit);
    if (!headers.has('X-Requested-With')) headers.set('X-Requested-With', 'XMLHttpRequest');
    if (opts.body && typeof opts.body === 'string' && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
    }
    const res = await fetch(buildUrl(path), {
        ...opts,
        headers,
        credentials: 'include',
    });
    if (res.status === 401) {
        window.dispatchEvent(new CustomEvent('auth:unauthorized'));
        throw new AuthError();
    }
    if (res.status === 204) return undefined as unknown as T;
    const text = await res.text();
    let data: unknown;
    try { data = text ? JSON.parse(text) : undefined; } catch { data = text as unknown; }
    if (!res.ok) {
        const msg = (data as { error?: string; message?: string })?.error
            || (data as { message?: string })?.message
            || `HTTP ${res.status}`;
        throw new Error(msg);
    }
    return data as T;
}
