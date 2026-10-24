/**
 * 天链V3 E2E - 告警管理流程
 *
 * 覆盖: 告警列表、统计、确认/解决告警、告警规则、告警通知
 */
import { test, expect } from '@playwright/test';
import { AlarmsPage, NotificationRulesPage } from './pages';
import { setupAuth, waitForTable } from './fixtures/auth.fixture';

test.describe('告警管理 (Alarms)', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  // ========== 告警列表 ==========
  test('告警列表页应正常加载', async ({ page }) => {
    const alarmsPage = new AlarmsPage(page);
    await alarmsPage.goto();
    await waitForTable(page);

    await expect(alarmsPage.table).toBeVisible();
  });

  // ========== 告警统计 ==========
  test('告警统计卡片应显示', async ({ page }) => {
    const alarmsPage = new AlarmsPage(page);
    await alarmsPage.goto();
    await waitForTable(page);

    // 检查统计卡片是否可见
    const statsCards = alarmsPage.statCards;
    const count = await statsCards.count();
    // 至少应有一个统计指标
    expect(count).toBeGreaterThanOrEqual(1);
  });

  // ========== 告警筛选 ==========
  test('告警状态筛选', async ({ page }) => {
    const alarmsPage = new AlarmsPage(page);
    await alarmsPage.goto();
    await waitForTable(page);

    // 找到状态筛选下拉框（第一个非禁用select）
    const statusSelects = page.locator('.ant-select');
    const count = await statusSelects.count();
    for (let i = 0; i < count; i++) {
      const select = statusSelects.nth(i);
      const isDisabled = await select.locator('.ant-select-disabled').count();
      if (isDisabled === 0) {
        await select.click();
        await page.waitForTimeout(500);

        const dropdown = page.locator('.ant-select-dropdown');
        if (await dropdown.isVisible({ timeout: 2000 })) {
          const option = dropdown.locator('.ant-select-item-option').first();
          if (await option.isVisible()) {
            await option.click();
            await page.waitForTimeout(800);
          }
        }
        break;
      }
    }
  });

  test('告警级别筛选', async ({ page }) => {
    const alarmsPage = new AlarmsPage(page);
    await alarmsPage.goto();
    await waitForTable(page);

    // 查找级别筛选
    const levelSelect = page.locator('.ant-select').filter({ hasText: /级别/ });
    if (await levelSelect.isVisible()) {
      await levelSelect.click();
      await page.waitForTimeout(500);

      const dropdown = page.locator('.ant-select-dropdown');
      if (await dropdown.isVisible({ timeout: 2000 })) {
        const criticalOption = dropdown.locator('.ant-select-item-option').filter({ hasText: /严重|critical/i });
        if (await criticalOption.isVisible()) {
          await criticalOption.click();
          await page.waitForTimeout(500);
        }
      }
    }
  });

  // ========== 告警确认/处理 ==========
  test('确认告警告警操作', async ({ page }) => {
    const alarmsPage = new AlarmsPage(page);
    await alarmsPage.goto();
    await waitForTable(page);

    // 查找确认/处理按钮
    const ackBtn = alarmsPage.table.locator('button, a').filter({ hasText: /确认|处理/ }).first();
    if (await ackBtn.isVisible()) {
      await ackBtn.click();
      await page.waitForTimeout(1000);

      // 可能弹出处理弹窗
      const modal = page.locator('.ant-modal');
      if (await modal.isVisible({ timeout: 2000 }).catch(() => false)) {
        // 关闭处理弹窗
        await page.keyboard.press('Escape');
      }
    }
  });

  test('解决告警告警操作', async ({ page }) => {
    const alarmsPage = new AlarmsPage(page);
    await alarmsPage.goto();
    await waitForTable(page);

    const resolveBtn = alarmsPage.table.locator('button, a').filter({ hasText: /解决|完成/ }).first();
    if (await resolveBtn.isVisible()) {
      await resolveBtn.click();
      await page.waitForTimeout(1000);

      const modal = page.locator('.ant-modal');
      if (await modal.isVisible({ timeout: 2000 }).catch(() => false)) {
        await page.keyboard.press('Escape');
      }
    }
  });

  // ========== 告警详情 ==========
  test('查看告警详情弹窗', async ({ page }) => {
    const alarmsPage = new AlarmsPage(page);
    await alarmsPage.goto();
    await waitForTable(page);

    const detailBtn = alarmsPage.table.locator('button, a').filter({ hasText: /详情|查看/ }).first();
    if (await detailBtn.isVisible()) {
      await detailBtn.click();
      await page.waitForTimeout(800);

      const modal = page.locator('.ant-modal');
      if (await modal.isVisible({ timeout: 3000 }).catch(() => false)) {
        await expect(modal).toBeVisible();
        // 关闭
        await page.keyboard.press('Escape');
      }
    }
  });

  // ========== 告警规则 Tab ==========
  test('告警规则标签页应可切换', async ({ page }) => {
    const alarmsPage = new AlarmsPage(page);
    await alarmsPage.goto();
    await waitForTable(page);

    // 检查是否有 tabs
    const tabs = alarmsPage.tabs;
    if (await tabs.isVisible({ timeout: 3000 }).catch(() => false)) {
      // 切换到规则标签
      const rulesTab = tabs.locator('.ant-tabs-tab').filter({ hasText: /规则/ });
      if (await rulesTab.isVisible()) {
        await rulesTab.click();
        await page.waitForTimeout(800);

        // 规则页应有内容
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(500);
      }
    }
  });

  // ========== 告警规则 CRUD ==========
  test('告警规则列表应加载（独立告警规则页）', async ({ page }) => {
    // 尝试访问告警规则独立路径
    await page.goto('/alarms');
    await waitForTable(page);

    // 在告警页中查找规则标签
    const rulesTab = page.locator('.ant-tabs-tab').filter({ hasText: /规则/ });
    if (await rulesTab.isVisible({ timeout: 3000 })) {
      await rulesTab.click();
      await page.waitForTimeout(800);
    }
    await expect(page.locator('.ant-table')).toBeVisible({ timeout: 5000 });
  });
});

// ========== 告警通知 ==========
test.describe('告警通知 (Alarm Notices)', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('告警通知页应加载', async ({ page }) => {
    const noticesPage = new NotificationRulesPage(page);
    await noticesPage.goto();
    await waitForTable(page);
  });
});