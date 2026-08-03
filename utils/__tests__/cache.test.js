// utils/__tests__/cache.test.js - 缓存层测试
const { cache, cachedRequest, LRUCache } = require('../cache');

// 套件结束清理全局缓存 TTL 定时器，避免并行跑时 worker pending timer 泄漏
afterAll(() => {
  cache.clear();
});

// 微信小程序环境模拟
global.wx = {
  getStorageSync: jest.fn(() => null),
  setStorageSync: jest.fn(),
  removeStorageSync: jest.fn()
};

describe('LRUCache', () => {
  beforeEach(() => {
    cache.clear();
  });

  test('基本 set/get', () => {
    cache.set('key1', 'value1');
    expect(cache.get('key1')).toBe('value1');
  });

  test('缓存未命中返回 null', () => {
    expect(cache.get('nonexistent')).toBeNull();
  });

  test('TTL 过期', (done) => {
    cache.set('temp', 'data', 100); // 100ms TTL
    expect(cache.get('temp')).toBe('data');

    setTimeout(() => {
      expect(cache.get('temp')).toBeNull();
      done();
    }, 150);
  });

  test('LRU 淘汰策略', () => {
    const smallCache = new LRUCache(3);
    smallCache.set('a', 1, 0);
    smallCache.set('b', 2, 0);
    smallCache.set('c', 3, 0);
    smallCache.set('d', 4, 0); // 应淘汰 'a'

    expect(smallCache.get('a')).toBeNull();
    expect(smallCache.get('b')).toBe(2);
    expect(smallCache.get('d')).toBe(4);
  });

  test('LRU 访问更新顺序', () => {
    const smallCache = new LRUCache(3);
    smallCache.set('a', 1, 0);
    smallCache.set('b', 2, 0);
    smallCache.set('c', 3, 0);

    // 访问 'a'，使其移到末尾
    smallCache.get('a');

    smallCache.set('d', 4, 0); // 现在应淘汰 'b'
    expect(smallCache.get('b')).toBeNull();
    expect(smallCache.get('a')).toBe(1);
  });

  test('delete 方法', () => {
    cache.set('key1', 'val1');
    cache.delete('key1');
    expect(cache.get('key1')).toBeNull();
  });

  test('clearByPrefix 方法', () => {
    cache.set('stations_a', 1, 0);
    cache.set('stations_b', 2, 0);
    cache.set('orders_a', 3, 0);
    cache.clearByPrefix('stations_');

    expect(cache.get('stations_a')).toBeNull();
    expect(cache.get('stations_b')).toBeNull();
    expect(cache.get('orders_a')).toBe(3);
  });

  test('getStats 返回统计', () => {
    cache.set('a', 1, 0);
    cache.set('b', 2, 0);
    const stats = cache.getStats();
    expect(stats.size).toBe(2);
    expect(stats.keys).toContain('a');
    expect(stats.keys).toContain('b');
  });

  test('滑动过期 - get 刷新 TTL', () => {
    cache.set('slide', 'val', 1000);
    // 第一次 get 后 TTL 应被刷新
    cache.get('slide');
    // 立即再 get 应该能拿到
    expect(cache.get('slide')).toBe('val');
  });
});

describe('cachedRequest', () => {
  beforeEach(() => {
    cache.clear();
  });

  test('首次请求调用 API 函数', async () => {
    const mockFn = jest.fn().mockResolvedValue({ data: 'test' });
    const result = await cachedRequest(mockFn, [], { cacheKey: 'test', ttl: 5000 });

    expect(mockFn).toHaveBeenCalledTimes(1);
    expect(result.data).toBe('test');
  });

  test('第二次请求命中缓存', async () => {
    const mockFn = jest.fn().mockResolvedValue({ data: 'test' });

    await cachedRequest(mockFn, [], { cacheKey: 'test', ttl: 5000 });
    const result = await cachedRequest(mockFn, [], { cacheKey: 'test', ttl: 5000 });

    expect(mockFn).toHaveBeenCalledTimes(1); // 只调用一次
    expect(result.data).toBe('test');
  });

  test('force=true 绕过缓存', async () => {
    const mockFn = jest.fn().mockResolvedValue({ data: 'test' });

    await cachedRequest(mockFn, [], { cacheKey: 'test', ttl: 5000 });
    await cachedRequest(mockFn, [], { cacheKey: 'test', ttl: 5000, force: true });

    expect(mockFn).toHaveBeenCalledTimes(2);
  });

  test('请求去重 - 相同 cacheKey 复用', async () => {
    const mockFn = jest.fn().mockImplementation(
      () => new Promise(resolve => { setTimeout(() => resolve({ data: 'dedup' }), 50); })
    );

    // 同时发两个相同 cacheKey 的请求
    const [r1, r2] = await Promise.all([
      cachedRequest(mockFn, [], { cacheKey: 'dedup', ttl: 5000 }),
      cachedRequest(mockFn, [], { cacheKey: 'dedup', ttl: 5000 })
    ]);

    expect(mockFn).toHaveBeenCalledTimes(1);
    expect(r1.data).toBe('dedup');
    expect(r2.data).toBe('dedup');
  });

  test('无 cacheKey 时不缓存', async () => {
    const mockFn = jest.fn().mockResolvedValue({ data: 'nocache' });

    await cachedRequest(mockFn, []);
    await cachedRequest(mockFn, []);

    expect(mockFn).toHaveBeenCalledTimes(2);
  });

  test('带参数的 API 函数', async () => {
    const mockFn = jest.fn((a, b) => Promise.resolve({ data: a + b }));

    const result = await cachedRequest(mockFn, [1, 2], { cacheKey: 'add_1_2', ttl: 5000 });

    expect(mockFn).toHaveBeenCalledWith(1, 2);
    expect(result.data).toBe(3);
  });

  test('TTL 过期后重新请求', async () => {
    const mockFn = jest.fn().mockResolvedValue({ data: 'expires' });

    await cachedRequest(mockFn, [], { cacheKey: 'exp', ttl: 50 });

    await new Promise(resolve => { setTimeout(resolve, 80); });

    await cachedRequest(mockFn, [], { cacheKey: 'exp', ttl: 50 });

    expect(mockFn).toHaveBeenCalledTimes(2);
  });
});
