import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@components': path.resolve(__dirname, './src/components'),
      '@features': path.resolve(__dirname, './src/features'),
      '@design-system': path.resolve(__dirname, './src/design-system'),
      '@hooks': path.resolve(__dirname, './src/hooks'),
      '@services': path.resolve(__dirname, './src/services'),
      '@store': path.resolve(__dirname, './src/store'),
      '@types-athena': path.resolve(__dirname, './src/types/athena.ts'),
      '@utils': path.resolve(__dirname, './src/utils'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // All /api/* calls proxied to existing Flask server
      '/api': {
        target: 'http://localhost:3000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: '../static/athena',   // Flask serves built files from /static/athena
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor':  ['react', 'react-dom', 'react-router-dom'],
          'query-vendor':  ['@tanstack/react-query', 'axios'],
          'plotly-vendor': ['plotly.js-dist-min', 'react-plotly.js'],
          'motion-vendor': ['framer-motion'],
          'table-vendor':  ['@tanstack/react-table'],
        },
      },
    },
  },
});
