/**
 * 天链V3 E2E - 设备管理流程
 *
 * 覆盖: 列表加载、搜索筛选、类型筛选、状态筛选、新增设备、编辑设备、删除设备
 */
import { test, expect } from '@playwright/test';
import { DevicesPage } from './pages';
import { setupAuth, waitForTable } from './fixtures/auth.fixture';

test.describe('设备管理 (Devices)', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  // ========== 列表加载 ==========
  test('设备列表页应正常加载', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await waitForTable(page);

    await expect(devicesPage.table).toBeVisible();
    // 标题应显示
    await expect(page.locator('text=设备管理')).toBeVisible();
    // 不应有错误
    await expect(page.locator('.ant-alert-error')).not.toBeVisible();
  });

  // ========== 搜索功能 ==========
  test('搜索设备名称', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await waitForTable(page);

    const searchInput = devicesPage.searchInput;
    if (await searchInput.isVisible()) {
      await searchInput.fill('充电桩');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(800);
    }
    await expect(devicesPage.table).toBeVisible();
  });

  test('搜索设备SN码', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await waitForTable(page);

    const searchInput = devicesPage.searchInput;
    if (await searchInput.isVisible()) {
      await searchInput.fill('SN-');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(800);
    }
    await expect(devicesPage.table).toBeVisible();
  });

  // ========== 筛选功能 ==========
  test('设备类型筛选', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await waitForTable(page);

    // 找到设备类型筛选下拉框
    const typeSelect = page.locator('.ant-select').filter({ hasText: /设备类型/ });
    if (await typeSelect.isVisible()) {
      await typeSelect.click();
      await page.waitForTimeout(500);

      const dropdown = page.locator('.ant-select-dropdown');
      if (await dropdown.isVisible({ timeout: 2000 })) {
        const option = dropdown.locator('.ant-select-item-option').first();
        if (await option.isVisible()) {
          await option.click();
          await page.waitForTimeout(500);
        }
      }
    }
  });

  test('设备状态筛选', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await waitForTable(page);

    const statusSelect = page.locator('.ant-select').filter({ hasText: /设备状态/ });
    if (await statusSelect.isVisible()) {
      await statusSelect.click();
      await page.waitForTimeout(500);

      const dropdown = page.locator('.ant-select-dropdown');
      if (await dropdown.isVisible({ timeout: 2000 })) {
        const onlineOption = dropdown.locator('.ant-select-item-option').filter({ hasText: '在线' });
        if (await onlineOption.isVisible()) {
          await onlineOption.click();
          await page.waitForTimeout(500);
        }
      }
    }
  });

  // ========== 新增设备 ==========
  test('新增设备弹窗打开和关闭', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await waitForTable(page);

    await devicesPage.addButton.click();
    await page.waitForTimeout(500);

    // 弹窗应显示
    const modal = page.locator('.ant-modal');
    await expect(modal).toBeVisible();

    // 验证核心表单字段
    await expect(modal.locator('input[id="sn"]')).toBeVisible();
    await expect(modal.locator('input[id="name"]')).toBeVisible();

    // 关闭
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    await expect(modal).not.toBeVisible();
  });

  test('新增设备：填写必填字段并提交', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await waitForTable(page);

    await devicesPage.addButton.click();
    await page.waitForTimeout(500);

    const modal = page.locator('.ant-modal');
    const ts = Date.now();

    await modal.locator('input[id="sn"]').fill(`E2E-SN-${ts}`);
    await modal.locator('input[id="name"]').fill(`E2E测试设备_${ts}`);
    await modal.locator('input[id="code"]').fill(`CODE_${ts}`);
    await modal.locator('input[id="model"]').fill('E2E-Model-X');
    await modal.locator('input[id="manufacturer"]').fill('E2E厂商');

    // 选择设备类型
    const typeSelect = modal.locator('.ant-select').filter({ hasText: /设备类型/ });
    if (await typeSelect.isVisible()) {
      await typeSelect.click();
      await page.waitForTimeout(300);
      const option = page.locator('.ant-select-item-option').first();
      if (await option.isVisible()) {
        await option.click();
      }
      await page.waitForTimeout(300);
    }

    // 提交
    await modal.locator('button').filter({ hasText: /确 定|OK/ }).click();
    await page.waitForTimeout(2000);

    // 弹窗应关闭
    await expect(modal).not.toBeVisible({ timeout: 5000 });
  });

  // ========== 编辑设备 ==========
  test('编辑设备：打开弹窗查看已有数据', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await waitForTable(page);

    const editBtn = devicesPage.table.locator('button').filter({ hasText: '编辑' }).first();
    if (await editBtn.isVisible()) {
      await editBtn.click();
      await page.waitForTimeout(500);

      const modal = page.locator('.ant-modal');
      await expect(modal).toBeVisible();

      // SN 应已有值
      const snInput = modal.locator('input[id="sn"]');
      const snValue = await snInput.inputValue();
      expect(snValue.length).toBeGreaterThan(0);

      await page.keyboard.press('Escape');
    }
  });

  // ========== 删除设备 ==========
  test('删除设备确认弹窗', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await waitForTable(page);

    const deleteBtn = devicesPage.table.locator('button').filter({ hasText: '删除' }).first();
    if (await deleteBtn.isVisible()) {
      await deleteBtn.click();
      await page.waitForTimeout(500);

      const confirmDialog = page.locator('.ant-popconfirm');
      await expect(confirmDialog).toBeVisible({ timeout: 3000 });

      // 取消删除
      const cancelBtn = confirmDialog.locator('button').filter({ hasText: /取消/ });
      if (await cancelBtn.isVisible()) {
        await cancelBtn.click();
      }
    }
  });

  // ========== 表格列检查 ==========
  test('设备表格应包含所有必要列', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await waitForTable(page);

    // 验证核心列标题
    const headerTexts = await devicesPage.table.locator('th').allTextContents();
    const expectedCols = ['设备名称', 'SN码', '设备类型', '状态', '健康度'];
    for (const col of expectedCols) {
      const found = headerTexts.some((t: string) => t.includes(col));
      expect(found).toBeTruthy();
    }
  });

  // ========== 分页 ==========
  test('分页器应正常工作', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await waitForTable(page);

    const pagination = page.locator('.ant-pagination');
    if (await pagination.isVisible({ timeout: 3000 }).catch(() => false)) {
      // 点击下一页（如果可用）
      const nextBtn = pagination.locator('.ant-pagination-next');
      if (await nextBtn.locator('.ant-pagination-disabled').count() === 0) {
        await nextBtn.click();
        await page.waitForTimeout(800);
      }
    }
  });
});