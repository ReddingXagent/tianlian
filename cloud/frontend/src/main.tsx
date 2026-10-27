import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider, theme as antTheme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import './i18n';
import './index.css';
import './dark-mode.css';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';

// ==================== 全局错误兜底 ====================
// 捕获未处理的 Promise rejection 与同步运行时异常, 仅 console.error 记录便于排障;
// 不弹窗/不刷屏 — 业务错误已由 axios 拦截器 message.error 统一提示, 此处仅兜底漏网异常。
window.addEventListener('unhandledrejection', (event) => {
  console.error('[UnhandledRejection]', event.reason);
});
window.onerror = (msg, source, lineno, colno, error) => {
  console.error('[WindowError]', { msg, source, lineno, colno, error });
  return false; // 不抑制浏览器默认控制台输出
};

// ==================== Service Worker 注册 ====================
// 离线缓存支持: 使用自定义 sw.js（非 vite-plugin-pwa 自动生成的 SW）
// vite-plugin-pwa 在 vite.config.ts 中已注释，此处手动注册确保可控性
if ('serviceWorker' in navigator) {
  // 先注销所有已注册的旧 SW (来自 vite-plugin-pwa 或其他来源)
  (async () => {
    try {
      const registrations = await navigator.serviceWorker.getRegistrations();
      const registrationsToRemove = registrations.filter(
        reg => reg.active && reg.active.scriptURL && !reg.active.scriptURL.endsWith('/sw.js')
      );
      registrationsToRemove.forEach(reg => {
        reg.unregister();
      });
      if (registrationsToRemove.length > 0) {
        // 清除非 sw.js 的所有缓存
        if ('caches' in window) {
          const names = await caches.keys();
          names.forEach(name => {
            if (!name.startsWith('tianlian-')) {
              caches.delete(name);
            }
          });
        }
      }
    } catch (err) {
      console.warn('[SW] 注销失败:', err);
    }
  })();

  // 注册自定义 Service Worker (sw.js)
  window.addEventListener('load', async () => {
    try {
      const registration = await navigator.serviceWorker.register('/sw.js');
      // 监听 SW 更新
      registration.addEventListener('updatefound', () => {
        const newWorker = registration.installing;
        if (newWorker) {
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              // 有新版本可用，触发自定义事件，由 OfflineNotice 组件捕获展示更新通知
              window.dispatchEvent(new CustomEvent('sw:update', { detail: { sw: registration } }));
            }
          });
        }
      });
    } catch (err) {
      console.warn('[SW] Service Worker 注册失败:', err);
    }
  });
}

// ==================== 应用根组件（接入 ThemeProvider）====================
const RootApp: React.FC = () => {
  const { isDark } = useTheme();

  // antd 暗色/亮色 token
  const themeConfig = {
    algorithm: isDark ? antTheme.darkAlgorithm : undefined,
    token: {
      colorPrimary: '#ff5a36',
      borderRadius: 6,
      fontFamily: '"Fragment Mono", -apple-system, system-ui, sans-serif',
    },
    components: {
      Button: {
        primaryShadow: '0 2px 4px rgba(255,90,54,0.2)',
      },
      Menu: {
        itemBg: 'transparent',
        itemSelectedBg: 'rgba(255,90,54,0.08)',
        itemSelectedColor: '#ff5a36',
        itemHoverBg: 'rgba(255,90,54,0.04)',
      },
    },
  };

  return (
    <ConfigProvider locale={zhCN} theme={themeConfig}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  );
};

// ==================== 应用挂载 ====================
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <RootApp />
    </ThemeProvider>
  </React.StrictMode>
);