/**
 * 天链V3 E2E - 用户管理流程
 *
 * 覆盖: 用户列表、新增用户、编辑用户、删除用户、角色筛选、状态管理
 */
import { test, expect } from '@playwright/test';
import { UsersPage } from './pages';
import { setupAuth, waitForTable } from './fixtures/auth.fixture';

test.describe('用户管理 (Users)', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  // ========== 用户列表 ==========
  test('用户列表页应正常加载', async ({ page }) => {
    const usersPage = new UsersPage(page);
    await usersPage.goto();
    await waitForTable(page);

    await expect(usersPage.table).toBeVisible();
  });

  // ========== 新增用户 ==========
  test('新增用户弹窗打开和关闭', async ({ page }) => {
    const usersPage = new UsersPage(page);
    await usersPage.goto();
    await waitForTable(page);

    const addBtn = usersPage.addButton;
    if (await addBtn.isVisible()) {
      await addBtn.click();
      await page.waitForTimeout(500);

      await expect(usersPage.modal).toBeVisible();

      // 关闭弹窗
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
      await expect(usersPage.modal).not.toBeVisible();
    }
  });

  test('新增用户：填写表单并提交', async ({ page }) => {
    const usersPage = new UsersPage(page);
    await usersPage.goto();
    await waitForTable(page);

    const addBtn = usersPage.addButton;
    if (await addBtn.isVisible()) {
      await addBtn.click();
      await page.waitForTimeout(500);

      const modal = usersPage.modal;
      const ts = Date.now();

      // 填写用户名
      const usernameInput = modal.locator('input[id="username"]').or(modal.locator('input').filter({ hasText: '' }).first());
      if (await usernameInput.isVisible()) {
        await usernameInput.fill(`e2e_user_${ts}`);
      }

      // 填写其他字段
      const inputs = modal.locator('input:not([type="hidden"])');
      const inputCount = await inputs.count();
      for (let i = 0; i < inputCount; i++) {
        const input = inputs.nth(i);
        const placeholder = await input.getAttribute('placeholder');
        if (placeholder?.includes('密码')) {
          await input.fill('Test@123456');
        } else if (placeholder?.includes('邮箱')) {
          await input.fill(`e2e_${ts}@test.com`);
        } else if (placeholder?.includes('手机') || placeholder?.includes('电话')) {
          await input.fill('13800138000');
        }
      }

      // 选择角色
      const roleSelect = modal.locator('.ant-select').filter({ hasText: /角色/ });
      if (await roleSelect.isVisible()) {
        await roleSelect.click();
        await page.waitForTimeout(300);
        const option = page.locator('.ant-select-item-option').first();
        if (await option.isVisible()) {
          await option.click();
        }
        await page.waitForTimeout(300);
      }

      // 提交
      const submitBtn = modal.locator('button').filter({ hasText: /确 定|提交|保存/ }).first();
      if (await submitBtn.isVisible()) {
        await submitBtn.click();
        await page.waitForTimeout(2000);
      }
    }
  });

  // ========== 编辑用户 ==========
  test('编辑用户可打开弹窗', async ({ page }) => {
    const usersPage = new UsersPage(page);
    await usersPage.goto();
    await waitForTable(page);

    const editBtn = usersPage.table.locator('button').filter({ hasText: /编辑/ }).first();
    if (await editBtn.isVisible()) {
      await editBtn.click();
      await page.waitForTimeout(500);

      await expect(usersPage.modal).toBeVisible();

      await page.keyboard.press('Escape');
    }
  });

  // ========== 删除用户 ==========
  test('删除用户应弹出确认框', async ({ page }) => {
    const usersPage = new UsersPage(page);
    await usersPage.goto();
    await waitForTable(page);

    const deleteBtn = usersPage.table.locator('button').filter({ hasText: /删除/ }).first();
    if (await deleteBtn.isVisible()) {
      await deleteBtn.click();
      await page.waitForTimeout(500);

      const confirmDialog = page.locator('.ant-popconfirm');
      await expect(confirmDialog).toBeVisible({ timeout: 3000 });

      // 取消
      const cancelBtn = confirmDialog.locator('button').filter({ hasText: /取消/ });
      if (await cancelBtn.isVisible()) {
        await cancelBtn.click();
      }
    }
  });

  // ========== 搜索 ==========
  test('搜索用户', async ({ page }) => {
    const usersPage = new UsersPage(page);
    await usersPage.goto();
    await waitForTable(page);

    const searchInput = page.locator('input[placeholder*="搜索"]');
    if (await searchInput.isVisible()) {
      await searchInput.fill('admin');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(800);
    }
    await expect(usersPage.table).toBeVisible();
  });

  // ========== 角色筛选 ==========
  test('角色筛选', async ({ page }) => {
    const usersPage = new UsersPage(page);
    await usersPage.goto();
    await waitForTable(page);

    const roleSelect = page.locator('.ant-select').filter({ hasText: /角色/ });
    if (await roleSelect.isVisible()) {
      await roleSelect.click();
      await page.waitForTimeout(300);

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

  // ========== 状态筛选 ==========
  test('用户状态筛选', async ({ page }) => {
    const usersPage = new UsersPage(page);
    await usersPage.goto();
    await waitForTable(page);

    const statusSelect = page.locator('.ant-select').filter({ hasText: /状态/ });
    if (await statusSelect.isVisible()) {
      await statusSelect.click();
      await page.waitForTimeout(300);

      const dropdown = page.locator('.ant-select-dropdown');
      if (await dropdown.isVisible({ timeout: 2000 })) {
        const activeOption = dropdown.locator('.ant-select-item-option').filter({ hasText: /启用|active/ });
        if (await activeOption.isVisible()) {
          await activeOption.click();
          await page.waitForTimeout(500);
        }
      }
    }
  });

  // ========== 表格列检查 ==========
  test('用户表格应包含核心列', async ({ page }) => {
    const usersPage = new UsersPage(page);
    await usersPage.goto();
    await waitForTable(page);

    const headerTexts = await usersPage.table.locator('th').allTextContents();
    const expectedCols = ['用户名', '角色', '状态'];
    for (const col of expectedCols) {
      const found = headerTexts.some((t: string) => t.includes(col));
      expect(found).toBeTruthy();
    }
  });

  // ========== 刷新 ==========
  test('刷新按钮应重新加载', async ({ page }) => {
    const usersPage = new UsersPage(page);
    await usersPage.goto();
    await waitForTable(page);

    const refreshBtn = page.locator('button').filter({ hasText: /刷新/ });
    if (await refreshBtn.isVisible()) {
      await refreshBtn.click();
      await page.waitForTimeout(1000);
    }
    await expect(usersPage.table).toBeVisible();
  });
});