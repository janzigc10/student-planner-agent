import { configDefaults, defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
const backendOrigin = process.env.STUDENT_PLANNER_BACKEND_ORIGIN ?? 'http://localhost:8000'
const backendWsOrigin = backendOrigin.replace(/^http/, 'ws')
const backendProxy = {
  '/api': backendOrigin,
  '/ws': {
    target: backendWsOrigin,
    ws: true,
  },
}

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'autoUpdate',
      includeAssets: ['pwa.svg'],
      manifest: {
        name: '学习规划助手',
        short_name: '学习助手',
        start_url: '/chat',
        display: 'standalone',
        background_color: '#ffffff',
        theme_color: '#1677ff',
        icons: [
          { src: '/pwa.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' },
        ],
      },
    }),
  ],
  server: {
    proxy: backendProxy,
  },
  preview: {
    allowedHosts: ['.loca.lt'],
    proxy: backendProxy,
  },
  test: {
    environment: 'jsdom',
    exclude: [...configDefaults.exclude, 'e2e/**'],
    setupFiles: './src/test/setup.ts',
    globals: true,
  },
})
