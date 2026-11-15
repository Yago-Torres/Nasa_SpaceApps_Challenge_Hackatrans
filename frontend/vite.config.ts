/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // 127.0.0.1, not localhost: Node 17+ resolves localhost to ::1 first, uvicorn listens on IPv4 only,
  // and the refused connection surfaced as an empty HTTP 500 from the dev proxy (e.g. on register).
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  // Generous per-test timeout: full user flows in jsdom are slow on shared CI runners.
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'], restoreMocks: true, testTimeout: 20000 },
});
