/**
 * 天链V3 E2E - 基础验证测试
 *
 * 验证 Playwright 配置是否正常工作
 */
import { test, expect } from '@playwright/test';

test.describe('Playwright 配置验证', () => {
  test('Playwright 应正常运行', async ({ page }) => {
    expect(true).toBe(true);
  });

  test('页面应可访问', async ({ page }) => {
    // 访问登录页（不依赖后端）
    await page.goto('/login');
    
    // 等待页面加载
    await page.waitForLoadState('domcontentloaded');
    
    // 基本检查：页面标题或关键元素
    const title = await page.title();
    expect(title).toBeTruthy();
  });
});