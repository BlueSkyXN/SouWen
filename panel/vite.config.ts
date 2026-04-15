/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'
import path from 'path'

const skin = process.env.VITE_SKIN || 'souwen-classic'

export default defineConfig({
  plugins: [react(), viteSingleFile()],
  resolve: {
    alias: {
      '@core': path.resolve(__dirname, 'src/core'),
      '@skin': path.resolve(__dirname, `src/skins/${skin}`),
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/core/test/setup.ts',
    css: { modules: { classNameStrategy: 'non-scoped' } },
  },
})
