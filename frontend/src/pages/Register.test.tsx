import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Register from './Register';

const navigateMock = vi.fn();
vi.mock('@tanstack/react-router', () => ({
    useNavigate: () => navigateMock,
    Link: ({ children }: { children: React.ReactNode }) => <a href="/login">{children}</a>,
}));

vi.mock('../i18n', () => ({
    useTranslation: () => ({ t: (key: string) => key }),
}));

function renderRegister() {
    const client = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
        <QueryClientProvider client={client}>
            <Register />
        </QueryClientProvider>,
    );
}

async function fillForm(user: ReturnType<typeof userEvent.setup>, data?: Partial<Record<string, string>>) {
    const d = {
        nombre: 'Ana Perez',
        username: 'ana',
        email: 'ana@test.local',
        password: 'Secret#123',
        confirmPassword: 'Secret#123',
        ...data,
    };
    await user.type(screen.getByLabelText('auth.fullName'), d.nombre);
    await user.type(screen.getByLabelText('auth.username'), d.username);
    await user.type(screen.getByLabelText('auth.email'), d.email);
    await user.type(screen.getByLabelText('auth.password'), d.password);
    await user.type(screen.getByLabelText('auth.confirmPassword'), d.confirmPassword);
    return d;
}

describe('Register', () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
        navigateMock.mockReset();
        fetchMock.mockReset();
        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('renderiza los cinco campos del formulario', () => {
        renderRegister();
        expect(screen.getByLabelText('auth.fullName')).toBeInTheDocument();
        expect(screen.getByLabelText('auth.username')).toBeInTheDocument();
        expect(screen.getByLabelText('auth.email')).toBeInTheDocument();
        expect(screen.getByLabelText('auth.password')).toBeInTheDocument();
        expect(screen.getByLabelText('auth.confirmPassword')).toBeInTheDocument();
    });

    it('contraseñas distintas muestran error local sin llamar a la API', async () => {
        const user = userEvent.setup();
        renderRegister();
        await fillForm(user, { confirmPassword: 'Otra#456' });
        await user.click(screen.getByRole('button'));

        await waitFor(() => {
            expect(screen.getByRole('alert')).toHaveTextContent('auth.passwordMismatch');
        });
        expect(fetchMock).not.toHaveBeenCalled();
        expect(navigateMock).not.toHaveBeenCalled();
    });

    it('registro exitoso envía payload mapeado y navega a /login', async () => {
        const user = userEvent.setup();
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ success: true, message: 'ok' }), { status: 201 }),
        );

        renderRegister();
        const d = await fillForm(user);
        await user.click(screen.getByRole('button'));

        await waitFor(() => {
            expect(navigateMock).toHaveBeenCalled();
        });
        expect(navigateMock).toHaveBeenCalledWith(
            expect.objectContaining({ to: '/login' }),
        );

        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toContain('/registro/socio');
        const body = JSON.parse(init.body);
        expect(body.username).toBe(d.username);
        expect(body.nombre_completo).toBe(d.nombre); // mapeo nombre -> nombre_completo
        expect(body.email).toBe(d.email);
        expect(body.password).toBe(d.password);
        expect(body.password_confirm).toBe(d.confirmPassword); // mapeo confirmPassword
    });

    it('error del backend (duplicado) muestra el mensaje y no navega', async () => {
        const user = userEvent.setup();
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ error: 'El username ya está registrado' }), { status: 409 }),
        );

        renderRegister();
        await fillForm(user);
        await user.click(screen.getByRole('button'));

        const alert = await screen.findByRole('alert');
        expect(alert).toHaveTextContent('El username ya está registrado');
        expect(navigateMock).not.toHaveBeenCalled();
    });
});
