import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredPerm?: string;
  requiredRole?: string;
}

/**
 * ProtectedRoute — gates child routes on AuthContext state.
 *
 * Reads ``isAuthenticated`` from context (derived from React state, not
 * synchronous storage reads) so a 401-driven logout flushes consumers
 * within the same render cycle. The previous implementation duplicated
 * storage probing here and produced a one-render desync where storage
 * had just been cleared but state hadn't yet flushed.
 */
const ProtectedRoute = ({ children, requiredPerm, requiredRole }: ProtectedRouteProps) => {
  const location = useLocation();
  const { isAuthenticated, hasPermission, hasRole } = useAuth();

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
