/**
 * 天链V3 E2E - 认证与测试数据 Fixture
 *
 * 提供统一的登录逻辑和测试数据基础
 */
import { Page, BrowserContext } from '@playwright/test';

// ============ 测试用户 ============
export const TEST_USERS = {
  admin: { username: 'admin', password: 'admin123', role: 'admin' },
  operator: { username: 'operator', password: 'operator123', role: 'operator' },
  viewer: { username: 'viewer', password: 'viewer123', role: 'viewer' },
};

// ============ 本地存储键名 ============
const TOKEN_KEY = 'admin_token';
const USER_KEY = 'admin_user';

// ============ 认证辅助函数 ============

/**
 * 通过 localStorage 注入认证信息，绕过登录页面
 */
export async function setupAuth(page: Page, user = TEST_USERS.admin) {
  await page.goto('/login');
  await page.evaluate(
    ({ tokenKey, userKey, token, userData }) => {
      localStorage.setItem(tokenKey, token);
      localStorage.setItem(userKey, JSON.stringify(userData));
    },
    {
      tokenKey: TOKEN_KEY,
      userKey: USER_KEY,
      token: `e2e-token-${user.username}`,
      userData: { username: user.username, role: user.role },
    }
  );
}

/**
 * 通过 UI 真实登录
 */
export async function loginViaUI(page: Page, user = TEST_USERS.admin) {
  await page.goto('/login');
  await page.fill('input[placeholder="请输入用户名"]', user.username);
  await page.fill('input[placeholder="请输入密码"]', user.password);
  await page.click('button[type="submit"]');
  await page.waitForURL(/dashboard/i, { timeout: 15000 });
}

/**
 * 清除认证信息
 */
export async function clearAuth(page: Page) {
  await page.evaluate(({ tokenKey, userKey }) => {
    localStorage.removeItem(tokenKey);
    localStorage.removeItem(userKey);
  }, { tokenKey: TOKEN_KEY, userKey: USER_KEY });
}

/**
 * 获取当前认证状态
 */
export async function isAuthenticated(page: Page): Promise<boolean> {
  const token = await page.evaluate(
    ({ tokenKey }) => localStorage.getItem(tokenKey),
    { tokenKey: TOKEN_KEY }
  );
  return !!token;
}

// ============ 常用操作辅助 ============

/**
 * 等待页面加载（table 出现）
 */
export async function waitForPageLoad(page: Page) {
  await page.waitForLoadState('networkidle');
  // 等待 antd Spin 消失
  await page.waitForSelector('.ant-spin', { state: 'hidden', timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(500);
}

/**
 * 等待表格数据加载
 */
export async function waitForTable(page: Page) {
  await waitForPageLoad(page);
  await page.waitForSelector('.ant-table', { timeout: 10000 });
}

/**
 * 导航到指定页面并等待加载
 */
export async function navigateTo(page: Page, path: string) {
  await page.goto(path);
  await waitForPageLoad(page);
}

/**
 * 点击侧边栏菜单项
 */
export async function clickSidebarMenu(page: Page, menuText: string) {
  // Try multiple selectors to find the menu item
  const menuItem = page.locator('.ant-menu-item, .ant-menu-title-content, a').filter({ hasText: menuText }).first();
  if (await menuItem.isVisible({ timeout: 3000 }).catch(() => false)) {
    await menuItem.click();
    await page.waitForTimeout(500);
  } else {
    // Fallback: try to find any link with the text
    const link = page.locator(`a:has-text("${menuText}")`).first();
    if (await link.isVisible({ timeout: 2000 }).catch(() => false)) {
      await link.click();
      await page.waitForTimeout(500);
    }
  }
  await page.waitForLoadState('networkidle').catch(() => {});
}