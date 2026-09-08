import { Link, Outlet, useLocation, useNavigate } from '@tanstack/react-router';
import {
    Video,
    Home,
    Upload,
    LogOut,
    Menu,
    Film,
    User,
    Brain,
    CloudUpload,
    PlaySquare,
    UserCog,
    Settings,
    FolderOpen,
    Grid3x3,
    FolderKanban,
    VideoIcon,
    Layers,
    Shield,
    Search,
    Activity,
    Headphones,
} from 'lucide-react';
import { useState, useRef, useEffect, Suspense } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Button } from '../components/ui/button';
import { authService } from '../services/auth';
import { useAuth } from '../context/AuthContext';
import { cn } from '../lib/utils';
import { startDashboardTour } from '../lib/driver';
import { HelpCircle } from 'lucide-react';
import { toast } from 'sonner';

export function DashboardLayout() {
    const location = useLocation();
    const navigate = useNavigate();
    const [isSidebarOpen, setSidebarOpen] = useState(true);
    const [isUserMenuOpen, setUserMenuOpen] = useState(false);
    const { user } = useAuth(); // Reactivo: se actualiza cuando verifySession() retorna foto_url firmada
    const menuRef = useRef<HTMLDivElement>(null);

    const handleLogout = () => {
        authService.logout();
        navigate({ to: '/login', search: { redirect: undefined } });
    };

    // Close user menu when clicking outside
    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setUserMenuOpen(false);
            }
        }
        document.addEventListener('mousedown', handleClickOutside);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, []);

    interface NavItemProps {
        to: string;
        icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
        label: string;
    }

    const NavItem = ({ to, icon: Icon, label }: NavItemProps) => {
        const isActive = location.pathname === to || location.pathname.startsWith(to + '/');
        return (
            <Link
                to={to}
                className={cn(
                    'flex items-center gap-3 py-2.5 rounded-lg transition-all duration-200 font-medium text-[13.5px] group relative overflow-hidden',
                    isSidebarOpen ? 'px-3' : 'justify-center px-2',
                    isActive
                        ? 'bg-white/10 text-white border-l-2 border-tivit-red pl-[10px]'
                        : 'text-gray-400 hover:bg-white/5 hover:text-gray-200 border-l-2 border-transparent',
                )}
                title={!isSidebarOpen ? label : undefined}
            >
                <Icon
                    size={19}
                    className={cn(
                        'shrink-0 transition-transform duration-200',
                        isActive ? 'text-tivit-red' : 'group-hover:text-gray-200',
                    )}
                    strokeWidth={2}
                />
                <span
                    className={cn(
                        'whitespace-nowrap transition-opacity duration-200',
                        !isSidebarOpen && 'opacity-0 w-0 hidden',
                    )}
                >
                    {label}
                </span>
            </Link>
        );
    };

    const getPageTitle = () => {
        if (location.pathname.includes('/admin/dashboard')) return 'Admin Dashboard';
        if (location.pathname.includes('/admin/socios')) return 'Gestión de Socios';
        if (location.pathname.includes('/admin/videos')) return 'Gestión Videos';
        if (location.pathname.includes('/admin/metricas')) return 'Métricas de IA';
        if (location.pathname.includes('/admin/cola')) return 'Operabilidad Cola';
        if (location.pathname.includes('/proyectos')) return 'Proyectos';
        if (location.pathname.includes('/proyecto/')) return 'Detalle Proyecto';
        if (location.pathname.includes('/audio/upload')) return 'Nuevo Análisis';
        if (location.pathname.includes('/audio/')) return 'Detalle Análisis de Audio';
        if (location.pathname === '/audio') return 'Análisis de Audio';
        if (location.pathname.includes('/upload')) return 'Subir Video';
        if (location.pathname.includes('/mis-videos')) return 'Mis Videos';
        if (location.pathname.includes('/perfil')) return 'Mi Perfil';
        if (location.pathname === '/dashboard') return 'Dashboard';
        return 'Principal';
    };

    const pageTitle = getPageTitle();

    return (
        <div className="flex min-h-screen bg-white font-sans text-black">
            {/* Sidebar */}
            <aside
                className={cn(
                    'fixed top-0 left-0 z-50 h-full flex flex-col bg-[#0f0f0f] text-white transition-all duration-300 ease-in-out border-r border-white/5',
                    isSidebarOpen
                        ? 'w-[260px] translate-x-0'
                        : 'w-[70px] translate-x-0 hidden lg:flex',
                )}
            >
                {/* Logo Area */}
                <Link
                    to="/dashboard"
                    className="flex items-center gap-3 p-4 h-16 overflow-hidden hover:bg-white/5 transition-all duration-300 group"
                >
                    <div className="relative">
                        <img
                            src="/icon_tivit.svg"
                            alt="TIVIT CU002"
                            className="h-9 w-auto shrink-0 object-cover rounded-lg shadow-lg transition-transform duration-300 group-hover:scale-110"
                        />
                        <div className="absolute inset-0 bg-gradient-to-br from-tivit-red/20 to-transparent rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                    </div>
                    <div
                        className={cn(
                            'transition-opacity duration-200 overflow-hidden whitespace-nowrap',
                            !isSidebarOpen && 'opacity-0 w-0 hidden',
                        )}
                    >
                        <h1 className="text-lg font-bold leading-none text-white tracking-tight">
                            TIVIT CU002
                        </h1>
                        <p className="text-[10px] text-gray-400 uppercase tracking-widest mt-1 font-semibold">
                            PLATAFORMA IA
                        </p>
                    </div>
                </Link>

                {/* Nav */}
                <nav className="flex-1 space-y-1 px-2 py-4 overflow-hidden mt-2">
                    <>
                        <NavItem to="/dashboard" icon={Grid3x3} label="Dashboard" />
                        <NavItem to="/proyectos" icon={FolderKanban} label="Proyectos" />
                        {/* <NavItem to="/upload" icon={CloudUpload} label="Subir Video" /> */}
                        <NavItem to="/mis-videos" icon={VideoIcon} label="Mis Videos" />
                        {/* <NavItem to="/security" icon={Shield} label="Análisis Seguridad" /> */}
                        <NavItem to="/operational" icon={Activity} label="Análisis Operativo" />
                        <NavItem to="/audio" icon={Headphones} label="Análisis de Audio" />
                    </>
                </nav>

                <div className="p-4 border-t border-white/5 relative mt-6">
                    <Button
                        variant="ghost"
                        size="sm"
                        fullWidth
                        onClick={handleLogout}
                        className={cn(
                            'justify-start text-gray-400 hover:text-white hover:bg-white/5',
                            !isSidebarOpen && 'justify-center px-2',
                        )}
                        title={!isSidebarOpen ? 'Cerrar Sesión' : undefined}
                    >
                        <LogOut
                            size={18}
                            className={cn('shrink-0', isSidebarOpen && 'mr-3')}
                            fill="currentColor"
                        />
                        {isSidebarOpen && <span>Cerrar Sesión</span>}
                    </Button>
                </div>
            </aside>

            {/* Main Content */}
            <main
                className={cn(
                    'flex-1 flex flex-col min-h-screen transition-all duration-300',
                    isSidebarOpen ? 'lg:ml-[260px]' : 'lg:ml-[70px]',
                )}
            >
                {/* Header */}
                <header className="sticky top-0 z-40 bg-white border-b border-gray-100 px-6 h-16 flex items-center justify-between shadow-xs">
                    <div className="flex items-center gap-4">
                        <Button
                            variant="ghost"
                            size="icon"
                            className="text-gray-500"
                            onClick={() => setSidebarOpen(!isSidebarOpen)}
                        >
                            <Menu size={20} />
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            className="hidden md:flex gap-2 items-center text-gray-700 border-gray-300 hover:bg-gray-50 hover:border-gray-400 hover:text-gray-900 transition-all duration-200 shadow-sm hover:shadow group"
                            onClick={() => {
                                if (location.pathname === '/dashboard') {
                                    startDashboardTour();
                                } else {
                                    // Show context-aware help
                                    const title = getPageTitle();
                                    const helpMap: Record<string, string> = {
                                        'Admin Dashboard':
                                            'Vista general de métricas y estado del sistema.',
                                        'Gestión Videos':
                                            'Administra todos los videos subidos a la plataforma.',
                                        'Gestión Socios': 'Gestiona usuarios y permisos de acceso.',
                                        'Métricas de IA':
                                            'Análisis detallado del rendimiento de los modelos de IA.',
                                        Proyectos:
                                            'Organiza tus videos en espacios de trabajo colaborativos.',
                                        'Detalle Proyecto':
                                            'Gestiona los videos y configuraciones de este proyecto.',
                                        'Subir Video': 'Sube nuevos videos para análisis.',
                                        'Mis Videos':
                                            'Tu biblioteca personal de videos procesados.',
                                        'Mi Perfil': 'Configura tu cuenta y preferencias personal.',
                                    };

                                        toast.info(title, {
                                            description:
                                                helpMap[title] ||
                                                'Información sobre la sección actual.',
                                            duration: 4000,
                                        });
                                }
                            }}
                        >
                            <HelpCircle
                                size={16}
                                className="transition-transform duration-200 group-hover:scale-110"
                                strokeWidth={2}
                            />
                            <span className="font-medium text-sm">Ayuda</span>
                        </Button>
                        <div className="hidden md:flex items-center gap-2 text-sm">
                            <span className="h-4 w-px bg-gray-300 mx-2"></span>
                            <span className="font-medium text-gray-500">Principal</span>
                            {pageTitle !== 'Principal' && (
                                <>
                                    <span className="text-gray-300">/</span>
                                    <span className="font-medium text-tivit-red">
                                        {pageTitle}
                                    </span>
                                </>
                            )}
                        </div>
                    </div>

                    <div className="flex items-center gap-4 relative" ref={menuRef}>
                        <div
                            className="flex items-center gap-3 cursor-pointer hover:bg-gray-50 p-2 rounded-lg transition-colors"
                            onClick={() => setUserMenuOpen(!isUserMenuOpen)}
                        >
                            <div className="text-right hidden sm:block">
                                <p className="text-sm font-bold text-gray-900 leading-none uppercase">
                                    {user?.nombre_completo || 'DEFAULT'}
                                </p>
                                <p className="text-xs text-gray-500 capitalize">
                                    {user?.rol || 'DEFAULT'}
                                </p>
                            </div>
                            <div className="h-10 w-10 rounded-lg bg-gray-100 border border-gray-200 overflow-hidden relative">
                                {user?.foto_url ? (
                                    <img
                                        src={user.foto_url}
                                        alt="Avatar"
                                        className="h-full w-full object-cover"
                                    />
                                ) : (
                                    <div className="h-full w-full flex items-center justify-center text-gray-400 font-bold bg-gray-50">
                                        {user?.nombre?.charAt(0) || 'U'}
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Dropdown Menu */}
                        {isUserMenuOpen && (
                            <div className="absolute top-16 right-0 w-56 bg-white rounded-xl shadow-xl border border-gray-100 py-2 animate-in fade-in zoom-in-95 duration-200 z-50">
                                <div className="px-4 py-3 border-b border-gray-100 sm:hidden">
                                    <p className="text-sm font-bold text-gray-900 leading-none uppercase">
                                        {user?.nombre || 'User'}
                                    </p>
                                    <p className="text-xs text-gray-500 mt-1 capitalize">
                                        {user?.rol || 'Socio'}
                                    </p>
                                </div>
                                <Link
                                    to="/perfil"
                                    className="flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 hover:text-tivit-red transition-colors"
                                    onClick={() => setUserMenuOpen(false)}
                                >
                                    <User size={16} fill="currentColor" />
                                    Editar Perfil
                                </Link>
                                <button
                                    onClick={handleLogout}
                                    className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 transition-colors text-left"
                                >
                                    <LogOut size={16} fill="currentColor" />
                                    Cerrar Sesión
                                </button>
                            </div>
                        )}
                    </div>
                </header>

                {/* Page Content */}
                <div className="flex-1 p-6 md:p-8 bg-[#f7f8fa] overflow-x-hidden">
                    <Suspense
                        fallback={
                            <div className="flex h-[calc(100vh-100px)] w-full items-center justify-center">
                                <span className="loader"></span>
                            </div>
                        }
                    >
                        <AnimatePresence mode="wait">
                            <motion.div
                                key={location.pathname}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -10 }}
                                transition={{ duration: 0.2, ease: 'easeInOut' }}
                                className="h-full"
                            >
                                <Outlet />
                            </motion.div>
                        </AnimatePresence>
                    </Suspense>
                </div>
            </main>

        </div>
    );
}
