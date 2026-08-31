import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In dev the API runs on :8000; the app calls same-origin paths (/chat, /health)
// and Vite proxies them. In the deployed single service, FastAPI serves the
// built assets and the same relative paths hit the same origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/chat': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
});
