/**
 * Service Worker - 天链V3 离线缓存
 * 
 * 缓存策略:
 * - CacheFirst: 静态资源 (JS/CSS/图片/字体)
 * - NetworkFirst: API请求 (优先网络,离线回退缓存)
 * - NetworkOnly: WebSocket/SSE连接
 * 
 * 版本: 2026-06-01
 */

const SW_VERSION = 'v1';
const CACHE_NAMES = {
  static: `tianlian-static-${SW_VERSION}`,
  images: `tianlian-images-${SW_VERSION}`,
  api: `tianlian-api-${SW_VERSION}`,
  fonts: `tianlian-fonts-${SW_VERSION}`,
};

// 需要预缓存的静态资源（安装时缓存）
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/pwa-192x192.png',
  '/pwa-512x512.png',
  '/vite.svg',
];

// API 路径前缀（网络优先策略）
const API_PREFIXES = ['/api/', '/ws/'];

// 静态资源扩展名（缓存优先策略）
const STATIC_EXTENSIONS = /\.(js|css|woff2?|ttf|otf|eot)(\?.*)?$/;
const IMAGE_EXTENSIONS = /\.(png|jpg|jpeg|gif|svg|webp|ico)(\?.*)?$/;

// ==================== 安装 ====================
self.addEventListener('install', (event) => {
  console.log(`[SW ${SW_VERSION}] 安装中...`);
  
  event.waitUntil(
    caches.open(CACHE_NAMES.static)
      .then((cache) => {
        console.log('[SW] 预缓存静态资源...');
        return cache.addAll(PRECACHE_URLS);
      })
      .then(() => {
        console.log('[SW] 预缓存完成');
        // 跳过等待，立即激活
        return self.skipWaiting();
      })
      .catch((err) => {
        console.error('[SW] 预缓存失败:', err);
        // 即使预缓存失败也激活
        return self.skipWaiting();
      })
  );
});

// ==================== 激活 ====================
self.addEventListener('activate', (event) => {
  console.log(`[SW ${SW_VERSION}] 激活中...`);
  
  // 清除旧版本缓存
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name.startsWith('tianlian-') && !Object.values(CACHE_NAMES).includes(name))
          .map((name) => {
            console.log('[SW] 清除旧缓存:', name);
            return caches.delete(name);
          })
      );
    }).then(() => {
      console.log('[SW] 激活完成，接管页面');
      return self.clients.claim();
    })
  );
});

// ==================== 请求拦截 ====================
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // 不缓存 WebSocket (ws:// wss://)
  if (url.protocol === 'ws:' || url.protocol === 'wss:') {
    return;
  }
  
  // 不缓存非 GET 请求
  if (request.method !== 'GET') {
    return;
  }
  
  // 不缓存浏览器扩展和 DevTools 请求
  if (!url.protocol.startsWith('http') || url.hostname === 'localhost' && url.port === '' && !url.pathname.startsWith('/')) {
    return;
  }
  
  // 判断请求类型，应用不同策略
  if (isAPIRequest(url)) {
    // API 请求: 网络优先（离线时回退缓存）
    event.respondWith(networkFirstWithFallback(request, CACHE_NAMES.api));
  } else if (STATIC_EXTENSIONS.test(url.pathname)) {
    // JS/CSS: 缓存优先
    event.respondWith(cacheFirstWithRefresh(request, CACHE_NAMES.static));
  } else if (IMAGE_EXTENSIONS.test(url.pathname)) {
    // 图片: 缓存优先
    event.respondWith(cacheFirstWithRefresh(request, CACHE_NAMES.images));
  } else {
    // 其他（HTML等）: 网络优先
    event.respondWith(networkFirstWithFallback(request, CACHE_NAMES.static));
  }
});

// ==================== 策略实现 ====================

/**
 * 网络优先 - API请求策略
 * 优先从网络获取，失败时返回缓存
 */
async function networkFirstWithFallback(request, cacheName) {
  try {
    const response = await fetch(request);
    
    // 只缓存成功的响应（状态码 2xx）
    if (response.ok) {
      const cache = await caches.open(cacheName);
      // 克隆响应：一份缓存，一份返回
      cache.put(request, response.clone());
    }
    
    return response;
  } catch (error) {
    console.log('[SW] 网络不可用，使用缓存:', request.url);
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // 无缓存时返回离线提示（仅对 HTML 导航请求）
    if (request.mode === 'navigate') {
      return new Response(
        `<!DOCTYPE html>
        <html lang="zh-CN">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>网络不可用 - 天链V3</title>
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
              font-family: -apple-system, system-ui, sans-serif;
              background: #1e1918;
              color: #faf5f4;
              display: flex;
              justify-content: center;
              align-items: center;
              min-height: 100vh;
              padding: 20px;
            }
            .offline-card {
              background: #2a2423;
              border-radius: 12px;
              padding: 40px;
              text-align: center;
              max-width: 400px;
              width: 100%;
              box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            }
            .offline-card h1 { font-size: 48px; margin-bottom: 16px; }
            .offline-card h2 { font-size: 22px; margin-bottom: 12px; color: #ff5a36; }
            .offline-card p { color: #a6a1a0; line-height: 1.6; font-size: 14px; }
            .offline-card .retry-btn {
              display: inline-block;
              margin-top: 24px;
              padding: 10px 24px;
              background: #ff5a36;
              color: #fff;
              border: none;
              border-radius: 6px;
              font-size: 15px;
              cursor: pointer;
              transition: background 0.2s;
            }
            .offline-card .retry-btn:hover { background: #ff7a5c; }
          </style>
        </head>
        <body>
          <div class="offline-card">
            <h1>📡</h1>
            <h2>网络连接已断开</h2>
            <p>天链V3运行在离线模式。<br>部分实时数据可能不可用。<br>请检查网络连接后重试。</p>
            <button class="retry-btn" onclick="window.location.reload()">重新连接</button>
          </div>
        </body>
        </html>`,
        {
          status: 503,
          statusText: 'Service Unavailable',
          headers: new Headers({
            'Content-Type': 'text/html; charset=utf-8',
          }),
        }
      );
    }
    
    // 非导航请求无缓存时，返回 504
    return new Response('Network unavailable', { status: 504 });
  }
}

/**
 * 缓存优先 - 静态资源策略
 * 优先从缓存读取，后台异步更新缓存
 */
async function cacheFirstWithRefresh(request, cacheName) {
  const cachedResponse = await caches.match(request);
  
  if (cachedResponse) {
    // 后台异步更新缓存
    fetch(request).then((response) => {
      if (response.ok) {
        caches.open(cacheName).then((cache) => {
          cache.put(request, response);
        });
      }
    }).catch(() => {
      // 静默处理后台刷新失败
    });
    
    return cachedResponse;
  }
  
  // 无缓存时从网络获取
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    console.warn('[SW] 缓存未命中且网络不可用:', request.url);
    return new Response('Resource unavailable', { status: 404 });
  }
}

// ==================== 辅助函数 ====================

function isAPIRequest(url) {
  return API_PREFIXES.some((prefix) => url.pathname.startsWith(prefix));
}

// ==================== 消息处理 ====================
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    console.log('[SW] 收到跳过等待消息');
    self.skipWaiting();
  }
});