/**
 * 审计日志页 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API — default export (axios instance)
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn() },
}));

vi.mock('../../../api', () => ({ default: mockApi }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

import AuditLogPage from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockLogs = {
  items: [
    { id: 1, timestamp: '2026-07-21T10:00:00Z', username: 'admin', user_role: 'ADMIN', action: 'login', module: 'auth', target_id: null, target_desc: null, detail: '用户登录', ip_address: '192.168.1.1', result: 'success', error_msg: null },
    { id: 2, timestamp: '2026-07-21T11:00:00Z', username: 'operator', user_role: 'OPERATOR', action: 'create', module: 'stations', target_id: '1', target_desc: 'StationA', detail: '创建站点', ip_address: '10.0.0.1', result: 'success', error_msg: null },
    { id: 3, timestamp: '2026-07-21T12:00:00Z', username: 'viewer', user_role: 'VIEWER', action: 'delete', module: 'devices', target_id: '5', target_desc: 'DeviceX', detail: '删除设备', ip_address: '10.0.0.2', result: 'failure', error_msg: 'Permission denied' },
  ],
  total: 3,
};

const mockStats = {
  total_logs: 150,
  today_logs: 15,
  failed_logs: 3,
  by_action: { login: 50, logout: 30, create: 20 },
};

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/stats')) return Promise.resolve({ data: mockStats });
    return Promise.resolve({ data: mockLogs });
  });
});

describe('审计日志 — 渲染', () => {
  it('页面可渲染不崩溃', async () => {
    let container: HTMLElement;
    await act(async () => {
      const { container: c } = render(<BrowserRouter><AuditLogPage /></BrowserRouter>);
      container = c;
    });
    expect(container!).toBeTruthy();
  });

  it('加载后表格渲染日志数据（用户名列）', async () => {
    await act(async () => {
      render(<BrowserRouter><AuditLogPage /></BrowserRouter>);
    });
    expect(await screen.findByText('admin')).toBeInTheDocument();
    expect(screen.getByText('operator')).toBeInTheDocument();
    expect(screen.getByText('viewer')).toBeInTheDocument();
  });

  it('统计数据卡片正确展示', async () => {
    await act(async () => {
      render(<BrowserRouter><AuditLogPage /></BrowserRouter>);
    });
    await screen.findByText('admin');
    // Statistic 组件渲染数值
    expect(screen.getByText('150')).toBeInTheDocument(); // 总日志
    expect(screen.getByText('15')).toBeInTheDocument();   // 今日
  });
});

describe('审计日志 — 交互', () => {
  it('点击刷新按钮触发数据重新加载', async () => {
    await act(async () => {
      render(<BrowserRouter><AuditLogPage /></BrowserRouter>);
    });
    await screen.findByText('admin');

    const initialCallCount = mockApi.get.mock.calls.length;

    fireEvent.click(screen.getByText('刷新'));

    await waitFor(() => {
      expect(mockApi.get.mock.calls.length).toBeGreaterThan(initialCallCount);
    });
  });

  it('搜索用户输入框正常工作', async () => {
    await act(async () => {
      render(<BrowserRouter><AuditLogPage /></BrowserRouter>);
    });
    await screen.findByText('admin');

    const input = screen.getByPlaceholderText('搜索用户');
    fireEvent.change(input, { target: { value: 'admin' } });

    expect(input).toHaveValue('admin');
  });
});

describe('审计日志 — 边界条件', () => {
  it('API加载失败时仍渲染页面', async () => {
    mockApi.get.mockRejectedValue(new Error('Network error'));

    let container: HTMLElement;
    await act(async () => {
      const { container: c } = render(<BrowserRouter><AuditLogPage /></BrowserRouter>);
      container = c;
    });

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalled();
    });
    expect(container!).toBeTruthy();
  });

  it('空列表正常渲染不崩溃', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/stats')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: { items: [], total: 0 } });
    });

    await act(async () => {
      render(<BrowserRouter><AuditLogPage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.queryByText('admin')).not.toBeInTheDocument();
    });
  });

  it('初始加载调用 operation-log 和 stats 接口', async () => {
    await act(async () => {
      render(<BrowserRouter><AuditLogPage /></BrowserRouter>);
    });
    await screen.findByText('admin');

    const urls = mockApi.get.mock.calls.map((c: any[]) => c[0]);
    expect(urls.some((u: string) => u.includes('/operation-log'))).toBe(true);
    expect(urls.some((u: string) => u.includes('/stats'))).toBe(true);
  });
});
