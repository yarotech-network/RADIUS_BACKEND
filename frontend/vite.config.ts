/// <reference types="vitest/config" />
import { defineConfig, loadEnv, type PluginOption, type UserConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig(async ({ mode }): Promise<UserConfig> => {
  const env = loadEnv(mode, process.cwd(), '');
  const proxyTarget = env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000';
  const plugins: PluginOption[] = [react(), tailwindcss()];
  if (process.env.ANALYZE) {
    // Lazy import keeps the visualizer out of normal builds.
    const { visualizer } = await import('rollup-plugin-visualizer');
    plugins.push(
      visualizer({ filename: 'stats.html', gzipSize: true, brotliSize: true, template: 'treemap' }),
    );
  }
  return {
    plugins,
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: false,
      allowedHosts: true,
      proxy: {
        '/api': { target: proxyTarget, changeOrigin: true },
        '/health': { target: proxyTarget, changeOrigin: true },
      },
    },
    preview: { host: '0.0.0.0', port: 4173, allowedHosts: true },
    build: {
      target: 'es2022',
      sourcemap: false,
      chunkSizeWarningLimit: 600,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return undefined;
            if (
              /node_modules\/(react|react-dom|scheduler|react-router|cookie|set-cookie-parser)\//.test(
                id,
              )
            )
              return 'react';
            if (id.includes('@tanstack')) return 'query';
            if (/node_modules\/(react-hook-form|@hookform|zod)\//.test(id)) return 'forms';
            return undefined;
          },
        },
      },
    },
    test: {
      env: {
        ...(process.env.LIVE_API ? { LIVE_API: process.env.LIVE_API } : {}),
        ...(process.env.LIVE_API_THROTTLE
          ? { LIVE_API_THROTTLE: process.env.LIVE_API_THROTTLE }
          : {}),
      },
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./vitest.setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      css: false,
    },
  };
});
