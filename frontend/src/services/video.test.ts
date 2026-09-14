import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { videoService } from './video';

function jsonResponse(status: number, body: unknown): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}

describe('videoService', () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
        vi.stubGlobal('fetch', fetchMock);
        fetchMock.mockReset();
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('getMyVideos sin usuario llama a /socio/mis-videos', async () => {
        fetchMock.mockResolvedValue(jsonResponse(200, { success: true, videos: [], count: 0 }));
        await videoService.getMyVideos();
        const [url] = fetchMock.mock.calls[0];
        expect(url).toContain('/socio/mis-videos');
    });

    it('getMyVideos con usuario añade query param', async () => {
        fetchMock.mockResolvedValue(jsonResponse(200, { success: true, videos: [], count: 0 }));
        await videoService.getMyVideos('ana');
        const [url] = fetchMock.mock.calls[0];
        expect(url).toContain('/socio/mis-videos?usuario=ana');
    });

    it('getVideo construye la ruta con el id', async () => {
        fetchMock.mockResolvedValue(
            jsonResponse(200, { success: true, video: { id: 'v-9' } }),
        );
        await videoService.getVideo('v-9');
        const [url] = fetchMock.mock.calls[0];
        expect(url).toContain('/socio/video/v-9/details');
    });

    it('getVideoStatus usa GET', async () => {
        fetchMock.mockResolvedValue(jsonResponse(200, { status: 'processing' }));
        await videoService.getVideoStatus('v-1');
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toContain('/socio/video/v-1/status');
        expect(init.method).toBe('GET');
    });

    it('requestRevision envía motivo como JSON POST', async () => {
        fetchMock.mockResolvedValue(
            jsonResponse(200, { success: true, message: 'ok', video: { id: 'v-1', estado: 'EN_REVISION' } }),
        );
        await videoService.requestRevision('v-1', 'contenido correcto');
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toContain('/socio/video/v-1/solicitar-revision');
        expect(init.method).toBe('POST');
        expect(init.body).toBe(JSON.stringify({ motivo: 'contenido correcto' }));
    });

    it('deleteVideo usa DELETE', async () => {
        fetchMock.mockResolvedValue(jsonResponse(200, { success: true, message: 'eliminado' }));
        await videoService.deleteVideo('v-1');
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toContain('/socio/videos/v-1');
        expect(init.method).toBe('DELETE');
    });

    it('cancelProcessing usa POST sin body', async () => {
        fetchMock.mockResolvedValue(jsonResponse(200, { success: true, message: 'cancelado' }));
        await videoService.cancelProcessing('v-1');
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toContain('/socio/video/v-1/cancel');
        expect(init.method).toBe('POST');
    });

    it('submitClarification envía answers serializadas', async () => {
        fetchMock.mockResolvedValue(jsonResponse(200, { success: true, message: 'ok', video_id: 'v-1' }));
        await videoService.submitClarification('v-1', { q1: 'a1' });
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toContain('/socio/video/v-1/clarify');
        expect(init.body).toBe(JSON.stringify({ answers: { q1: 'a1' } }));
    });

    it('propaga errores del backend', async () => {
        fetchMock.mockResolvedValue(jsonResponse(404, { error: 'Video no encontrado' }));
        await expect(videoService.getVideo('v-x')).rejects.toThrow('Video no encontrado');
    });
});
