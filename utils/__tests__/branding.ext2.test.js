// utils/__tests__/branding.ext2.test.js — F1235 覆盖缺口闭合
// 目标(branchMap定法, 全局跑分摊值失真后局部实跑定基线):
//   branding.js b17 L118 (cached.data||null 的 null 兜底臂) — 94→100
//   branding.js b18 L134 (ttl||300000 兜底臂) — 顺带闭合
//   branding.js b23 L160 (lazyConfig.CACHE_TTL.TENANT_BRANDING||300000 第三臂兜底) — CONFIG 空对象走默认
//   polling.js b8  L50  (execute 时已 inactive 的守卫臂)
//   cache.js  b12 L117 (t.unref 可选链 falsy 臂) — unref 为 undefined 时跳过
// 手法: doMock 双 mock 缺省臂 + 受控 start/stop 顺序 + unref-less setTimeout stub

const {
  TENANT_BRANDING_CACHE_KEY,
  getCachedTenantBranding,
  cacheTenantBranding
} = require('../branding');

describe('branding.ext2 — F1235 缺口闭合', () => {
  describe('getCachedTenantBranding b17: cached.data 为空走 || null', () => {
    let storage;
    beforeEach(() => {
      storage = {};
      global.wx = {
        setStorageSync: jest.fn((k, v) => { storage[k] = v; }),
        getStorageSync: jest.fn((k) => storage[k] || '')
      };
    });
    afterEach(() => { delete global.wx; });

    it('缓存对象 data 缺失时返回 null (L118 || null 兜底)', () => {
      // 直接注入 data 缺失形态: cacheTenantBranding 总是写 data 字段,
      // 但 storage 可能被其他页面覆写为 {cachedAt, expiredAt} 无 data 形态
      storage[TENANT_BRANDING_CACHE_KEY] = {
        cachedAt: Date.now(),
        expiredAt: Date.now() + 60000
        // 无 data 字段 → undefined → falsy → || null 臂
      };
      expect(getCachedTenantBranding()).toBeNull();
    });

    it('b18: cacheTenantBranding 无 ttl 参数走 || 300000 默认', () => {
      const branding = { operator_name: 'X', theme_color: '#112233', source: 'operator' };
      cacheTenantBranding(branding); // 不传 ttl
      const written = storage[TENANT_BRANDING_CACHE_KEY];
      // expiredAt - cachedAt ≈ 300000 (兜底值), 允许 1s 时钟容差
      const delta = written.expiredAt - written.cachedAt;
      expect(delta).toBeGreaterThanOrEqual(299000);
      expect(delta).toBeLessThanOrEqual(301000);
      // round-trip 仍可用
      expect(getCachedTenantBranding()).toEqual(branding);
    });
  });

  describe('loadAndApplyTenantBranding b23: CACHE_TTL 空对象走默认', () => {
    let setNavColorSpy;

    beforeEach(() => {
      global.wx = {
        setStorageSync: jest.fn(),
        getStorageSync: jest.fn(() => '')
      };
      // applyBrandingToApp 依赖 wx.setNavigationBarColor — spy 住防 ReferenceError
      setNavColorSpy = jest.fn();
      global.wx.setNavigationBarColor = setNavColorSpy;
    });
    afterEach(() => { delete global.wx; });

    it('config.CACHE_TTL 为空对象时 ttl 走 || 300000 (L160 第三臂)', async () => {
      jest.resetModules();
      jest.doMock('../../services/api', () => ({
        getTenantBranding: jest.fn().mockResolvedValue({
          data: { operator_name: '默认租户', theme_color: '#336699', source: 'operator' }
        })
      }));
      // 关键: CACHE_TTL 存在但无 TENANT_BRANDING 键 → 第三臂
      jest.doMock('../../config/index', () => ({ CACHE_TTL: {} }));
      const brandingMod = require('../branding');      const result = await brandingMod.loadAndApplyTenantBranding('t-default');
      expect(result).not.toBeNull();
      expect(result.operatorName).toBe('默认租户');
    });
  });

  describe('polling.ext — execute 时已 inactive (b8 L50)', () => {
    it('stop 后待执行回调不再执行 fn (L50 !active 守卫臂)', async () => {
      const { createPolling } = require('../polling');
      const fn = jest.fn().mockResolvedValue();
      const capturedTimers = [];
      const origSetTimeout = global.setTimeout;

      // 受控 setTimeout: 捕获回调不真正入队, 手动触发
      global.setTimeout = jest.fn((cb, ms) => {
        capturedTimers.push({ cb, ms });
        return capturedTimers.length;
      });
      try {
        const polling = createPolling(fn, { interval: 1000 });
        polling.start();
        // start 同步调 execute → fn 微任务; scheduleNext 在 await fn() 之后才 setTimeout
        await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
        polling.stop(); // active=false
        expect(polling.isActive()).toBe(false);
        expect(capturedTimers.length).toBeGreaterThanOrEqual(1);
        // 手动触发捕获的调度回调 (等价于真实场景中已入队 timer 在 stop 之后到期):
        // 回调链里 scheduleNext→execute 检查 !active → return, fn 不再增长
        for (const t of capturedTimers) t.cb();
        await Promise.resolve(); await Promise.resolve();
        // 仅 start 时的首次 execute, 守卫臂拦截后续
        expect(fn).toHaveBeenCalledTimes(1);
      } finally {
        global.setTimeout = origSetTimeout;
      }
    });
  });

  describe('cache.ext5 — b12 L117 if(t) alternate 臂 (setTimeout 返回 falsy)', () => {
    it('setTimeout 返回 undefined 时跳过 unref 不抛错 (小程序环境形态)', () => {
      const origSetTimeout = global.setTimeout;
      // stub 返回 undefined — 微信小程序 setTimeout 无返回值形态
      global.setTimeout = jest.fn(() => undefined);
      try {
        const { LRUCache } = require('../cache');
        const c = new LRUCache(3);
        c.set('k', 'v', 60000);
        // _refreshTimer: const t = undefined → if(t) false 臂 → t.unref?.() 不执行 → 无 TypeError
        expect(c.get('k')).toBe('v');
        expect(c.timers.k).toBeUndefined(); // falsy timer 不入 timers 表
      } finally {
        global.setTimeout = origSetTimeout;
      }
    });

    it('同 key 二次 set 走 _clearTimer(既有真值 timer) 分支 (顺带链路验证)', () => {
      const origSetTimeout = global.setTimeout;
      const origClearTimeout = global.clearTimeout;
      let seq = 0;
      global.setTimeout = jest.fn((cb) => ({ id: ++seq, cb }));
      global.clearTimeout = jest.fn();
      try {
        const { LRUCache } = require('../cache');
        const c = new LRUCache(3);
        c.set('k', 'v1', 60000);
        const firstTimer = c.timers.k;
        expect(firstTimer).toBeDefined();
        c.set('k', 'v2', 60000);
        expect(c.get('k')).toBe('v2');
        expect(global.clearTimeout).toHaveBeenCalledWith(firstTimer);
        expect(c.timers.k).not.toBe(firstTimer);
      } finally {
        global.setTimeout = origSetTimeout;
        global.clearTimeout = origClearTimeout;
      }
    });
  });
});
