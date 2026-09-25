import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ plugins: [react()], server: { proxy: {
  '/core': {target: 'http://127.0.0.1:8000', rewrite: p => p.replace(/^\/core/, ''), ws: true},
  '/tasks-api': {target: 'http://127.0.0.1:8001', rewrite: p => p.replace(/^\/tasks-api/, '')}
}}});
