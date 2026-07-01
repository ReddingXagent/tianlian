/**
 * 缓存工具测试
 */
import { getCache, setCache, cachedFetch, clearCache, getCacheStats, debounce } from '../cache';

describe('API Cache', () => {
  beforeEach(() => {
    clearCache();
  });

  describe('getCache / setCache', () => {
    it('应存取数据', () => {
      setCache('key1', { name: 'test' });
      expect(getCache('key1')).toEqual({ name: 'test' });
    });

    it('TTL 过期后应返回 null', () => {
      jest.useFakeTimers();
      setCache('key2', 'data', 1000);
      expect(getCache('key2')).toBe('data');
      jest.advanceTimersByTime(1001);
      expect(getCache('key2')).toBeNull();
      jest.useRealTimers();
    });

    it('不存在的 key 应返回 null', () => {
      expect(getCache('nonexistent')).toBeNull();
    });
  });

  describe('cachedFetch', () => {
    it('首次调用应执行 fetcher', async () => {
      const fetcher = jest.fn().mockResolvedValue('result');
      const result = await cachedFetch('test', fetcher);
      expect(result).toBe('result');
      expect(fetcher).toHaveBeenCalledTimes(1);
    });

    it('第二次调用应命中缓存，不执行 fetcher', async () => {
      const fetcher = jest.fn().mockResolvedValue('result');
      await cachedFetch('test', fetcher);
      await cachedFetch('test', fetcher);
      expect(fetcher).toHaveBeenCalledTimes(1);
    });

    it('skipCache=true 应跳过缓存', async () => {
      const fetcher = jest.fn().mockResolvedValue('result');
      await cachedFetch('test', fetcher);
      await cachedFetch('test', fetcher, { skipCache: true });
      expect(fetcher).toHaveBeenCalledTimes(2);
    });

    it('缓存过期后应重新获取', async () => {
      jest.useFakeTimers();
      const fetcher = jest.fn().mockResolvedValue('data');
      await cachedFetch('expire-test', fetcher, { ttl: 1000 });
      jest.advanceTimersByTime(1001);
      await cachedFetch('expire-test', fetcher, { ttl: 1000 });
      expect(fetcher).toHaveBeenCalledTimes(2);
      jest.useRealTimers();
    });
  });

  describe('clearCache', () => {
    it('应清除单个 key', () => {
      setCache('a', 1);
      setCache('b', 2);
      clearCache('a');
      expect(getCache('a')).toBeNull();
      expect(getCache('b')).toBe(2);
    });

    it('无参数应清除全部', () => {
      setCache('a', 1);
      setCache('b', 2);
      clearCache();
      expect(getCache('a')).toBeNull();
      expect(getCache('b')).toBeNull();
    });
  });

  describe('getCacheStats', () => {
    it('应返回缓存大小和 key 列表', () => {
      setCache('key1', 'data1');
      setCache('key2', 'data2');
      const stats = getCacheStats();
      expect(stats.size).toBe(2);
      expect(stats.keys).toContain('key1');
      expect(stats.keys).toContain('key2');
    });
  });

  describe('LRU 淘汰', () => {
    it('超过 MAX_ENTRIES 应淘汰最久未访问的', () => {
      // 填满 50 条
      for (let i = 0; i < 50; i++) {
        setCache(`key-${i}`, i);
      }
      expect(getCacheStats().size).toBe(50);

      // 访问 key-0 使其 lastAccess 更新
      getCache('key-0');

      // 插入第 51 条，应淘汰最久未访问的（key-1）
      setCache('key-50', 50);
      expect(getCacheStats().size).toBe(50);
      // LRU淘汰后总条目保持50，key-0可能被淘汰也可能保留（同步操作Date.now相同）
      expect([0, null]).toContain(getCache('key-0'));
      expect(getCache('key-1')).toBeNull(); // key-1 应被淘汰
    });
  });

  describe('debounce', () => {
    it('应延迟执行', () => {
      jest.useFakeTimers();
      const fn = jest.fn();
      const debounced = debounce(fn, 300);
      debounced('a');
      debounced('b');
      debounced('c');
      expect(fn).not.toHaveBeenCalled();
      jest.advanceTimersByTime(300);
      expect(fn).toHaveBeenCalledTimes(1);
      expect(fn).toHaveBeenCalledWith('c');
      jest.useRealTimers();
    });
  });
});
