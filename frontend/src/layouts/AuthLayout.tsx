import { Outlet, useLocation } from '@tanstack/react-router';
import { AnimatePresence, motion } from 'framer-motion';
import { Suspense } from 'react';
import { Spinner } from '../components/ui/spinner';
import { useTranslation } from '../i18n';

export function AuthLayout() {
  const location = useLocation();
  const { t } = useTranslation();
  const isRegister = location.pathname.includes('register');

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background p-4 sm:p-6">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,var(--color-brand-soft),transparent_55%)]" />
      <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-brand-soft blur-3xl" />

      <div
        className={`relative z-10 w-full transition-all duration-300 ${
          isRegister ? 'max-w-2xl' : 'max-w-[420px]'
        }`}
      >
        <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-popover">
          <div className="h-1 w-full bg-gradient-to-r from-brand via-brand-hover to-brand" />
          <div className="min-h-[300px] p-6 sm:p-8">
            <Suspense
              fallback={
                <div className="flex h-[300px] w-full items-center justify-center">
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
                  transition={{ duration: 0.25, ease: 'easeOut' }}
                >
                  <Outlet />
                </motion.div>
              </AnimatePresence>
            </Suspense>
          </div>
          <div className="border-t border-border bg-muted/50 px-6 py-3 text-center text-xs text-muted-foreground">
            &copy; {new Date().getFullYear()} {t('common.appName')}. {t('auth.legalFooter')}.
          </div>
        </div>
      </div>
    </div>
  );
}
