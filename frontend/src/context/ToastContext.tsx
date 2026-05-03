import { createContext, useContext, useState, useCallback, ReactNode } from 'react';

type ToastType = 'success' | 'error' | 'warning' | 'info';

interface Toast {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
}

interface ToastContextType {
  toasts: Toast[];
  addToast: (message: string, type?: ToastType, duration?: number) => void;
  removeToast: (id: string) => void;
  clearToasts: () => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

/**
 * Type-aware default durations (ms). Calibrated for posting errors
 * which often carry multi-line remediation hints ("Configure a
 * Liability account with reconciliation_type='accounts_payable'…",
 * "Warrant ceiling exceeded for 010000000000/22020309/02101…"). The
 * operator needs time to read, screenshot for support, or walk
 * across the room to consult a colleague before the toast vanishes.
 *
 * These defaults apply to every tenant served by this build —
 * present and future — because the ToastContext is mounted once at
 * app root and consumed by every page. No per-tenant override path
 * exists or is needed; bumping these values cascades everywhere.
 *
 * Toasts are always dismissable: click the toast or its × button.
 * Callers can override by passing an explicit `duration`, and
 * `duration=0` makes a toast fully sticky until manually closed.
 */
const DEFAULT_DURATIONS: Record<ToastType, number> = {
  error:   30000, // 30s — multi-line error + remediation hint, time to screenshot/share
  warning: 15000, // 15s — advisory, still actionable
  success:  5000, // 5s  — confirms an action the user just took
  info:    10000, // 10s — neutral notice, longer to ensure it's read
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, type: ToastType = 'info', duration?: number) => {
    // When `duration` is omitted, pick the type-aware default so errors
    // get the attention they need. `duration=0` (sticky) still wins.
    const effective = duration === undefined ? DEFAULT_DURATIONS[type] : duration;
    const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setToasts((prev) => [...prev, { id, type, message, duration: effective }]);

    if (effective > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, effective);
    }
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const clearToasts = useCallback(() => {
    setToasts([]);
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast, clearToasts }}>
      {children}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}