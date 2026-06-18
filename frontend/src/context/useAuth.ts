/**
 * useAuth — consumer hook for AuthContext.
 *
 * Lives in its own file (split from AuthContext.tsx) so React fast-refresh
 * can hot-swap edits to the AuthProvider component without a full page
 * reload. Vite's fast-refresh plugin requires each file to export ONLY
 * components or ONLY non-components; mixing them forces a fall-back to
 * full reload, which destroys auth state during dev iteration.
 *
 * The re-export from AuthContext is preserved as a deprecation shim so
 * existing call sites (`import { useAuth } from '../context/AuthContext'`)
 * keep working until they migrate.
 */
import { useContext } from 'react';
import AuthContext, { type AuthState } from './AuthContext';

export const useAuth = (): AuthState => {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
    return ctx;
};
