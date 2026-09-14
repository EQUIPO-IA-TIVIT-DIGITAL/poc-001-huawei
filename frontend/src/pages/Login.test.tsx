import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Login from './Login';
import { AuthProvider } from '../context/AuthContext';

// Mocks de TanStack Router: el componente usa useNavigate/useSearch/Link
const navigateMock = vi.fn();
let searchParams: Record<string, string> = {};
vi.mock('@tanstack/react-router', () => ({
    useNavigate: () => navigateMock,
    useSearch: () => searchParams,
    Link: ({ children }: { children: React.ReactNode }) => <a href="/register">{children}</a>,
}));

// Mock de i18n: devolvemos la clave tal cual
vi.mock('../i18n', () => ({
    useTranslation: () => ({ t: (key: string) => key }),
}));

function renderLogin() {
    const client = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
        <QueryClientProvider client={client}>
            <AuthProvider>
                <Login />
            </AuthProvider>
        </QueryClientProvider>,
    );
}

describe('Login', () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
        localStorage.clear();
        navigateMock.mockReset();
        fetchMock.mockReset();
        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        localStorage.clear();
    });

    it('renderiza el formulario con campos usuario y contraseña', () => {
        renderLogin();
        expect(screen.getByLabelText('auth.username')).toBeInTheDocument();
        expect(screen.getByLabelText('auth.password')).toBeInTheDocument();
        expect(screen.getByRole('button')).toBeInTheDocument();
    });
    it('login exitoso navega a /dashboard', async () => {
        const user = userEvent.setup();
        fetchMock.mockImplementation((url: string) => {
            if (String(url).includes('/login')) {
                return Promise.resolve(
                    new Response(
                        JSON.stringify({
                            success: true,
                            user: { id: 'u-1', username: 'ana', email: 'a@a', nombre: 'Ana', rol: 'socio' },
                        }),
                        { status: 200 },
                    ),
                );
            }
            return Promise.resolve(
                new Response(JSON.stringify({ authenticated: false, user: null }), { status: 200 }),
            );
        });

        renderLogin();
        await user.type(screen.getByLabelText('auth.username'), 'ana');
        await user.type(screen.getByLabelText('auth.password'), 'Secret#1');
        await user.click(screen.getByRole('button'));

        await waitFor(() => {
            expect(navigateMock).toHaveBeenCalledWith({ to: '/dashboard' });
        });
    });

    it('login fallido muestra el error del backend', async () => {
        const user = userEvent.setup();
        fetchMock.mockImplementation((url: string) => {
            if (String(url).includes('/login')) {
                return Promise.resolve(
                    new Response(JSON.stringify({ error: 'Credenciales inválidas' }), { status: 401 }),
                );
            }
            return Promise.resolve(
                new Response(JSON.stringify({ authenticated: false, user: null }), { status: 200 }),
            );
        });

        renderLogin();
        await user.type(screen.getByLabelText('auth.username'), 'ana');
        await user.type(screen.getByLabelText('auth.password'), 'mala');
        await user.click(screen.getByRole('button'));

        // 401 corta-circuito en apiRequest: el mensaje es el genérico del AuthError
        const alert = await screen.findByRole('alert');
        expect(alert).toHaveTextContent('Unauthorized');
        expect(navigateMock).not.toHaveBeenCalled();
    });

    it('respects redirect param: navega a la ruta indicada', async () => {
        searchParams = { redirect: '/workspaces' };
        try {
            const user = userEvent.setup();
            fetchMock.mockImplementation((url: string) => {
                if (String(url).includes('/login')) {
                    return Promise.resolve(
                        new Response(
                            JSON.stringify({
                                success: true,
                                user: { id: 'u-1', username: 'ana', email: 'a@a', nombre: 'Ana', rol: 'socio' },
                            }),
                            { status: 200 },
                        ),
                    );
                }
                return Promise.resolve(
                    new Response(JSON.stringify({ authenticated: false, user: null }), { status: 200 }),
                );
            });

            renderLogin();
            await user.type(screen.getByLabelText('auth.username'), 'ana');
            await user.type(screen.getByLabelText('auth.password'), 'Secret#1');
            await user.click(screen.getByRole('button'));

            await waitFor(() => {
                expect(navigateMock).toHaveBeenCalledWith({ to: '/workspaces' });
            });
        } finally {
            searchParams = {};
        }
    });
});
