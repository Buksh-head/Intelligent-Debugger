/**
 * Vite config: plugins, plus a proxy that sends /api calls to the backend
 */
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  envDir: '../../deployment',
  server: {
    proxy: {
      // Send /api requests to the backend
      '/api': {
        // Docker sets this to http://backend:8000
        // Outside Docker it falls back to localhost:8000
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
    watch: {
      // Turned on in Docker so code changes reload the page
      usePolling: process.env.VITE_USE_POLLING === 'true',
    },
  },
  plugins: [
    react(),
    // React Compiler: speeds up components automatically
    babel({ presets: [reactCompilerPreset()] }),
    tailwindcss(),
  ],
})
