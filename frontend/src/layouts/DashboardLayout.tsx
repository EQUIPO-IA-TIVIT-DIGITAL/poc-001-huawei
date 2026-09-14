import { Link, Outlet, useLocation, useNavigate } from '@tanstack/react-router';
import {
  Activity,
  FolderKanban,
  Headphones,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  User,
  Video,
  X,
  type LucideIcon,
} from 'lucide-react';
import { Suspense, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Button } from '../components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '../components/ui/avatar';
import { Separator } from '../components/ui/separator';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import { Spinner } from '../components/ui/spinner';
import { authService } from '../services/auth';
import { useAuth } from '../context/AuthContext';
import { useTranslation } from '../i18n';
import type { TranslationKey } from '../i18n/es';
import { cn } from '../lib/utils';
import { startDashboardTour } from '../lib/driver';
import { toast } from 'sonner';

interface NavItemConfig {
  to: string;
  icon: LucideIcon;
  labelKey: TranslationKey;
}

const NAV_ITEMS: NavItemConfig[] = [
  { to: '/dashboard', icon: LayoutDashboard, labelKey: 'nav.dashboard' },
  { to: '/proyectos', icon: FolderKanban, labelKey: 'nav.projects' },
  { to: '/mis-videos', icon: Video, labelKey: 'nav.myVideos' },
  { to: '/operational', icon: Activity, labelKey: 'nav.operational' },
  { to: '/audio', icon: Headphones, labelKey: 'nav.audio' },
];

