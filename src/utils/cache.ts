/**
 * 轻量级 API 响应缓存
 * TTL 过期 + LRU 淘汰策略
 */

interface CacheEntry<T> {
  data: T;
  expireAt: number;
  lastAccess: number;
}

const DEFAULT_TTL = 30_000; // 30 秒
const MAX_ENTRIES = 50;

const store = new Map<string, CacheEntry<any>>();
let lruSeq = 0; // 递增序列号，保证 LRU 淘汰时 lastAccess 唯一

/**
 * 从缓存读取，不存在或过期返回 null
 */
export function getCache<T>(key: string): T | null {
  const entry = store.get(key);
  if (!entry) return null;
  if (Date.now() > entry.expireAt) {
    store.delete(key);
    return null;
  }
  entry.lastAccess = ++lruSeq;
  return entry.data as T;
}

/**
 * 写入缓存，设置 TTL
 */
export function setCache<T>(key: string, data: T, ttl: number = DEFAULT_TTL): void {
  // LRU 淘汰
  if (store.size >= MAX_ENTRIES) {
    let oldestKey = '';
    let oldestTime = Infinity;
    for (const [k, v] of store) {
      if (v.lastAccess < oldestTime) {
        oldestTime = v.lastAccess;
        oldestKey = k;
      }
    }
    if (oldestKey) store.delete(oldestKey);
  }

  store.set(key, { data, expireAt: Date.now() + ttl, lastAccess: ++lruSeq });
}

/**
 * 带缓存的 fetch 函数
 * - 命中缓存直接返回
 * - 未命中调用 fetcher，结果写入缓存
 * - 支持 skipCache 跳过
 */
export async function cachedFetch<T>(
  key: string,
  fetcher: () => Promise<T>,
  options?: { ttl?: number; skipCache?: boolean }
): Promise<T> {
  if (!options?.skipCache) {
    const cached = getCache<T>(key);
    if (cached !== null) return cached;
  }
  const data = await fetcher();
  setCache(key, data, options?.ttl);
  return data;
}

/**
 * 清除指定 key 或全部缓存
 */
export function clearCache(key?: string): void {
  if (key) {
    store.delete(key);
  } else {
    store.clear();
  }
}

/**
 * 获取缓存统计（调试用）
 */
export function getCacheStats() {
  return {
    size: store.size,
    keys: Array.from(store.keys()),
  };
}

/**
 * 去抖动函数 — 用于搜索输入等高频触发场景
 */
export function debounce<T extends (...args: any[]) => void>(
  fn: T,
  delayMs: number = 300
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  return (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delayMs);
  };
}
