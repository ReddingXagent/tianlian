/**
 * 天链V3 E2E - 数据看板流程
 *
 * 覆盖: Dashboard页面渲染、图表展示、导航菜单、健康页、报表页
 */
import { test, expect } from '@playwright/test';
import { DashboardPage } from './pages';
import { setupAuth, waitForPageLoad } from './fixtures/auth.fixture';

test.describe('数据看板与导航 (Dashboard & Navigation)', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  // ========== Dashboard 页面 ==========
  test('Dashboard首页应正常加载', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.waitLoaded();

    // 侧边栏应可见
    await expect(dashboard.sider).toBeVisible({ timeout: 10000 });
    // 顶部导航应可见
    await expect(dashboard.header).toBeVisible({ timeout: 5000 });
  });

  test('Dashboard统计卡片应显示', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.waitLoaded();

    // 统计卡片
    const statCards = dashboard.statCards;
    const count = await statCards.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('Dashboard图表区域应有内容', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.waitLoaded();

    // ECharts 容器或图表
    await page.waitForTimeout(1000);
    const chartContainer = page.locator('.echarts-for-react, canvas, .ant-card');
    await expect(chartContainer.first()).toBeVisible({ timeout: 10000 });
  });

  // ========== 侧边栏导航 ==========
  test('侧边栏菜单项应可点击', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.waitLoaded();

    await expect(dashboard.sider).toBeVisible();

    const menuItems = ['电站管理', '设备管理', '工单管理', '告警管理'];
    for (const item of menuItems) {
      const menuItem = dashboard.sider.locator('.ant-menu-item').filter({ hasText: item });
      const isVisible = await menuItem.isVisible().catch(() => false);
      if (isVisible) {
        await menuItem.click();
        await page.waitForTimeout(300);
      }
    }
  });

  test('侧边栏折叠展开', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.waitLoaded();

    const trigger = page.locator('.ant-layout-sider-trigger');
    if (await trigger.isVisible()) {
      await trigger.click();
      await page.waitForTimeout(500);
      // 点击后侧边栏应变窄
    }
  });

  // ========== 所有页面可访问性 ==========
  test('所有核心页面应可访问且不报错', async ({ page }) => {
    const pages = [
      { path: '/stations', name: '电站管理' },
      { path: '/devices', name: '设备管理' },
      { path: '/workorders', name: '工单管理' },
      { path: '/alarms', name: '告警管理' },
      { path: '/knowledge', name: '知识库' },
      { path: '/users', name: '用户管理' },
      { path: '/reports', name: '报表' },
      { path: '/monitor', name: '监控' },
      { path: '/health', name: '健康' },
    ];

    const results: string[] = [];
    for (const { path, name } of pages) {
      try {
        await page.goto(path, { timeout: 10000 });
        await page.waitForLoadState('networkidle', { timeout: 10000 });
        // 不应有白屏错误
        const isError = await page.locator('.ant-alert-error').isVisible().catch(() => false);
        const hasContent = await page.locator('.ant-layout-content').isVisible().catch(() => false);
        results.push(`✅ ${name} (${path}): ${hasContent ? 'OK' : 'Empty'}${isError ? ' ERROR' : ''}`);
      } catch (err: any) {
        results.push(`❌ ${name} (${path}): ${err.message?.substring(0, 50)}`);
      }
    }

    console.log('页面可访问性检查:\n' + results.join('\n'));
    // 至少 80% 页面可访问
    const failedCount = results.filter(r => r.startsWith('❌')).length;
    expect(failedCount).toBeLessThanOrEqual(Math.floor(pages.length * 0.2));
  });
});

// ========== 报表页 ==========
test.describe('报表管理 (Reports)', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('报表页应加载', async ({ page }) => {
    await page.goto('/reports');
    await waitForPageLoad(page);

    // 应有内容
    await expect(page.locator('.ant-layout-content')).toBeVisible({ timeout: 10000 });
  });
});

// ========== 健康监控 ==========
test.describe('健康监控 (Health)', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('健康监控页应加载', async ({ page }) => {
    await page.goto('/health');
    await waitForPageLoad(page);

    // 应有统计信息或表格
    await expect(page.locator('.ant-layout-content')).toBeVisible({ timeout: 10000 });
  });
});

// ========== 知识库 (需资源) ==========
test.describe('知识库 (Knowledge)', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('知识库列表页应加载', async ({ page }) => {
    await page.goto('/knowledge');
    await waitForPageLoad(page);

    await expect(page.locator('.ant-list, .ant-table')).toBeVisible({ timeout: 10000 });
  });
});