import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

// Frontend tests live in tests/frontend at the repo root, next to the backend
// tests. The repo root has its own stray node_modules with a second copy of
// React, so these packages are pinned to this app's copies.
export default mergeConfig(viteConfig, defineConfig({
  resolve: {
    dedupe: [
      'react',
      'react-dom',
      'react-router-dom',
      '@monaco-editor/react',
      '@testing-library/react',
      '@testing-library/user-event',
    ],
  },
  server: {
    fs: { allow: ['../..'] },
  },
  test: {
    dir: '../../tests/frontend',
    environment: 'jsdom',
  },
}))
