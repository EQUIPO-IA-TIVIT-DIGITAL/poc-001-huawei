import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';
import { authService } from '../services/auth';
import type { User } from '../services/auth';

const sampleUser: User = {
    id: 'u-1',
    username: 'ana',
    email: 'ana@test.local',
    nombre: 'Ana',
    rol: 'socio',
};

function Probe() {
    const { user, isLoading, login, logout, updateUser } = useAuth();
    return (
        <div>
            <span data-testid="user">{user ? user.username : 'none'}</span>
            <span data-testid="loading">{String(isLoading)}</span>
            <button onClick={() => login({ username: 'ana', password: 'x' })}>login</button>
            <button onClick={() => logout()}>logout</button>
            <button onClick={() => updateUser({ nombre: 'Modificada' })}>update</button>
        </div>
    );
}

describe('AuthContext', () => {
    const fetchMock = vi.fn();

    function mockFetch(impl: () => Promise<Response>) {
        fetchMock.mockReset();
        fetchMock.mockImplementation(impl);
        vi.stubGlobal('fetch', fetchMock);
    }

    beforeEach(() => {
        localStorage.clear();
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        localStorage.clear();
    });

    it('arranca cargando y termina sin usuario cuando no hay sesión', async () => {
        mockFetch(() =>
            Promise.resolve(
                new Response(JSON.stringify({ authenticated: false, user: null }), { status: 200 }),
            ),
        );
        render(
            <AuthProvider>
                <Probe />
            </AuthProvider>,
        );
        expect(screen.getByTestId('loading').textContent).toBe('true');
        await waitFor(() =>
            expect(screen.getByTestId('loading').textContent).toBe('false'),
        );
        expect(screen.getByTestId('user').textContent).toBe('none');
    });

    it('restaura usuario de localStorage de inmediato (fast path)', async () => {
        localStorage.setItem('accessfan_user', JSON.stringify(sampleUser));
        mockFetch(() =>
            Promise.resolve(
                new Response(
                    JSON.stringify({ authenticated: true, user: sampleUser }),
                    { status: 200 },
                ),
            ),
        );
        render(
            <AuthProvider>
                <Probe />
            </AuthProvider>,
        );
        // Fast path: usuario visible antes de que termine la verificación
        expect(screen.getByTestId('user').textContent).toBe('ana');
        await waitFor(() =>
            expect(screen.getByTestId('loading').textContent).toBe('false'),
        );
        expect(screen.getByTestId('user').textContent).toBe('ana');
    });

    it('login exitoso establece el usuario', async () => {
        mockFetch(() =>
            Promise.resolve(
                new Response(JSON.stringify({ success: true, user: sampleUser }), { status: 200 }),
            ),
        );
        render(
            <AuthProvider>
                <Probe />
            </AuthProvider>,
        );
        await waitFor(() =>
            expect(screen.getByTestId('loading').textContent).toBe('false'),
        );

        await act(async () => {
            screen.getByText('login').click();
        });
        await waitFor(() =>
            expect(screen.getByTestId('user').textContent).toBe('ana'),
        );
    });

    it('logout limpia el usuario', async () => {
        localStorage.setItem('accessfan_user', JSON.stringify(sampleUser));
        mockFetch(() =>
            Promise.resolve(
                new Response(JSON.stringify({ authenticated: true, user: sampleUser }), { status: 200 }),
            ),
        );
        render(
            <AuthProvider>
                <Probe />
            </AuthProvider>,
        );
        await waitFor(() =>
            expect(screen.getByTestId('loading').textContent).toBe('false'),
        );

        act(() => {
            screen.getByText('logout').click();
        });
        expect(screen.getByTestId('user').textContent).toBe('none');
    });

    it('updateUser modifica el estado y localStorage', async () => {
        localStorage.setItem('accessfan_user', JSON.stringify(sampleUser));
        mockFetch(() =>
            Promise.resolve(
                new Response(JSON.stringify({ authenticated: true, user: sampleUser }), { status: 200 }),
            ),
        );
        render(
            <AuthProvider>
                <Probe />
            </AuthProvider>,
        );
        await waitFor(() =>
            expect(screen.getByTestId('loading').textContent).toBe('false'),
        );

        act(() => {
            screen.getByText('update').click();
        });
        await waitFor(() =>
            expect(screen.getByTestId('user').textContent).toBe('ana'),
        );
        const stored = JSON.parse(localStorage.getItem('accessfan_user')!);
        expect(stored.nombre).toBe('Modificada');
    });

    it('verifySession con error de red mantiene la sesión actual', async () => {
        localStorage.setItem('accessfan_user', JSON.stringify(sampleUser));
        mockFetch(() => Promise.reject(new TypeError('network down')));
        render(
            <AuthProvider>
                <Probe />
            </AuthProvider>,
        );
        await waitFor(() =>
            expect(screen.getByTestId('loading').textContent).toBe('false'),
        );
        // undefined (red) => no toca el estado: usuario se conserva
        expect(screen.getByTestId('user').textContent).toBe('ana');
    });

    it('useAuth sin provider lanza error descriptivo', () => {
        const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        function Orphan() {
            useAuth();
            return null;
        }
        expect(() => render(<Orphan />)).toThrow('useAuth must be used within an AuthProvider');
        consoleSpy.mockRestore();
    });
});
