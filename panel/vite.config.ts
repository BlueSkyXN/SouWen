/// <reference types="vitest" />
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'
import path from 'path'

const ALL_SKINS = ['souwen-classic', 'carbon', 'apple']

function parseSkins(): string[] {
  const raw = process.env.VITE_SKINS || process.env.VITE_SKIN || 'all'
  if (raw === 'all') return ALL_SKINS
  return raw.split(',').map((s) => s.trim()).filter((s) => ALL_SKINS.includes(s))
}

function skinLoaderPlugin(skins: string[]): Plugin {
  const virtualId = 'virtual:skin-loader'
  const resolvedId = '\0' + virtualId

  return {
    name: 'souwen-skin-loader',
    resolveId(id) {
      if (id === virtualId) return resolvedId
    },
    load(id) {
      if (id !== resolvedId) return

      const lines: string[] = [`import '@core/styles/base.scss'`]

      skins.forEach((skinId, i) => {
        const varName = `skin${i}`
        lines.push(`import '/src/skins/${skinId}/styles/global.scss'`)
        lines.push(`import * as ${varName} from '/src/skins/${skinId}'`)
      })

      lines.push(`import { registerSkin } from '@core/skin-registry'`)
      lines.push('')

      skins.forEach((skinId, i) => {
        lines.push(`registerSkin('${skinId}', skin${i})`)
      })

      return lines.join('\n') + '\n'
    },
  }
}

const skins = parseSkins()

export default defineConfig({
  plugins: [react(), skinLoaderPlugin(skins), viteSingleFile()],
  resolve: {
    alias: {
      '@core': path.resolve(__dirname, 'src/core'),
      '@skin': path.resolve(__dirname, `src/skins/${skins[0]}`),
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
