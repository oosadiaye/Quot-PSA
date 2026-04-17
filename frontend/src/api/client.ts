import axios from 'axios';
import logger from '../utils/logger';

const API_BASE_URL = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1`;

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor — inject auth token & tenant header
apiClient.interceptors.request.use((config) => {
  // Skip auth headers for login/register endpoints to prevent stale tokens
  // from interfering with authentication
  const isAuthEndpoint = config.url?.includes('/auth/login') || config.url?.includes('/auth/register');

  if (!isAuthEndpoint) {
    const token = localStorage.getItem('authToken') ?? sessionStorage.getItem('authToken');
    if (token) {
      config.headers['Authorization'] = `Token ${token}`;
    }

    const tenantDomain = localStorage.getItem('tenantDomain') ?? sessionStorage.getItem('tenantDomain');
    if (tenantDomain && tenantDomain !== 'null' && tenantDomain !== 'undefined') {
      config.headers['X-Tenant-Domain'] = tenantDomain;
    }

    // Inject active organization header for MDA-scoped requests
    const orgRaw = localStorage.getItem('activeOrganization') ?? sessionStorage.getItem('activeOrganization');
    if (orgRaw) {
      try {
        const org = JSON.parse(orgRaw);
        if (org?.id) {
          config.headers['X-Organization-Id'] = String(org.id);
        }
      } catch { /* ignore parse errors */ }
    }
  }

  return config;
}, (error) => {
  return Promise.reject(error);
});

// Response interceptor for handling auth errors
apiClient.interceptors.response.use(
  (response) => {
    if (typeof response.data === 'string') {
      try {
        response.data = JSON.parse(response.data);
      } catch {
        // Not JSON, leave as-is
      }
    }
    return response;
  },
  (error) => {
    if (!error.response) {
      logger.error('Network error: Unable to reach server');
      return Promise.reject(new Error('Network error: Unable to reach the server. Please check your connection.'));
    }

    const { status } = error.response;

    if (status === 401) {
      // Check if we're in an impersonation session before clearing auth
      const impersonation = sessionStorage.getItem('impersonation_session');
      if (impersonation) {
        // During impersonation, redirect back to superadmin instead of login
        sessionStorage.removeItem('impersonation_session');
        localStorage.removeItem('impersonation');
        window.location.href = '/superadmin';
      } else {
        // Clear stale auth data from both storages and notify ProtectedRoute to redirect
        const keys = ['authToken', 'user', 'tenantDomain', 'tenantInfo', 'tenantPermissions'];
        for (const key of keys) {
          localStorage.removeItem(key);
          sessionStorage.removeItem(key);
        }
        // Dispatch event so ProtectedRoute can react without hard redirect
        window.dispatchEvent(new Event('auth-expired'));
      }
    } else if (status === 403) {
      // Permission denied — don't redirect, let the component handle it
    } else if (status >= 500) {
      logger.error('Server error:', error.response.data || 'Internal server error');
    }

    return Promise.reject(error);
  }
);

export default apiClient;
