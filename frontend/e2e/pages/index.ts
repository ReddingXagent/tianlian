/**
 * 天链V3 E2E - Page Object: 登录页
 */
import { Page } from '@playwright/test';
import { TEST_USERS } from '../fixtures/auth.fixture.js';

export class LoginPage {
  constructor(private page: Page) {}

  get usernameInput() { return this.page.locator('input[placeholder="请输入用户名"]'); }
  get passwordInput() { return this.page.locator('input[placeholder="请输入密码"]'); }
  get phoneInput() { return this.page.locator('input[placeholder="请输入手机号"]').first(); }
  get smsCodeInput() { return this.page.locator('input[placeholder="请输入验证码"]').first(); }
  get submitButton() { return this.page.locator('button[type="submit"]'); }
  get formErrors() { return this.page.locator('text=请输入用户名和密码').or(this.page.locator('text=登录失败')).or(this.page.locator('text=手机号格式错误')); }
  get titleText() { return this.page.locator('h1'); }

  async goto() { await this.page.goto('/login'); }
  async fillForm(username: string, password: string) {
    await this.usernameInput.fill(username);
    await this.passwordInput.fill(password);
  }
  async submit() { await this.submitButton.click(); }
  async loginAs(user = TEST_USERS.admin) {
    await this.fillForm(user.username, user.password);
    await this.submit();
  }
}

export class DashboardPage {
  constructor(private page: Page) {}

  get statCards() { return this.page.locator('.ant-statistic'); }
  get sider() { return this.page.locator('.ant-layout-sider'); }
  get header() { return this.page.locator('.ant-layout-header'); }

  async goto() { await this.page.goto('/dashboard'); }
  async waitLoaded() {
    await this.page.waitForLoadState('networkidle');
    await this.page.waitForTimeout(500);
  }
}

export class StationsPage {
  constructor(private page: Page) {}

  get addButton() { return this.page.locator('button').filter({ hasText: /添加站点/ }); }
  get refreshButton() { return this.page.locator('button').filter({ hasText: /刷新/ }); }
  get searchInput() { return this.page.locator('input[placeholder*="搜索站点"]'); }
  get table() { return this.page.locator('.ant-table'); }
  get modal() { return this.page.locator('.ant-modal'); }
  get statCards() { return this.page.locator('.ant-statistic'); }

  async goto() { await this.page.goto('/stations'); }
}

export class DevicesPage {
  constructor(private page: Page) {}

  get addButton() { return this.page.locator('button').filter({ hasText: /新增设备/ }); }
  get table() { return this.page.locator('.ant-table'); }
  get searchInput() { return this.page.locator('input[placeholder*="搜索设备"]'); }
  get typeFilter() { return this.page.locator('.ant-select').filter({ hasText: /设备类型/ }).or(this.page.locator('text=设备类型 ~ .ant-select')); }

  async goto() { await this.page.goto('/devices'); }
}

export class WorkOrdersPage {
  constructor(private page: Page) {}

  get createButton() { return this.page.locator('button').filter({ hasText: /创建工单|新增工单/ }); }
  get table() { return this.page.locator('.ant-table'); }
  get modal() { return this.page.locator('.ant-modal'); }
  get searchInput() { return this.page.locator('input[placeholder*="搜索"]'); }

  async goto() { await this.page.goto('/workorders'); }
}

export class AlarmsPage {
  constructor(private page: Page) {}

  get table() { return this.page.locator('.ant-table'); }
  get statCards() { return this.page.locator('.ant-statistic'); }
  get tabs() { return this.page.locator('.ant-tabs'); }

  async goto() { await this.page.goto('/alarms'); }
}

export class UsersPage {
  constructor(private page: Page) {}

  get addButton() { return this.page.locator('button').filter({ hasText: /添加用户/ }); }
  get table() { return this.page.locator('.ant-table'); }
  get modal() { return this.page.locator('.ant-modal'); }

  async goto() { await this.page.goto('/users'); }
}

export class NotificationRulesPage {
  constructor(private page: Page) {}

  get table() { return this.page.locator('.ant-table'); }
  get tabs() { return this.page.locator('.ant-tabs'); }

  async goto() { await this.page.goto('/alarm-notices'); }
}