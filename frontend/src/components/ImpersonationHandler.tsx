import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

/**
 * Reads impersonation data from sessionStorage (set by the superadmin "Login As" action),
 * stores impersonation session info, swaps the auth token, and redirects to /dashboard.
 *
 * The superadmin opens a new tab with `/?impersonation=pending` and stores the
 * impersonation payload in sessionStorage under `pending_impersonation`.
 */
const ImpersonationHandler = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const isPending = searchParams.get('impersonation') === 'pending';
    if (!isPending) return;

    const raw = sessionStorage.getItem('pending_impersonation');
    if (!raw) return;

    let impersonationData: {
      token: string;
      tenant_domain: string;
      tenant_name?: string;
      user: string;
      user_id?: number;
      user_email?: string;
      user_first_name?: string;
      user_last_name?: string;
      session_id: number;
    };

    try {
      impersonationData = JSON.parse(raw);
    } catch {
      return;
    }

    const {
      token, tenant_domain, tenant_name,
      user: targetUser, user_id, user_email, user_first_name, user_last_name,
      session_id,
    } = impersonationData;
    if (!token || !tenant_domain || !targetUser) return;

    // Resolve a human-readable name: prefer backend-supplied name, fall back to domain
    const displayName = tenant_name || tenant_domain;

    // Clean up the pending data immediately
    sessionStorage.removeItem('pending_impersonation');

    // Store only session_id and tenant_domain in sessionStorage (tab-scoped, not accessible from other tabs).
    // We intentionally do NOT store the original superadmin token — the superadmin
    // should re-authenticate after ending impersonation for security.
    sessionStorage.setItem('impersonation_session', JSON.stringify({
      sessionId: session_id ? Number(session_id) : 0,
      tenantDomain: tenant_domain,
      tenantName: displayName,
      targetUser,
    }));

    // Also keep a flag in localStorage for components that check impersonation state
    localStorage.setItem('impersonation', JSON.stringify({
      sessionId: session_id ? Number(session_id) : 0,
      targetUser,
      targetTenant: tenant_domain,
      targetTenantName: displayName,
    }));

    // Swap to the impersonation token + tenant context
    localStorage.setItem('authToken', token);
    localStorage.setItem('tenantDomain', tenant_domain);
    // Replace the stored user record with the impersonated user's profile so
    // that the "Welcome back, <name>" greeting and other user-facing UI reflects
    // the impersonated account, not the superadmin who initiated the session.
    localStorage.setItem('user', JSON.stringify({
      id: user_id ?? 0,
      username: targetUser,
      email: user_email ?? '',
      first_name: user_first_name ?? '',
      last_name: user_last_name ?? '',
      name: user_first_name
        ? `${user_first_name} ${user_last_name ?? ''}`.trim()
        : targetUser,
    }));
    // activeTenant is used by Dashboard to display the Organization name
    localStorage.setItem('activeTenant', displayName);
    localStorage.setItem('tenantInfo', JSON.stringify({
      id: 0,
      name: displayName,
      domain: tenant_domain,
      role: 'admin',
    }));

    // Navigate to dashboard (clear impersonation params from URL)
    navigate('/dashboard', { replace: true });
    window.location.reload();
  }, [searchParams, navigate]);

  return null;
};

export default ImpersonationHandler;
