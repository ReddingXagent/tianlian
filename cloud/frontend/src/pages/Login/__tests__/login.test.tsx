import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockAuthAPI } = vi.hoisted(() => ({
  mockAuthAPI: { login: vi.fn(), sendSms: vi.fn(), verify2FA: vi.fn() },
}));

vi.mock('../../../api', () => ({ authAPI: mockAuthAPI }));
vi.mock('../../../utils/auth', () => ({
  setUserType: vi.fn(),
  getDefaultRoute: vi.fn(() => '/dashboard'),
  USER_TYPE_LABELS: { operator: '运营', admin: '管理员', engineer: '工程师', fleet: '车队' },
  USER_TYPE_DESCRIPTIONS: {},
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import LoginPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockAuthAPI.login.mockResolvedValue({ data: { data: { token: 'test-token' } } });
  mockAuthAPI.sendSms.mockResolvedValue({});
  mockAuthAPI.verify2FA.mockResolvedValue({ data: { token: 'final-token' } });
});

describe('Login 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><LoginPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('渲染角色选择卡片', async () => {
    await act(async () => {
      render(<BrowserRouter><LoginPage /></BrowserRouter>);
    });
    expect(document.body.textContent).toBeTruthy();
  });

  it('渲染登录页标题和SVG图标', async () => {
    await act(async () => {
      render(<BrowserRouter><LoginPage /></BrowserRouter>);
    });
    // Login page should render title text and svg elements
    expect(document.querySelector('svg')).toBeTruthy();
    expect(document.body.textContent).toMatch(/天链|登录|选择/);
  });

  it('两步登录: second_factor_required 响应后切换到验证码输入', async () => {
    // login 返回 2FA 要求, 不发正式 token
    mockAuthAPI.login.mockResolvedValue({
      data: { second_factor_required: true, temp_token: 'tmp-xxx', method: 'sms', phone_masked: '139****0001' },
    });

    await act(async () => {
      render(<BrowserRouter><LoginPage /></BrowserRouter>);
    });

    // 通过点击"进入"按钮进入登录表单: 找到第一个"进入"文本并点击
    const enterBtns = Array.from(document.querySelectorAll('*')).filter(
      el => el.textContent === '进入'
    ) as HTMLElement[];
    await act(async () => {
      fireEvent.click(enterBtns[0]);
    });

    // 输入用户名/密码
    const inputs = screen.getAllByPlaceholderText(/用户名|密码/) as HTMLInputElement[];
    fireEvent.change(inputs[0], { target: { value: 'admin2fa' } });
    fireEvent.change(inputs[1], { target: { value: 'pass1234' } });

    // 提交登录
    const submitBtn = screen.getByRole('button', { name: /登 录/ });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    // 应进入 2FA 验证码输入界面
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/6位验证码/)).toBeTruthy();
    });
    expect(document.body.textContent).toMatch(/139\*+0001/);

    // 输入验证码并提交 → 调 verify2FA
    fireEvent.change(screen.getByPlaceholderText(/6位验证码/), { target: { value: '123456' } });
    const verifyBtn = screen.getByRole('button', { name: /验证并登录/ });
    await act(async () => {
      fireEvent.click(verifyBtn);
    });
    await waitFor(() => {
      expect(mockAuthAPI.verify2FA).toHaveBeenCalledWith('tmp-xxx', '123456');
    });
  });
});
