import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockAuthAPI } = vi.hoisted(() => ({
  mockAuthAPI: {
    registerEnterprise: vi.fn(),
    uploadLicense: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ authAPI: mockAuthAPI }));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import RegisterPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockAuthAPI.registerEnterprise.mockResolvedValue({ data: { id: 1, status: 'pending' } });
  mockAuthAPI.uploadLicense.mockResolvedValue({ data: { file_path: '/uploads/x.png' } });
});

function renderPage() {
  return render(
    <BrowserRouter>
      <RegisterPage />
    </BrowserRouter>
  );
}

// 填满所有合法字段(协议默认勾选与否由参数控制)
function fillValid(container: HTMLElement, opts: { agree: boolean; password?: string; confirm?: string }) {
  const getByLabelText = (text: RegExp) => {
    const label = Array.from(container.querySelectorAll('label')).find(l => text.test(l.textContent || ''));
    return label;
  };
  const setInput = (labelText: RegExp, value: string) => {
    const label = getByLabelText(labelText);
    const input = label?.parentElement?.querySelector('input') as HTMLInputElement | null;
    if (input) fireEvent.change(input, { target: { value } });
  };
  setInput(/企业名称/, '测试新能源公司');
  setInput(/统一社会信用代码/, '91110000ABCDEFGH01'); // 18位合法字符
  setInput(/联系人 \*/, '王五');
  setInput(/联系人手机/, '13912345678');
  setInput(/登录密码/, opts.password ?? 'pass1234');
  setInput(/确认密码/, opts.confirm ?? 'pass1234');

  if (opts.agree) {
    const agreeInput = container.querySelector('#agreeTerms') as HTMLInputElement;
    if (agreeInput) fireEvent.click(agreeInput);
  }
}

describe('Register 企业注册页', () => {
  it('渲染不崩溃, 含关键字段', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = renderPage();
      container = r.container;
    });
    expect(container!).toBeTruthy();
    expect(document.body.textContent).toMatch(/企业注册/);
    expect(document.body.textContent).toMatch(/统一社会信用代码/);
  });

  it('必填校验: 空提交显示错误, 不调用注册接口', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = renderPage();
      container = r.container;
    });
    // 取消默认勾选的协议
    const agreeInput = container!.querySelector('#agreeTerms') as HTMLInputElement;
    if (agreeInput) fireEvent.click(agreeInput);

    const btn = screen.getByRole('button', { name: /提交注册申请/ });
    await act(async () => {
      fireEvent.click(btn);
    });

    expect(document.body.textContent).toMatch(/请输入企业名称|统一社会信用代码需18位/);
    expect(mockAuthAPI.registerEnterprise).not.toHaveBeenCalled();
  });

  it('协议必勾: 未勾协议提交显示提示', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = renderPage();
      container = r.container;
    });
    fillValid(container!, { agree: false });

    const btn = screen.getByRole('button', { name: /提交注册申请/ });
    await act(async () => {
      fireEvent.click(btn);
    });

    expect(document.body.textContent).toMatch(/同意平台协议/);
    expect(mockAuthAPI.registerEnterprise).not.toHaveBeenCalled();
  });

  it('密码确认不匹配: 显示不一致提示', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = renderPage();
      container = r.container;
    });
    fillValid(container!, { agree: true, password: 'pass1234', confirm: 'pass9999' });

    const btn = screen.getByRole('button', { name: /提交注册申请/ });
    await act(async () => {
      fireEvent.click(btn);
    });

    expect(document.body.textContent).toMatch(/两次输入的密码不一致/);
    expect(mockAuthAPI.registerEnterprise).not.toHaveBeenCalled();
  });

  it('全部合法并勾协议: 提交成功 → 等待审核页', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = renderPage();
      container = r.container;
    });
    fillValid(container!, { agree: true });

    const btn = screen.getByRole('button', { name: /提交注册申请/ });
    await act(async () => {
      fireEvent.click(btn);
    });

    await waitFor(() => {
      expect(mockAuthAPI.registerEnterprise).toHaveBeenCalledTimes(1);
    });
    // payload 校验: apply_scope=both, agreed_to_terms=true, credit_code 大写
    const payload = mockAuthAPI.registerEnterprise.mock.calls[0][0];
    expect(payload.apply_scope).toBe('both');
    expect(payload.agreed_to_terms).toBe(true);
    expect(payload.credit_code).toBe('91110000ABCDEFGH01');

    await waitFor(() => {
      expect(document.body.textContent).toMatch(/资料已提交|等待平台审核/);
    });
  });
});
