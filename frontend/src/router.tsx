import {
    createRouter,
    createRootRoute,
    createRoute,
    Outlet,
    redirect,
} from '@tanstack/react-router';
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools';
import { AuthRedirectHandler } from './components/AuthRedirectHandler';
import { authService } from './services/auth';
import { lazy, Suspense } from 'react';

// Layouts
import { AuthLayout } from './layouts/AuthLayout';
import { DashboardLayout } from './layouts/DashboardLayout';

// Lazy Load Pages
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const MyVideos = lazy(() => import('./pages/MyVideos'));
const Workspaces = lazy(() => import('./pages/Workspaces'));
const WorkspaceDetail = lazy(() => import('./pages/WorkspaceDetail'));
const Upload = lazy(() => import('./pages/Upload'));
const Profile = lazy(() => import('./pages/Profile'));
const VideoProcessing = lazy(() => import('./pages/VideoProcessing'));
const VideoDetailsPage = lazy(() => import('./pages/VideoDetailsPage'));
const SecurityVideos = lazy(() => import('./pages/SecurityVideos'));
const SecurityUpload = lazy(() => import('./pages/SecurityUpload'));
const SecurityVideoDetail = lazy(() => import('./pages/SecurityVideoDetail'));
const SecurityAnalysis = lazy(() => import('./pages/SecurityAnalysis'));
const OperationalVideos = lazy(() => import('./pages/OperationalVideos'));
const OperationalUpload = lazy(() => import('./pages/OperationalUpload'));
const OperationalVideoDetail = lazy(() => import('./pages/OperationalVideoDetail'));
const AudioAnalyses = lazy(() => import('./pages/AudioAnalyses'));
const AudioUpload = lazy(() => import('./pages/AudioUpload'));
const AudioAnalysisDetail = lazy(() => import('./pages/AudioAnalysisDetail'));

import { Toaster } from 'sonner';

// Create a root route
const rootRoute = createRootRoute({
    component: () => (
        <>
            <AuthRedirectHandler />
            <Outlet />
            <Toaster position="top-center" richColors />
            {import.meta.env.DEV && <TanStackRouterDevtools />}
        </>
    ),
    notFoundComponent: () => (
        <div className="flex items-center justify-center min-h-screen">
            <div className="text-center">
                <h1 className="text-6xl font-bold text-gray-800">404</h1>
                <p className="text-xl text-gray-600 mt-4">Página no encontrada</p>
                <a
                    href="/"
                    className="mt-6 inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                    Volver al inicio
                </a>
            </div>
        </div>
    ),
});

// Suspense wrapper helper
const SuspenseWrapper = ({ children }: { children: React.ReactNode }) => (
    <Suspense
        fallback={
            <div className="flex items-center justify-center min-h-[50vh]">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
        }
    >
        {children}
    </Suspense>
);

// Auth Layout Route
const authLayoutRoute = createRoute({
    getParentRoute: () => rootRoute,
    id: 'auth',
    component: AuthLayout,
});

// Define valid search params for login
const loginSearchSchema = (search: Record<string, unknown>) => ({
    redirect: (search.redirect as string) || undefined,
});

// Define Auth routes
const loginRoute = createRoute({
    getParentRoute: () => authLayoutRoute,
    path: 'login',
    component: () => (
        <SuspenseWrapper>
            <Login />
        </SuspenseWrapper>
    ),
    validateSearch: loginSearchSchema,
});

const registerRoute = createRoute({
    getParentRoute: () => authLayoutRoute,
    path: 'register',
    component: () => (
        <SuspenseWrapper>
            <Register />
        </SuspenseWrapper>
    ),
});

// Dashboard Layout Route
const dashboardLayoutRoute = createRoute({
    getParentRoute: () => rootRoute,
    id: 'app',
    component: DashboardLayout,
    notFoundComponent: () => (
        <div className="flex items-center justify-center min-h-screen">
            <div className="text-center">
                <h1 className="text-6xl font-bold text-gray-800">404</h1>
                <p className="text-xl text-gray-600 mt-4">Página no encontrada</p>
                <a
                    href="/dashboard"
                    className="mt-6 inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                    Volver al Dashboard
                </a>
            </div>
        </div>
    ),
    beforeLoad: async ({ location }) => {
        if (!authService.isAuthenticated()) {
            // localStorage is empty — could be a fresh SSO session (e.g. Microsoft OAuth).
            // Verify with backend before rejecting the navigation.
            const sessionUser = await authService.verifySession();
            if (!sessionUser) {
                throw redirect({
                    to: '/login',
                    search: {
                        redirect: location.href,
                    },
                });
            }
        }
    },
});

