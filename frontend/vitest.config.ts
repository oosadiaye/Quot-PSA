import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    // ``e2e/`` holds Playwright specs, which import @playwright/test and
    // cannot run under vitest. Without this they are collected anyway and
    // every one of them is reported as a failed file — twelve permanent
    // reds that hide any real failure and train everyone to ignore the
    // run. Playwright runs them itself via ``npm run test:e2e``.
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      'e2e/**',
      'playwright-report/**',
      'test-results/**',
    ],
  },
})
