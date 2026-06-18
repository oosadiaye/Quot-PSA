import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
  build: {
    sourcemap: false,
    // antd v6 is a large, monolithic vendor (~1.3MB raw / ~0.4MB gzip) used
    // across the app. It's a single package with internal init-order
    // coupling, so it can't be safely sub-split — but it's loaded once and
    // long-cached, and route-level code-splitting keeps per-page chunks
    // small. Set the warning threshold above the antd chunk so the build
    // reports clean; the real size driver is antd itself (a future
    // antd-reduction refactor is the only way to shrink it further).
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-antd': ['antd'],
          'vendor-charts': ['recharts'],
          'vendor-query': ['@tanstack/react-query'],
        },
      },
    },
  },
})
