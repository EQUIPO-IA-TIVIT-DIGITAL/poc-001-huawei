import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { authService, User } from '../services/auth';

interface AuthContextType {
    user: User | null;
    isLoading: boolean;
    login: (credentials: { username: string; password?: string }) => Promise<User | null>;
    logout: () => void;
    verifySession: () => Promise<void>;
    updateUser: (updates: Partial<User>) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    const verifySession = useCallback(async () => {
        const validatedUser = await authService.verifySession();
        // undefined means network error / unknown -> Mantain current state (safe)
        // null means explicit logout -> Clear state
        // User object means success -> Update state
        if (validatedUser !== undefined) {
            setUser(validatedUser);
        }
    }, []);

    useEffect(() => {
        // Initialize user from storage first (fast UI path for normal logins)
        const storedUser = authService.getUser();
        if (storedUser) {
            setUser(storedUser);
        }
        // Always verify with the backend on mount.
        verifySession().finally(() => setIsLoading(false));
    }, [verifySession]);

    const login = useCallback(async (credentials: { username: string; password?: string }): Promise<User | null> => {
        const result = await authService.login(credentials);
        if (result) {
            setUser(result);
        }
        return result;
    }, []);

    const logout = useCallback(() => {
        authService.logout(); // Clears localStorage and might call API
        setUser(null);
    }, []);

    const updateUser = useCallback((updates: Partial<User>) => {
        authService.updateLocalUser(updates);
        setUser((currentUser) => (currentUser ? { ...currentUser, ...updates } : currentUser));
    }, []);

    return (
        <AuthContext.Provider value={{ user, isLoading, login, logout, verifySession, updateUser }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
