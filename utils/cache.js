// utils/cache.js - API缓存层（LRU + TTL + 请求去重）
// 性能优化：减少重复网络请求，提升页面切换速度

/**
 * LRU Cache with TTL support
 * 适用于微信小程序的轻量缓存
 */
class LRUCache {
  constructor(maxSize = 50) {
    this.maxSize = maxSize;
    this.cache = new Map();
    this.timers = {};
  }

  /**
   * 获取缓存值
   * @param {string} key
   * @returns {*} null if expired or missing
   */
  get(key) {
    if (!this.cache.has(key)) return null;

    const entry = this.cache.get(key);
    const now = Date.now();

    // TTL 过期检查
    if (entry.expireAt && entry.expireAt < now) {
      this.delete(key);
      return null;
    }

    // LRU: 移到末尾（Map 保持插入顺序）
    this.cache.delete(key);
    this.cache.set(key, entry);

    // 刷新 TTL（滑动过期）
    if (entry.ttl > 0) {
      this._refreshTimer(key, entry.ttl);
      entry.expireAt = now + entry.ttl;
    }

    return entry.value;
  }

  /**
   * 设置缓存值
   * @param {string} key
   * @param {*} value
   * @param {number} ttl - 过期时间（毫秒），0 表示不过期
   */
  set(key, value, ttl = 0) {
    // 容量淘汰
    if (this.cache.size >= this.maxSize && !this.cache.has(key)) {
      const oldestKey = this.cache.keys().next().value;
      this.delete(oldestKey);
    }

    const entry = {
      value,
      ttl,
      expireAt: ttl > 0 ? Date.now() + ttl : 0
    };

    // 如果已存在，先删再设（更新位置）
    if (this.cache.has(key)) {
      this.cache.delete(key);
    }
    this.cache.set(key, entry);

    if (ttl > 0) {
      this._refreshTimer(key, ttl);
    }
  }

  /**
   * 删除缓存
   */
  delete(key) {
    this.cache.delete(key);
    this._clearTimer(key);
  }

  /**
   * 清空所有缓存
   */
  clear() {
    Object.keys(this.timers).forEach(key => this._clearTimer(key));
    this.cache.clear();
  }

  /**
   * 清除指定前缀的缓存
   */
  clearByPrefix(prefix) {
    for (const key of this.cache.keys()) {
      if (key.startsWith(prefix)) {
        this.delete(key);
      }
    }
  }

  /**
   * 获取缓存统计
   */
  getStats() {
    return {
      size: this.cache.size,
      maxSize: this.maxSize,
      keys: Array.from(this.cache.keys())
    };
  }

  _refreshTimer(key, ttl) {
    this._clearTimer(key);
    this.timers[key] = setTimeout(() => this.delete(key), ttl);
  }

  _clearTimer(key) {
    if (this.timers[key]) {
      clearTimeout(this.timers[key]);
      delete this.timers[key];
    }
  }
}

// 全局单例
const cache = new LRUCache(50);

// 进行中的请求（去重）
const pendingRequests = new Map();

/**
 * 带缓存的请求包装
 * @param {Function} apiFn - API 函数
 * @param {Array} args - API 函数参数
 * @param {object} options - { cacheKey, ttl, force }
 * @returns {Promise}
 */
async function cachedRequest(apiFn, args = [], options = {}) {
  const { cacheKey, ttl = 30000, force = false } = options;

  // 强制刷新时跳过缓存
  if (!force && cacheKey) {
    const cached = cache.get(cacheKey);
    if (cached !== null) {
      return cached;
    }
  }

  // 请求去重：相同 cacheKey 的进行中请求复用
  if (cacheKey && pendingRequests.has(cacheKey)) {
    return pendingRequests.get(cacheKey);
  }

  const promise = Promise.resolve(apiFn(...args));

  if (cacheKey) {
    pendingRequests.set(cacheKey, promise);

    try {
      const result = await promise;
      cache.set(cacheKey, result, ttl);
      return result;
    } finally {
      pendingRequests.delete(cacheKey);
    }
  }

  return promise;
}

module.exports = {
  cache,
  cachedRequest,
  LRUCache
};
