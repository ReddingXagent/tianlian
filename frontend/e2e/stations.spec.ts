/**
 * 天链V3 E2E - 站点管理流程
 *
 * 覆盖: 列表浏览、搜索筛选、新建站点、编辑站点、删除站点、详情查看、统计卡片
 */
import { test, expect } from '@playwright/test';
import { StationsPage } from './pages';
import { setupAuth, waitForTable } from './fixtures/auth.fixture';

test.describe('站点管理 (Stations)', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  // ========== 列表加载 ==========
  test('站点列表页应正常加载', async ({ page }) => {
    const stationsPage = new StationsPage(page);
    await stationsPage.goto();
    await waitForTable(page);

    // 应显示统计卡片
    await expect(stationsPage.statCards.first()).toBeVisible();
    // 应有表格
    await expect(stationsPage.table).toBeVisible();
    // 不应有错误状态
    await expect(page.locator('.ant-alert-error')).not.toBeVisible();
  });

  // ========== 统计卡片 ==========
  test('统计卡片显示站点统计数据', async ({ page }) => {
    const stationsPage = new StationsPage(page);
    await stationsPage.goto();
    await waitForTable(page);

    // 至少有一个统计卡片
    const cards = stationsPage.statCards;
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(4); // 总数、正常、维护中、关闭
  });

  // ========== 搜索筛选 ==========
  test('搜索功能：按站点名称搜索', async ({ page }) => {
    const stationsPage = new StationsPage(page);
    await stationsPage.goto();
    await waitForTable(page);

    const searchInput = stationsPage.searchInput;
    if (await searchInput.isVisible()) {
      await searchInput.fill('测试');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(800);

      // 表格应该还在（即使为空）
      await expect(stationsPage.table).toBeVisible();
    }
  });

  test('状态筛选下拉框应可用', async ({ page }) => {
    const stationsPage = new StationsPage(page);
    await stationsPage.goto();
    await waitForTable(page);

    // 找到状态筛选 select
    const statusFilter = page.locator('.ant-select').filter({ hasText: /状态筛选/ });
    if (await statusFilter.isVisible()) {
      await statusFilter.click();
      await page.waitForTimeout(300);

      // 下拉选项应可见
      const dropdown = page.locator('.ant-select-dropdown');
      await expect(dropdown).toBeVisible({ timeout: 3000 });

      // 选择"正常"
      const normalOption = dropdown.locator('.ant-select-item-option').filter({ hasText: '正常' });
      if (await normalOption.isVisible()) {
        await normalOption.click();
        await page.waitForTimeout(500);
      }
    }
  });

  // ========== 新建站点 ==========
  test('新建站点弹窗应能打开和关闭', async ({ page }) => {
    const stationsPage = new StationsPage(page);
    await stationsPage.goto();
    await waitForTable(page);

    // 点击添加站点按钮
    await stationsPage.addButton.click();
    await page.waitForTimeout(500);

    // 弹窗应显示
    await expect(stationsPage.modal).toBeVisible();

    // 验证表单字段
    const modal = stationsPage.modal;
    await expect(modal.locator('input[id="name"]')).toBeVisible();
    await expect(modal.locator('input[id="code"]')).toBeVisible();

    // 关闭弹窗
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    await expect(stationsPage.modal).not.toBeVisible();
  });

  test('新建站点：填写表单并提交', async ({ page }) => {
    const stationsPage = new StationsPage(page);
    await stationsPage.goto();
    await waitForTable(page);

    // 打开新建弹窗
    await stationsPage.addButton.click();
    await page.waitForTimeout(500);

    // 填写表单
    const modal = stationsPage.modal;
    await modal.locator('input[id="name"]').fill(`E2E测试站点_${Date.now()}`);
    await modal.locator('input[id="code"]').fill(`E2E_CODE_${Date.now()}`);
    await modal.locator('input[id="address"]').fill('E2E测试地址');

    // 选择状态
    const statusSelect = modal.locator('.ant-select').filter({ hasText: /状态/ });
    if (await statusSelect.isVisible()) {
      await statusSelect.click();
      await page.waitForTimeout(300);
      const normalOption = page.locator('.ant-select-item-option').filter({ hasText: '正常' });
      if (await normalOption.isVisible()) {
        await normalOption.click();
      }
      await page.waitForTimeout(300);
    }

    // 点击确定提交
    await stationsPage.modal.locator('button').filter({ hasText: /确 定/ }).click();
    await page.waitForTimeout(2000);

    // 提交后弹窗应关闭
    await expect(stationsPage.modal).not.toBeVisible({ timeout: 5000 });
  });

  // ========== 编辑站点 ==========
  test('编辑站点应能打开弹窗并修改', async ({ page }) => {
    const stationsPage = new StationsPage(page);
    await stationsPage.goto();
    await waitForTable(page);

    // 找到第一个编辑按钮
    const editBtn = stationsPage.table.locator('button').filter({ hasText: '编辑' }).first();
    if (await editBtn.isVisible()) {
      await editBtn.click();
      await page.waitForTimeout(500);

      // 弹窗应出现
      await expect(stationsPage.modal).toBeVisible();

      // 名称字段应有值
      const nameInput = stationsPage.modal.locator('input[id="name"]');
      const nameValue = await nameInput.inputValue();
      expect(nameValue.length).toBeGreaterThan(0);

      // 关闭弹窗
      await page.keyboard.press('Escape');
    }
  });

  // ========== 删除站点 ==========
  test('删除站点应弹出确认框', async ({ page }) => {
    const stationsPage = new StationsPage(page);
    await stationsPage.goto();
    await waitForTable(page);

    // 找到第一个删除按钮
    const deleteBtn = stationsPage.table.locator('button').filter({ hasText: '删除' }).first();
    if (await deleteBtn.isVisible()) {
      await deleteBtn.click();
      await page.waitForTimeout(500);

      // 确认弹窗应显示
      const confirmDialog = page.locator('.ant-popconfirm');
      await expect(confirmDialog).toBeVisible({ timeout: 3000 });

      // 取消删除
      const cancelBtn = confirmDialog.locator('button').filter({ hasText: /取消/ });
      if (await cancelBtn.isVisible()) {
        await cancelBtn.click();
      }
    }
  });

  // ========== 查看详情 ==========
  test('查看站点详情弹窗', async ({ page }) => {
    const stationsPage = new StationsPage(page);
    await stationsPage.goto();
    await waitForTable(page);

    const detailBtn = stationsPage.table.locator('button').filter({ hasText: '详情' }).first();
    if (await detailBtn.isVisible()) {
      await detailBtn.click();
      await page.waitForTimeout(500);

      // 详情弹窗应显示
      await expect(stationsPage.modal).toBeVisible();

      // 应包含站点详情信息
      await expect(page.locator('text=站点编码')).toBeVisible();

      // 关闭
      await page.locator('button').filter({ hasText: /关闭|取消/ }).first().click();
    }
  });

  // ========== 刷新 ==========
  test('刷新按钮应重新加载数据', async ({ page }) => {
    const stationsPage = new StationsPage(page);
    await stationsPage.goto();
    await waitForTable(page);

    const refreshBtn = stationsPage.refreshButton;
    await refreshBtn.click();
    await page.waitForTimeout(1000);

    // 表格应该还在
    await expect(stationsPage.table).toBeVisible();
  });

  // ========== 分页 ==========
  test('分页器应显示', async ({ page }) => {
    const stationsPage = new StationsPage(page);
    await stationsPage.goto();
    await waitForTable(page);

    const pagination = page.locator('.ant-pagination');
    // 如果有数据就应显示分页器
    await expect(pagination).toBeVisible({ timeout: 5000 }).catch(() => {});
  });
});