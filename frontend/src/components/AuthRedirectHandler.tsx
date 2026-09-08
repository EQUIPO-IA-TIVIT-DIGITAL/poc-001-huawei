import React, { useEffect } from 'react';
import { useNavigate, useLocation } from '@tanstack/react-router';
import { useAuth } from '../context/AuthContext';

export function AuthRedirectHandler() {
    const navigate = useNavigate();
    const location = useLocation();
    const { user, isLoading, logout, verifySession } = useAuth();

    // Rutas públicas que no requieren autenticación
    const publicRoutes = ['/login', '/register', '/'];
    const isPublicRoute = publicRoutes.some(path => location.pathname === path || (path !== '/' && location.pathname.startsWith(path + '/')));

    // 1. Manejo de error 401 global (cuando una petición falla)
    useEffect(() => {
        const handleUnauthorized = () => {
            console.warn('Unauthorized access detected (Event). Redirecting...');
            logout();

            if (!isPublicRoute) {
                navigate({
                    to: '/login',
                    search: {
                        redirect: location.href,
                    },
                });
            }
        };

        window.addEventListener('auth:unauthorized', handleUnauthorized);
        return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
    }, [navigate, location.pathname, logout, isPublicRoute]);

    // 2. Proteger rutas donde el usuario local ya no existe
    useEffect(() => {
        if (!isLoading && !user && !isPublicRoute) {
            console.warn('User session not found on protected route. Redirecting...');
            navigate({
                to: '/login',
                search: { redirect: location.href }
            });
        }
    }, [user, isLoading, isPublicRoute, navigate, location.href]);

    // 3. Verificación proactiva inteligente
    // Se ejecuta al cambiar de ruta, pero NO en login/registro
    // Usamos useRef para asegurar que solo se ejecute cuando cambia la ruta, no cuando se actualiza el user
    const prevPathRef = React.useRef(location.pathname);

    useEffect(() => {
        // Solo ejecutar si la ruta cambió realmente
        const pathChanged = prevPathRef.current !== location.pathname;

        if (pathChanged) {
            prevPathRef.current = location.pathname;

            if (!isPublicRoute && !isLoading && user) {
                // Verificar si la sesión de backend sigue viva
                verifySession();
            }
        }
    }, [location.pathname, isPublicRoute, isLoading, user, verifySession]);

    return null;
}