// Define Dashboard routes
const dashboardRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'dashboard',
    component: () => (
        <SuspenseWrapper>
            <Dashboard />
        </SuspenseWrapper>
    ),
});

const myVideosRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'mis-videos',
    component: () => (
        <SuspenseWrapper>
            <MyVideos />
        </SuspenseWrapper>
    ),
});

const workspacesRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'proyectos',
    component: () => (
        <SuspenseWrapper>
            <Workspaces />
        </SuspenseWrapper>
    ),
});

const workspaceDetailRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'proyecto/$id',
    component: () => (
        <SuspenseWrapper>
            <WorkspaceDetail />
        </SuspenseWrapper>
    ),
});

const uploadRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'upload',
    component: () => (
        <SuspenseWrapper>
            <Upload />
        </SuspenseWrapper>
    ),
});

const profileRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'perfil',
    component: () => (
        <SuspenseWrapper>
            <Profile />
        </SuspenseWrapper>
    ),
});

const processingRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'processing/$videoId',
    component: () => (
        <SuspenseWrapper>
            <VideoProcessing />
        </SuspenseWrapper>
    ),
});

const detailsRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'video/$videoId',
    component: () => (
        <SuspenseWrapper>
            <VideoDetailsPage />
        </SuspenseWrapper>
    ),
});

// Security Analysis Routes
const securityRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'security',
    component: () => (
        <SuspenseWrapper>
            <SecurityVideos />
        </SuspenseWrapper>
    ),
});

const securityUploadRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'security/upload',
    component: () => (
        <SuspenseWrapper>
            <SecurityUpload />
        </SuspenseWrapper>
    ),
});

const securityVideoDetailRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'security/$videoId',
    component: () => (
        <SuspenseWrapper>
            <SecurityVideoDetail />
        </SuspenseWrapper>
    ),
});

const securityAnalysisRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'security/analysis',
    component: () => (
        <SuspenseWrapper>
            <SecurityAnalysis />
        </SuspenseWrapper>
    ),
});

// Operational Analysis Routes
const operationalRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'operational',
    component: () => (
        <SuspenseWrapper>
            <OperationalVideos />
        </SuspenseWrapper>
    ),
});

const operationalUploadRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'operational/upload',
    component: () => (
        <SuspenseWrapper>
            <OperationalUpload />
        </SuspenseWrapper>
    ),
    validateSearch: (search: Record<string, unknown>) => ({
        analysisType: (search.analysisType as string) || undefined,
    }),
});

const operationalDetailRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'operational/$analysisId',
    component: () => (
        <SuspenseWrapper>
            <OperationalVideoDetail />
        </SuspenseWrapper>
    ),
});

// Audio Analysis Routes
const audioRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'audio',
    component: () => (
        <SuspenseWrapper>
            <AudioAnalyses />
        </SuspenseWrapper>
    ),
});

const audioUploadRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'audio/upload',
    component: () => (
        <SuspenseWrapper>
            <AudioUpload />
        </SuspenseWrapper>
    ),
});

const audioDetailRoute = createRoute({
    getParentRoute: () => dashboardLayoutRoute,
    path: 'audio/$analysisId',
    component: () => (
        <SuspenseWrapper>
            <AudioAnalysisDetail />
        </SuspenseWrapper>
    ),
});

const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => <div className="p-4">Redirecting...</div>,
    beforeLoad: () => {
        if (authService.isAuthenticated()) {
            throw redirect({ to: '/dashboard' });
        } else {
            throw redirect({
                to: '/login',
                search: { redirect: undefined },
            });
        }
    },
});

// Create the route tree
const routeTree = rootRoute.addChildren([
    indexRoute,
    authLayoutRoute.addChildren([loginRoute, registerRoute]),
    dashboardLayoutRoute.addChildren([
        dashboardRoute,
        myVideosRoute,
        workspacesRoute,
        workspaceDetailRoute,
        uploadRoute,
        profileRoute,
        processingRoute,
        detailsRoute,
        securityRoute,
        securityUploadRoute,
        securityVideoDetailRoute,
        securityAnalysisRoute,
        operationalRoute,
        operationalUploadRoute,
        operationalDetailRoute,
        audioRoute,
        audioUploadRoute,
        audioDetailRoute,
    ]),
]);

// Create the router
export const router = createRouter({ routeTree });

// Register the router for type safety
declare module '@tanstack/react-router' {
    interface Register {
        router: typeof router;
    }
}
