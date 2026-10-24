/**
 * 懒加载 chunk 失败自动自愈（发版后旧会话恢复）
 *
 * 背景：Vite 按内容哈希命名 chunk（如 index-FRuzy3rx.js），每次发版后旧 chunk
 * 即被删除。用户浏览器若还开着发版前的旧页面（SPA 会话），点进懒加载路由时
 * 旧代码会去请求已不存在的旧 chunk → 404 →
 * "TypeError: Failed to fetch dynamically imported module" 页面报错。
 *
 * 方案：包装 React.lazy 的动态 import，chunk 加载失败时自动整页刷新一次，
 * 让浏览器拉取最新 index.html 加载新构建。sessionStorage 冷却保护防刷新死循环。
 *
 * 实战案例：2026-10-08 http://demo.example.com/operate/points 报
 *   TypeError: Failed to fetch dynamically imported module:
 *   http://demo.example.com/assets/index-FRuzy3rx.js
 * （旧会话请求 10-07 凌晨发版后被删的旧 chunk；新构建本身完好 200）
 */
import { lazy, type ComponentType } from 'react';

/** sessionStorage 冷却标记 key */
export const CHUNK_RELOAD_STORAGE_KEY = 'tl:chunk-reload-ts';

/** 冷却窗口：10 秒内最多自动刷新一次，防刷新后仍失败导致死循环 */
const RELOAD_COOLDOWN_MS = 10_000;

/** 判断是否为 chunk 加载失败（覆盖 Chrome/Safari/Firefox 报错文案） */
export function isChunkLoadError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  return (
    // Chrome / Edge
    /Failed to fetch dynamically imported module/i.test(err.message) ||
    // Safari
    /Importing a module script failed/i.test(err.message) ||
    // Firefox
    /error loading dynamically imported module/i.test(err.message) ||
    // webpack 风格（历史遗留兼容）
    /Loading (CSS )?chunk \d+ failed/i.test(err.message)
  );
}

/** chunk 失败时自动整页刷新（带冷却保护） */
function scheduleReloadOnChunkError(): void {
  if (typeof window === 'undefined') return;
  let last = 0;
  try {
    last = Number(window.sessionStorage.getItem(CHUNK_RELOAD_STORAGE_KEY)) || 0;
  } catch {
    // sessionStorage 不可用（隐私模式等）→ 跳过冷却判断直接刷新
  }
  if (Date.now() - last <= RELOAD_COOLDOWN_MS) return;
  try {
    window.sessionStorage.setItem(CHUNK_RELOAD_STORAGE_KEY, String(Date.now()));
  } catch {
    // ignore
  }
  window.location.reload();
}

/**
 * 给动态 import 的 Promise 挂 chunk 失败自愈：失败先触发整页刷新，
 * 再把原错误抛出（刷新是异步导航，抛错让当前渲染落回 ErrorBoundary 兜底）。
 */
export function withChunkReload<T>(importer: Promise<T>): Promise<T> {
  return importer.catch((err: unknown) => {
    if (isChunkLoadError(err)) {
      scheduleReloadOnChunkError();
    }
    throw err;
  });
}

/** React.lazy + chunk 失败自动刷新，用法与 React.lazy 完全一致 */
export function lazyRetry<T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
) {
  return lazy(() => withChunkReload(factory()));
}
