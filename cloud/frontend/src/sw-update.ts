/**
 * 自定义 Hook: 处理 Service Worker 更新事件
 * vite-plugin-pwa 会通过 autoUpdate 模式自动处理更新
 * 但我们保留一个自定义事件监听以展示更新通知
 */
export function useSWUpdate() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      // New SW has taken over, reload to get fresh assets
      window.location.reload();
    });
  }
}

export default useSWUpdate;