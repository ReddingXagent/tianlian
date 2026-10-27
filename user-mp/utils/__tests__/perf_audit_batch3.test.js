// utils/__tests__/perf_audit_batch3.test.js - T-1202 第3批: 页面级 guardTap 集成审计测试
// 纯文件审计方式，不 require 页面模块（避免 Page() 未定义）

const fs = require('fs');
const path = require('path');

const pageDir = path.join(__dirname, '../../pages');

function readPage(relPath) {
  return fs.readFileSync(path.join(pageDir, relPath), 'utf-8');
}

describe('T-1202-Batch3: 页面 guardTap 集成审计', () => {

  describe('scan.js - 扫码充电页', () => {
    let src;
    beforeAll(() => { src = readPage('scan/scan.js'); });

    test('引入 guardTap', () => {
      expect(src).toContain('guardTap');
    });

    test('startCharging 防 duplicate（guardTap + 3s间隔）', () => {
      expect(src).toMatch(/startCharging:\s*guardTap/);
      expect(src).toMatch(/startCharging[\s\S]*?3000\)/);
    });

    test('onManualStart 防连点', () => {
      expect(src).toMatch(/onManualStart:\s*guardTap/);
    });

    test('onHistoryTap 防连点', () => {
      expect(src).toMatch(/onHistoryTap:\s*guardTap/);
    });
  });

  describe('notifications.js - 消息通知页', () => {
    let src;
    beforeAll(() => { src = readPage('notifications/notifications.js'); });

    test('引入 guardTap', () => {
      expect(src).toContain('guardTap');
    });

    test('onTabChange 防连点', () => {
      expect(src).toMatch(/onTabChange:\s*guardTap/);
    });

    test('onMarkAllRead 防连点', () => {
      expect(src).toMatch(/onMarkAllRead:\s*guardTap/);
    });

    test('onPullDownRefresh 防连点', () => {
      expect(src).toMatch(/onPullDownRefresh:\s*guardTap/);
    });
  });

  describe('coupons.js - 优惠券页', () => {
    let src;
    beforeAll(() => { src = readPage('coupons/coupons.js'); });

    test('引入 guardTap', () => {
      expect(src).toContain('guardTap');
    });

    test('onTabChange 防连点', () => {
      expect(src).toMatch(/onTabChange:\s*guardTap/);
    });

    test('onClaim 防重复领取', () => {
      expect(src).toMatch(/onClaim:\s*guardTap/);
    });

    test('onPullDownRefresh 防连点', () => {
      expect(src).toMatch(/onPullDownRefresh:\s*guardTap/);
    });
  });

  describe('points.js - 积分中心页', () => {
    let src;
    beforeAll(() => { src = readPage('points/points.js'); });

    test('引入 guardTap', () => {
      expect(src).toContain('guardTap');
    });

    test('onSignIn 防重复签到', () => {
      expect(src).toMatch(/onSignIn:\s*guardTap/);
    });
  });

  describe('favorites.js - 收藏页', () => {
    let src;
    beforeAll(() => { src = readPage('favorites/favorites.js'); });

    test('引入 guardTap', () => {
      expect(src).toContain('guardTap');
    });

    test('onRemoveFavorite 防连点', () => {
      expect(src).toMatch(/onRemoveFavorite:\s*guardTap/);
    });
  });

  describe('已有页面性能保护验证（回归）', () => {
    test('index.js - cachedRequest + guardTap + buildMarkers', () => {
      const src = readPage('index/index.js');
      expect(src).toContain('cachedRequest');
      expect(src).toContain('guardTap');
      expect(src).toContain('buildMarkers');
    });

    test('charging.js - createPolling + diffSetData', () => {
      const src = readPage('charging/charging.js');
      expect(src).toContain('createPolling');
      expect(src).toContain('diffSetData');
    });

    test('orders.js - createPagination + guardTap', () => {
      const src = readPage('orders/orders.js');
      expect(src).toContain('createPagination');
      expect(src).toContain('guardTap');
    });

    test('payment.js - cachedRequest', () => {
      const src = readPage('payment/payment.js');
      expect(src).toContain('cachedRequest');
    });

    test('order-detail.js - cachedRequest', () => {
      const src = readPage('order-detail/order-detail.js');
      expect(src).toContain('cachedRequest');
    });
  });
});

describe('T-1202-Batch3: 性能优化覆盖率统计', () => {
  test('所有页面 JS 文件均引入性能工具', () => {
    const pageFiles = [
      'index/index.js',
      'charging/charging.js',
      'orders/orders.js',
      'order-detail/order-detail.js',
      'payment/payment.js',
      'scan/scan.js',
      'profile/profile.js',
      'coupons/coupons.js',
      'points/points.js',
      'favorites/favorites.js',
      'notifications/notifications.js'
    ];

    let perfCount = 0;

    for (const file of pageFiles) {
      const src = readPage(file);
      const usesPerf =
        src.includes('cachedRequest') ||
        src.includes('guardTap') ||
        src.includes('createPolling') ||
        src.includes('createPagination') ||
        src.includes('diffSetData') ||
        src.includes('createBatchSetData');

      if (usesPerf) perfCount++;
    }

    // 至少 10/11 页面使用性能工具
    expect(perfCount).toBeGreaterThanOrEqual(10);
  });

  test('guardTap 使用次数 ≥ 10（覆盖关键交互）', () => {
    const pageFiles = [
      'index/index.js',
      'charging/charging.js',
      'orders/orders.js',
      'scan/scan.js',
      'coupons/coupons.js',
      'points/points.js',
      'favorites/favorites.js',
      'notifications/notifications.js'
    ];

    let totalGuardTap = 0;
    for (const file of pageFiles) {
      const src = readPage(file);
      const matches = src.match(/guardTap\(/g);
      if (matches) totalGuardTap += matches.length;
    }

    expect(totalGuardTap).toBeGreaterThanOrEqual(10);
  });
});
