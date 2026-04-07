/**
 * Centralized logging utility for the ERP frontend.
 *
 * In production, error/warn messages can be routed to an external
 * monitoring service (Sentry, LogRocket, etc.) by extending the
 * `report()` helper below.  In development, messages are forwarded
 * to the native console for DevTools visibility.
 *
 * Usage:
 *   import logger from '@/utils/logger';
 *   logger.error('Failed to save invoice:', error);
 *   logger.warn('Retrying request...');
 *   logger.info('Invoice saved successfully');
 */

const isProd = import.meta.env.PROD;

/**
 * Extensibility hook: send structured errors to an external service.
 * Replace the body of this function when you integrate Sentry, etc.
 */
function report(level: 'error' | 'warn', message: string, ...args: unknown[]) {
  // Example Sentry integration (uncomment when ready):
  // if (level === 'error') Sentry.captureMessage(message, { extra: { args } });
  void level;
  void message;
  void args;
}

const logger = {
  error(message: string, ...args: unknown[]) {
    if (!isProd) {
      // eslint-disable-next-line no-console
      console.error(message, ...args);
    }
    report('error', message, ...args);
  },

  warn(message: string, ...args: unknown[]) {
    if (!isProd) {
      // eslint-disable-next-line no-console
      console.warn(message, ...args);
    }
    report('warn', message, ...args);
  },

  info(message: string, ...args: unknown[]) {
    if (!isProd) {
      // eslint-disable-next-line no-console
      console.info(message, ...args);
    }
  },

  debug(message: string, ...args: unknown[]) {
    if (!isProd) {
      // eslint-disable-next-line no-console
      console.debug(message, ...args);
    }
  },
};

export default logger;
