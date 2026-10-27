import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [
    react({
      babel: {
        parserOpts: {
          plugins: ['typescript']
        }
      }
    }),
    // VitePWA 已禁用 - 管理后台不需要 PWA，Service Worker 会缓存旧的 401 响应导致登录闪退
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3004,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  esbuild: {
    logOverride: { 'this-is-undefined-in-esm': 'silent' }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          // antd ecosystem - large vendor chunk
          if (id.includes('node_modules/antd/') || id.includes('node_modules/@ant-design/')) {
            return 'vendor-antd';
          }
          // echarts + zrender - large, lazy loaded via code splitting
          if (id.includes('node_modules/echarts/') || id.includes('node_modules/zrender/')) {
            return 'vendor-echarts';
          }
          // react core (always needed on first paint)
          if (id.includes('node_modules/react/') || id.includes('node_modules/react-dom/') || id.includes('node_modules/scheduler/')) {
            return 'vendor-react';
          }
          // react ecosystem (router, query)
          if (id.includes('node_modules/react-router') || id.includes('node_modules/@tanstack/')) {
            return 'vendor-react-ecosystem';
          }
          // three.js + R3F ecosystem — 不做 manualChunks：
          // 强制分组会把 Vite __vitePreload helper 困进 vendor-three，入口被迫静态依赖 863KB three.js (卡 d9ea4182)
          // DigitalTwin 页走 lazy import，Rollup 自动按懒加载边界生成独立 three chunk
          // dayjs (antd dependency)
          if (id.includes('node_modules/dayjs/')) {
            return 'vendor-dayjs';
          }
          // axios (small but commonly used)
          if (id.includes('node_modules/axios/')) {
            return 'vendor-axios';
          }
          // react-quill (only on knowledge edit pages)
          if (id.includes('node_modules/react-quill-new/')) {
            return 'vendor-editor';
          }
        },
      },
    },
    chunkSizeWarningLimit: 1300,
    // 启用 CSS 代码分割
    cssCodeSplit: true,
    // 减少开发环境的 sourcemap
    sourcemap: false,
  },
});