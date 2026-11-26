import { defineConfig } from 'vite';

const api = { target: 'http://localhost:8002', changeOrigin: true };

export default defineConfig({
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      ['/health', '/sources', '/storage', '/analysis', '/performance', '/sql', '/docs', '/openapi.json']
        .map((path) => [path, api]),
    ),
  },
});
