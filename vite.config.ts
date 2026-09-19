import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
  },
  build: {
    // Everything the interface needs is bundled; the app runs offline (spec 4).
    assetsInlineLimit: 0,
    target: 'es2022',
  },
});
