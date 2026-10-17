import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const post = vi.fn(() => Promise.resolve({ data: {} }));
vi.mock('../../api/client', () => ({
    default: { post: (...args: unknown[]) => post(...(args as [])), get: vi.fn(() => Promise.resolve({ data: {} })) },
}));

import { AuthProvider, useAuth } from '../AuthContext';

function SignOutButton() {
    const { logout } = useAuth();
    return <button onClick={logout}>sign out</button>;
}

describe('AuthContext.logout', () => {
    beforeEach(() => {
        post.mockClear();
        localStorage.clear();
        sessionStorage.clear();
        sessionStorage.setItem('authToken', 'tok-123');
        sessionStorage.setItem('user', JSON.stringify({ id: 1, username: 'ada', permissions: [] }));
        localStorage.setItem('tenantDomain', 'oag.example.test');
    });

    it('tells the server, authenticated, even though storage is cleared right after', () => {
        render(<AuthProvider><SignOutButton /></AuthProvider>);
        fireEvent.click(screen.getByText('sign out'));

        // The credentials must travel with the request itself: axios reads storage in an interceptor,
        // asynchronously, by which time sign-out has already emptied it — the logout would go out
        // anonymous and revoke nothing.
        expect(post).toHaveBeenCalledTimes(1);
        const [url, , config] = post.mock.calls[0] as unknown as [string, unknown, { headers: Record<string, string> }];
        expect(url).toBe('/core/auth/logout/');
        expect(config.headers.Authorization).toBe('Token tok-123');
        expect(config.headers['X-Tenant-Domain']).toBe('oag.example.test');
    });

    it('clears the token from BOTH storages', () => {
        localStorage.setItem('authToken', 'tok-123');
        render(<AuthProvider><SignOutButton /></AuthProvider>);
        fireEvent.click(screen.getByText('sign out'));

        expect(sessionStorage.getItem('authToken')).toBeNull();
        expect(localStorage.getItem('authToken')).toBeNull();
        expect(sessionStorage.getItem('user')).toBeNull();
    });

    it('still signs out locally when the server cannot be reached', () => {
        post.mockImplementationOnce(() => Promise.reject(new Error('Network error')));
        render(<AuthProvider><SignOutButton /></AuthProvider>);
        fireEvent.click(screen.getByText('sign out'));

        expect(sessionStorage.getItem('authToken')).toBeNull();
    });
});
