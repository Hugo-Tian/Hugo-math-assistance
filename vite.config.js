import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({ plugins: [vue()], server: {
  proxy: { '/api': process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000' },
  fs: { deny: ['**/.env', '**/.env.*', '**/*.db', '**/*.db-*', '**/data/**', '**/backend/**', '**/tests/**', '**/scripts/**', '**/tmp/**', '**/storage/**', '**/evals/**', '**/migrations/**', '**/requirements*.txt'] }
} })
