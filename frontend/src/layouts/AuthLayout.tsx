import { Outlet, useLocation } from '@tanstack/react-router';
import { AnimatePresence, motion } from 'framer-motion';
import { Suspense } from 'react';

export function AuthLayout() {
    const location = useLocation();
    const isRegister = location.pathname.includes('register');

    return (
        <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-linear-to-br from-black via-black-soft to-black p-6">
            {/* Background Effects */}
            <div className="absolute -top-[20%] -left-[10%] h-[500px] w-[500px] rounded-full bg-[radial-gradient(circle,rgba(227,6,19,0.15)_0%,transparent_70%)] blur-[60px] animate-pulse-slow" />
            <div className="absolute -bottom-[20%] -right-[10%] h-[600px] w-[600px] rounded-full bg-[radial-gradient(circle,rgba(227,6,19,0.12)_0%,transparent_70%)] blur-[80px] animate-pulse-slow [animation-delay:4s]" />

            {/* Content */}
            <div className={`relative z-10 w-full transition-all duration-300 ${isRegister ? 'max-w-md md:max-w-2xl' : 'max-w-[420px]'}`}>
                <div className="overflow-hidden rounded-3xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-2xl">
                    {/* Top Line Gradient */}
                    <div className="absolute top-0 left-1/2 h-[2px] w-[60%] -translate-x-1/2 bg-linear-to-r from-transparent via-tivit-red to-transparent" />

                    {/* Content Area with Transition */}
                    <div className="min-h-[300px]">
                        <Suspense fallback={
                            <div className="flex h-[300px] w-full items-center justify-center">
                                <span className="loader"></span>
                            </div>
                        }>
                            <AnimatePresence mode="wait">
                                <motion.div
                                    key={location.pathname}
                                    initial={{ opacity: 0, x: 20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    exit={{ opacity: 0, x: -20 }}
                                    transition={{ duration: 0.3, ease: "easeOut" }}
                                >
                                    <Outlet />
                                </motion.div>
                            </AnimatePresence>
                        </Suspense>
                    </div>

                    {/* Footer */}
                    <div className="border-t border-white/10 bg-black/30 p-4 text-center text-sm text-white/50">
                        &copy; {new Date().getFullYear()} TIVIT CU002. Todos los derechos reservados.
                    </div>
                </div>
            </div>
        </div>
    );
}
