import { Navigate, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import LoadingScreen from '../components/common/LoadingScreen';
import logger from '../utils/logger';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredPerm?: string;
  requiredRole?: string;
}

const ProtectedRoute = ({ children, requiredPerm, requiredRole }: ProtectedRouteProps) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const location = useLocation();
  const { hasPermission, hasRole } = useAuth();

  const checkAuth = () => {
    try {
      // Check both storages — sessionStorage for non-remembered sessions
      const token = localStorage.getItem('authToken') ?? sessionStorage.getItem('authToken');
      const userRaw = localStorage.getItem('user') ?? sessionStorage.getItem('user');
      if (userRaw) {
        JSON.parse(userRaw);
      }
      setIsAuthenticated(!!token);
    } catch (err) {
      logger.error('Auth check error:', err);
      const keys = ['authToken', 'user', 'tenantDomain', 'tenantInfo', 'tenantPermissions'];
      for (const key of keys) {
        localStorage.removeItem(key);
        sessionStorage.removeItem(key);
      }
      setIsAuthenticated(false);
    }
  };

  // Check auth on mount and route change
  useEffect(() => {
    checkAuth();
  }, [location.pathname]);

  // Listen for auth-expired events from the API interceptor
  useEffect(() => {
    const onAuthExpired = () => setIsAuthenticated(false);
    const onStorage = (e: StorageEvent) => {
      if (e.key === 'authToken' && !e.newValue) {
        setIsAuthenticated(false);
      }
    };
    window.addEventListener('auth-expired', onAuthExpired);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('auth-expired', onAuthExpired);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  if (isAuthenticated === null) {
    return <LoadingScreen message="Checking authentication..." />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (requiredPerm && !hasPermission(requiredPerm)) {
    return (
      <div className="flex items-center justify-center h-full min-h-[60vh]">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-700 dark:text-gray-300 mb-2">Access Denied</h2>
          <p className="text-gray-500 dark:text-gray-400">You do not have permission to access this page.</p>
        </div>
      </div>
    );
  }

  if (requiredRole && !hasRole(requiredRole)) {
    return (
      <div className="flex items-center justify-center h-full min-h-[60vh]">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-700 dark:text-gray-300 mb-2">Access Denied</h2>
          <p className="text-gray-500 dark:text-gray-400">Your role does not have access to this page.</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
};

export default ProtectedRoute;
