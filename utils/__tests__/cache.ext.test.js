// utils/__tests__/cache.ext.test.js
// F663: cache.js branches 92.5→100%
const { LRUCache, cachedRequest, cache } = require('../cache');

afterAll(() => {
  cache.clear();
});

describe('cache.ext: branches 92.5→100%', () => {
  beforeEach(() => {
    cache.clear();
  });

  // L9: LRUCache无参构造 → maxSize默认50
  test('LRUCache无参构造: maxSize=50', () => {
    const c = new LRUCache();
    expect(c.maxSize).toBe(50);
    c.set('a', 1, 0);
    expect(c.get('a')).toBe(1);
  });

  // L27: entry.expireAt=0 (ttl=0) → if条件falsy → 不过期
  test('get: expireAt=0 → 不过期 (if条件短路)', () => {
    const c = new LRUCache(5);
    c.set('perm', 'val', 0); // ttl=0 → expireAt=0
    // 直接访问cache内部确认expireAt=0
    const entry = c.cache.get('perm');
    expect(entry.expireAt).toBe(0);
    // get应该返回值而非null（if条件不进入过期分支）
    expect(c.get('perm')).toBe('val');
  });

  // L139: cachedRequest options无ttl → 默认30000
  test('cachedRequest: 无ttl参数 → 默认30000ms', async () => {
    const mockFn = jest.fn().mockResolvedValue({ data: 'default-ttl' });
    const result = await cachedRequest(mockFn, [], { cacheKey: 'dt' });
    expect(result.data).toBe('default-ttl');

    // 验证cache中entry的ttl为30000
    const entry = cache.cache.get('dt');
    expect(entry.ttl).toBe(30000);
  });

  // 补充: cachedRequest完全无options
  test('cachedRequest: 无options → 直接调用不缓存', async () => {
    const mockFn = jest.fn().mockResolvedValue({ data: 'no-opts' });
    const result = await cachedRequest(mockFn, []);
    expect(mockFn).toHaveBeenCalledTimes(1);
    expect(result.data).toBe('no-opts');
  });

  // 补充: force=true但cacheKey存在 → 绕过缓存
  test('cachedRequest: force=true有cacheKey → 绕过缓存直接请求', async () => {
    const mockFn = jest.fn().mockResolvedValue({ data: 'forced' });
    // 先填充缓存
    await cachedRequest(mockFn, [], { cacheKey: 'fk', ttl: 5000 });
    // force=true绕过
    const result = await cachedRequest(mockFn, [], { cacheKey: 'fk', ttl: 5000, force: true });
    expect(mockFn).toHaveBeenCalledTimes(2);
    expect(result.data).toBe('forced');
  });

  // 补充: 请求去重 reject路径
  test('cachedRequest: API函数reject → pendingRequests清理', async () => {
    const mockFn = jest.fn().mockRejectedValue(new Error('api fail'));

    await expect(cachedRequest(mockFn, [], { cacheKey: 'fail-key', ttl: 5000 })).rejects.toThrow('api fail');
    await expect(cachedRequest(mockFn, [], { cacheKey: 'fail-key', ttl: 5000 })).rejects.toThrow('api fail');
    expect(mockFn).toHaveBeenCalledTimes(2);
  });
});
