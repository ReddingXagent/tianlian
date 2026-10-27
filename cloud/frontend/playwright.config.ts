import { defineConfig, devices } from '@playwright/test';

/**
 * 天链V3 E2E测试配置
 *
 * 特性:
 * - 截图 on failure
 * - 视频录制 (CI环境下)
 * - HTML + JSON 双 Reporter
 * - 合理的超时设置
 * - CI 优化 (retries, workers)
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,

  /* Reporter: HTML (可视化) + JSON (CI解析) */
  reporter: [
    ['html', { open: 'never', outputFolder: 'test-results/html' }],
    ['json', { outputFile: 'test-results/json/results.json' }],
    ['list'],
  ],

  /* 全局超时设置 */
  timeout: 30000,
  expect: {
    timeout: 10000,
  },

  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: process.env.CI ? 'retain-on-failure' : 'off',
  },

  /* 输出目录 */
  outputDir: 'test-results/artifacts',

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },

    // CI中也跑 Firefox 做交叉验证
    ...(process.env.CI ? [{
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    }] : []),
  ],

  /* Dev Server (本地开发模式) */
  ...(process.env.CI ? {} : {
    webServer: {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
  }),
});