export function DashboardLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { t } = useTranslation();
  const [isSidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [isMobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.body.style.overflow = isMobileOpen ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [isMobileOpen]);

  const handleLogout = () => {
    authService.logout();
    navigate({ to: '/login', search: { redirect: undefined } });
  };

  const handleHelp = () => {
    if (location.pathname === '/dashboard') {
      startDashboardTour();
    } else {
      toast.info(t('common.help'), {
        description: t('common.help'),
        duration: 4000,
      });
    }
  };

  const isActive = (to: string) =>
    location.pathname === to || location.pathname.startsWith(to + '/');

  return (
    <div className="min-h-screen bg-background font-sans text-foreground">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground"
      >
        {t('common.skipToContent')}
      </a>

      {isMobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-gray-900/50 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        id="app-sidebar"
        aria-label={t('nav.sectionLabel')}
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-[260px] flex-col border-r border-border bg-card transition-transform duration-300 ease-in-out lg:translate-x-0 lg:transition-[width]',
          isMobileOpen ? 'translate-x-0' : '-translate-x-full',
          isSidebarCollapsed ? 'lg:w-[76px]' : 'lg:w-[260px]',
        )}
      >
        <div className="flex h-16 items-center justify-between gap-2 border-b border-border px-3">
          <Link
            to="/dashboard"
            className={cn(
              'flex min-w-0 items-center gap-3 rounded-lg p-1 transition-colors hover:bg-muted',
              isSidebarCollapsed && 'lg:justify-center',
            )}
          >
            <img
              src="/icon_tivit.svg"
              alt=""
              className="h-9 w-9 shrink-0 rounded-lg object-cover"
            />
            <span className={cn('min-w-0', isSidebarCollapsed && 'lg:hidden')}>
              <span className="block truncate text-sm font-bold leading-none text-foreground">
                {t('common.appName')}
              </span>
              <span className="mt-1 block truncate text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                {t('common.appTagline')}
              </span>
            </span>
          </Link>

          <Button
            variant="ghost"
            size="icon-sm"
            className="lg:hidden"
            onClick={() => setMobileOpen(false)}
            aria-label={t('common.closeMenu')}
          >
            <X aria-hidden="true" />
          </Button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          {NAV_ITEMS.map(({ to, icon: Icon, labelKey }) => {
            const active = isActive(to);
            return (
              <Link
                key={to}
                to={to}
                aria-label={t(labelKey)}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  isSidebarCollapsed && 'lg:justify-center lg:px-2',
                  active
                    ? 'bg-brand-soft text-brand-hover'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                )}
              >
                {active && (
                  <span className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-primary" />
                )}
                <Icon size={19} className="shrink-0" aria-hidden="true" />
                <span className={cn('truncate', isSidebarCollapsed && 'lg:hidden')}>
                  {t(labelKey)}
                </span>
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-border p-3">
          <Button
            variant="ghost"
            size="sm"
            fullWidth
            onClick={handleLogout}
            aria-label={t('common.logout')}
            className={cn(
              'justify-start text-muted-foreground',
              isSidebarCollapsed && 'lg:justify-center lg:px-2',
            )}
          >
            <LogOut aria-hidden="true" />
            <span className={cn('truncate', isSidebarCollapsed && 'lg:hidden')}>
              {t('common.logout')}
            </span>
          </Button>
        </div>
      </aside>

      <div
        className={cn(
          'flex min-h-screen flex-col transition-[padding] duration-300 ease-in-out',
          isSidebarCollapsed ? 'lg:pl-[76px]' : 'lg:pl-[260px]',
        )}
      >
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-card/85 px-4 backdrop-blur lg:px-6">
          <Button
            variant="ghost"
            size="icon-sm"
            className="lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label={t('common.openMenu')}
            aria-expanded={isMobileOpen}
            aria-controls="app-sidebar"
          >
            <Menu aria-hidden="true" />
          </Button>

          <Button
            variant="ghost"
            size="icon-sm"
            className="hidden lg:inline-flex"
            onClick={() => setSidebarCollapsed((value) => !value)}
            aria-label={t('common.toggleSidebar')}
            aria-expanded={!isSidebarCollapsed}
            aria-controls="app-sidebar"
          >
            {isSidebarCollapsed ? (
              <PanelLeftOpen aria-hidden="true" />
            ) : (
              <PanelLeftClose aria-hidden="true" />
            )}
          </Button>

          <div className="flex-1" />

          <Button
            variant="outline"
            size="sm"
            onClick={handleHelp}
            className="hidden sm:inline-flex"
          >
            <HelpCircle aria-hidden="true" />
            {t('common.help')}
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex items-center gap-3 rounded-lg p-1.5 transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                aria-label={t('common.openMenu')}
              >
                <span className="hidden text-right sm:block">
                  <span className="block text-sm font-semibold leading-none text-foreground">
                    {user?.nombre_completo || t('common.user')}
                  </span>
                  <span className="mt-1 block text-xs capitalize text-muted-foreground">
                    {user?.rol || '—'}
                  </span>
                </span>
                <Avatar>
                  {user?.foto_url ? (
                    <AvatarImage src={user.foto_url} alt={t('common.avatar')} />
                  ) : null}
                  <AvatarFallback>{user?.nombre?.charAt(0) || 'U'}</AvatarFallback>
                </Avatar>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel>
                <span className="block truncate text-sm font-semibold text-foreground">
                  {user?.nombre_completo || t('common.user')}
                </span>
                <span className="mt-0.5 block truncate text-xs font-normal capitalize text-muted-foreground">
                  {user?.rol || '—'}
                </span>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link to="/perfil">
                  <User aria-hidden="true" />
                  {t('common.profile')}
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem destructive onSelect={handleLogout}>
                <LogOut aria-hidden="true" />
                {t('common.logout')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        <main id="main-content" className="flex-1 p-4 sm:p-6 lg:p-8">
          <Suspense
            fallback={
              <div className="flex h-[calc(100vh-128px)] w-full items-center justify-center">
                <Spinner size="xl" className="text-primary" />
              </div>
            }
          >
            <AnimatePresence mode="wait">
              <motion.div
                key={location.pathname}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2, ease: 'easeInOut' }}
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          </Suspense>
        </main>
      </div>
    </div>
  );
}
