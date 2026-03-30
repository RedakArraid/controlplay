import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/** En prod, les chunks sont servis via le mount FastAPI existant `GET /static/...` (pas de mount séparé /assets). */
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/static/spa/' : '/',
  plugins: [react(), tailwindcss()],
  build: {
    outDir: path.resolve(__dirname, '../app/static/spa'),
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    /** Écoute sur toutes les interfaces (utile LAN / outils). Le HMR ne marche que via ce serveur. */
    host: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
}))
