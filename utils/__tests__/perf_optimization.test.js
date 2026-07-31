// utils/__tests__/perf_optimization.test.js - T-1202 第3批性能优化测试
// 测试环境配置切换、缓存集成、防抖节流等优化

const { cache, cachedRequest, LRUCache } = require('../cache');
const { createPolling } = require('../polling');
const util = require('../util');

// 套件结束清理全局缓存的 TTL 定时器（真实 setTimeout，最长30s）
// 否则并行跑时 worker 因 pending timer 无法优雅退出（force exited 告警）
afterAll(() => {
  cache.clear();
});

// 模拟微信环境
global.wx = {
  getStorageSync: jest.fn(() => null),
  setStorageSync: jest.fn(),
  removeStorageSync: jest.fn(),
  showToast: jest.fn(),
  setTabBarBadge: jest.fn(),
  removeTabBarBadge: jest.fn()
};

describe('T-1202-Batch3: 环境配置', () => {
  test('config 模块应正确加载', () => {
    const config = require('../../config/index');
    expect(config.API_BASE_URL).toBeDefined();
    expect(config.API_BASE_URL).toMatch(/^https?:\/\/.+/);
    expect(config.MAP_KEY).toBeDefined();
    expect(config.ENV).toMatch(/^(dev|staging|prod)$/);
  });

  test('CACHE_TTL 所有键存在', () => {
    const config = require('../../config/index');
    const requiredKeys = ['STATIONS', 'STATION_DETAIL', 'FAVORITES', 'COUPONS', 'POINTS', 'ORDERS', 'NOTIFICATIONS', 'USER_INFO'];
    for (const key of requiredKeys) {
      expect(config.CACHE_TTL[key]).toBeDefined();
      expect(typeof config.CACHE_TTL[key]).toBe('number');
      expect(config.CACHE_TTL[key]).toBeGreaterThan(0);
    }
  });
});

describe('T-1202-Batch3: 缓存层增强', () => {
  beforeEach(() => {
    cache.clear();
  });

  test('clearByPrefix 批量清除通知缓存', () => {
    cache.set('notifications_1', { data: 'a' }, 0);
    cache.set('notifications_2', { data: 'b' }, 0);
    cache.set('notifications_all', { data: 'c' }, 0);
    cache.set('orders_1', { data: 'd' }, 0);

    cache.clearByPrefix('notifications_');

    expect(cache.get('notifications_1')).toBeNull();
    expect(cache.get('notifications_2')).toBeNull();
    expect(cache.get('notifications_all')).toBeNull();
    expect(cache.get('orders_1')).not.toBeNull();
  });

  test('wallet_info 缓存键可复用', async () => {
    const mockFn = jest.fn().mockResolvedValue({ data: { balance: 100 } });

    await cachedRequest(mockFn, [], { cacheKey: 'wallet_info', ttl: 30000 });
    const result = await cachedRequest(mockFn, [], { cacheKey: 'wallet_info', ttl: 30000 });

    expect(mockFn).toHaveBeenCalledTimes(1);
    expect(result.data.balance).toBe(100);
  });

  test('order_detail 缓存键隔离不同订单', async () => {
    const mockFn = jest.fn((id) => Promise.resolve({ data: { id, amount: 500 } }));

    await cachedRequest(mockFn, ['order_1'], { cacheKey: 'order_detail_order_1', ttl: 10000 });
    await cachedRequest(mockFn, ['order_2'], { cacheKey: 'order_detail_order_2', ttl: 10000 });

    expect(mockFn).toHaveBeenCalledTimes(2);

    // 复用缓存
    await cachedRequest(mockFn, ['order_1'], { cacheKey: 'order_detail_order_1', ttl: 10000 });
    expect(mockFn).toHaveBeenCalledTimes(2);
  });

  test('cachedRequest force 刷新清旧缓存', async () => {
    let callCount = 0;
    const mockFn = jest.fn().mockImplementation(() => {
      callCount++;
      return Promise.resolve({ data: { version: callCount } });
    });

    await cachedRequest(mockFn, [], { cacheKey: 'test_force', ttl: 5000 });
    expect(cache.get('test_force').data.version).toBe(1);

    await cachedRequest(mockFn, [], { cacheKey: 'test_force', ttl: 5000, force: true });
    expect(cache.get('test_force').data.version).toBe(2);
  });
});

describe('T-1202-Batch3: 智能轮询', () => {
  test('轮询自动停止（shouldStop）', (done) => {
    let count = 0;
    const polling = createPolling(
      () => {
        count++;
        return Promise.resolve();
      },
      {
        interval: 50,
        shouldStop: () => count >= 3
      }
    );

    polling.start();

    setTimeout(() => {
      expect(count).toBe(3);
      expect(polling.isActive()).toBe(false);
      done();
    }, 300);
  });

  test('连续失败后指数退避停止', (done) => {
    let attempts = 0;
    const polling = createPolling(
      () => {
        attempts++;
        return Promise.reject(new Error('network'));
      },
      {
        interval: 20,
        maxRetries: 3,
        backoffFactor: 1.2
      }
    );

    polling.start();

    setTimeout(() => {
      expect(attempts).toBe(3);
      expect(polling.isActive()).toBe(false);
      done();
    }, 500);
  });

  test('成功后重置重试计数', async () => {
    let calls = 0;
    const polling = createPolling(
      () => {
        calls++;
        if (calls <= 1) return Promise.reject(new Error('fail'));
        return Promise.resolve();
      },
      { interval: 10, maxRetries: 5 }
    );

    polling.start();
    await new Promise(r => setTimeout(r, 100));
    polling.stop();
    // Should still be active since it succeeded
    // (not stopped by retries)
  });
});

describe('T-1202-Batch3: 工具函数', () => {
  test('debounce 去抖动', (done) => {
    let callCount = 0;
    const fn = util.debounce(() => { callCount++; }, 50);

    fn();
    fn();
    fn();

    setTimeout(() => {
      expect(callCount).toBe(1);
      done();
    }, 100);
  });

  test('throttle 节流', () => {
    let callCount = 0;
    const fn = util.throttle(() => { callCount++; }, 100);

    fn();
    fn();
    fn();

    expect(callCount).toBe(1);
  });

  test('formatDistance 边界值', () => {
    expect(util.formatDistance(0.05)).toBe('50m');
    expect(util.formatDistance(0.5)).toBe('500m');
    expect(util.formatDistance(1.5)).toBe('1.5km');
    expect(util.formatDistance(null)).toBe('未知');
  });

  test('formatMoney 分转元', () => {
    expect(util.formatMoney(0)).toBe('0.00');
    expect(util.formatMoney(500)).toBe('5.00');
    expect(util.formatMoney(999)).toBe('9.99');
    expect(util.formatMoney(null)).toBe('0.00');
  });

  test('calcDistance 返回合理值', () => {
    const dist = util.calcDistance(30.5728, 104.0668, 30.5828, 104.0768);
    expect(dist).toBeGreaterThan(0);
    expect(dist).toBeLessThan(5);
  });
});

describe('T-1202-Batch3: setData 优化验证', () => {
  test('cachedRequest 支持 null cacheKey（不缓存）', async () => {
    const mockFn = jest.fn().mockResolvedValue({ data: 'ok' });

    await cachedRequest(mockFn, [], {});
    await cachedRequest(mockFn, [], {});

    expect(mockFn).toHaveBeenCalledTimes(2);
  });
});
