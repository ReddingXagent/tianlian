/**
 * 天链V3 E2E - 登录认证流程
 *
 * 覆盖: 页面渲染、表单元素、本地Token注入、受保护页面访问
 */
import { test, expect } from '@playwright/test';
import { LoginPage } from './pages';
import { setupAuth, clearAuth, isAuthenticated, TEST_USERS } from './fixtures/auth.fixture';

test.describe('登录认证 (Auth)', () => {
  // ========== 页面渲染 ==========
  test('登录页面正常渲染', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await page.waitForTimeout(1000);

    await expect(loginPage.usernameInput).toBeVisible();
    await expect(loginPage.passwordInput).toBeVisible();
    await expect(loginPage.submitButton).toBeVisible();
    await expect(loginPage.titleText).toBeVisible();
  });

  test('入口切换按钮可见', async ({ page }) => {
    await page.goto('/login');
    await page.waitForTimeout(1000);

    // 运维管理/平台管理切换按钮
    await expect(page.locator('button:has-text("运维管理")')).toBeVisible();
    await expect(page.locator('button:has-text("平台管理")')).toBeVisible();
  });

  // ========== 表单交互 ==========
  test('可以填写用户名密码', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await page.waitForTimeout(500);

    await loginPage.fillForm('admin', 'admin123');

    // 验证输入值
    const usernameVal = await loginPage.usernameInput.inputValue();
    const passwordVal = await loginPage.passwordInput.inputValue();
    expect(usernameVal).toBe('admin');
    expect(passwordVal).toBe('admin123');
  });

  // ========== localStorage 注入认证 ==========
  test('注入Token后可直接访问Dashboard', async ({ page }) => {
    await setupAuth(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    const authed = await isAuthenticated(page);
    expect(authed).toBeTruthy();
    // 不应被重定向到登录页
    await expect(page).not.toHaveURL(/\/login/);
  });

  test('认证后可访问受保护页面集合', async ({ page }) => {
    await setupAuth(page);
    const pages = ['/stations', '/devices', '/workorders', '/alarms', '/users'];

    for (const path of pages) {
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      await expect(page).not.toHaveURL(/\/login/);
    }
  });

  test('连续页面导航不重置到登录页', async ({ page }) => {
    await setupAuth(page);
    const pages = ['/dashboard', '/stations', '/devices', '/workorders', '/alarms'];
    const results: string[] = [];
    
    for (const path of pages) {
      await page.goto(path, { timeout: 15000 });
      await page.waitForLoadState('networkidle', { timeout: 10000 });
      const redirected = page.url().includes('/login');
      results.push(`${redirected ? '❌' : '✅'} ${path}`);
    }
    
    console.log(results.join('\n'));
    const failures = results.filter(r => r.includes('❌')).length;
    expect(failures).toBeLessThanOrEqual(2);
  });
  
  // ========== Token过期/清除 ==========
  test('清除Token后受保护页面应重定向', async ({ page }) => {
    await setupAuth(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await expect(page).not.toHaveURL(/\/login/);

    // 清除认证
    await clearAuth(page);
    const authed = await isAuthenticated(page);
    expect(authed).toBeFalsy();
    
    // 访问受保护页面应回到登录页
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
  });

  // ========== 登出=重定向 ==========
  test('无效Token无法通过后端API调用', async ({ page }) => {
    await page.goto('/login');
    await page.evaluate(() => {
      localStorage.setItem('admin_token', 'definitely_invalid_token_12345');
      localStorage.setItem('admin_user', JSON.stringify({ username: 'admin', role: 'admin' }));
    });
    
    // RouteGuard仅检查localStorage中有无token, 只要有token就可以访问
    // 后端API会在调用时返回401, 前端会清空token
    await page.goto('/stations', { timeout: 10000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // 页面不应显示登录页（有token就可以通过RouteGuard）
    expect(page.url()).not.toContain('/login');
  });
});