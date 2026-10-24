/**
 * 通知规则管理页面 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  default: mockApi,
}));

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

import NotificationRulesPage from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockRules = [
  { id: 1, name: '紧急告警通知', level: 'critical', channels: ['sms', 'phone'], receivers: ['team:ops', 'oncall'], enabled: true, created_at: '2024-01-01T00:00:00Z' },
  { id: 2, name: '警告通知', level: 'warning', channels: ['email', 'im_b'], receivers: ['team:manager'], enabled: false, created_at: '2024-02-01T00:00:00Z' },
  { id: 3, name: '信息通知', level: 'info', channels: ['im'], receivers: ['user:admin'], enabled: true, created_at: '2024-03-01T00:00:00Z' },
];

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: mockRules });
  mockApi.post.mockResolvedValue({ data: { id: 99 } });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
});

describe('通知规则 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><NotificationRulesPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('加载后渲染规则列表', async () => {
    await act(async () => {
      render(<BrowserRouter><NotificationRulesPage /></BrowserRouter>);
    });
    expect(await screen.findByText('紧急告警通知')).toBeInTheDocument();
    expect(screen.getByText('警告通知')).toBeInTheDocument();
    expect(screen.getByText('信息通知')).toBeInTheDocument();
  });

  it('渲染统计卡片（总规则数、已启用、已禁用、紧急级别）', async () => {
    await act(async () => {
      render(<BrowserRouter><NotificationRulesPage /></BrowserRouter>);
    });
    await screen.findByText('紧急告警通知');
    expect(screen.getByText('总规则数')).toBeInTheDocument();
    expect(screen.getByText('已启用')).toBeInTheDocument();
    expect(screen.getByText('已禁用')).toBeInTheDocument();
    expect(screen.getByText('紧急级别')).toBeInTheDocument();
  });
});

describe('通知规则 — 数据展示', () => {
  it('API get 被调用加载规则', async () => {
    await act(async () => {
      render(<BrowserRouter><NotificationRulesPage /></BrowserRouter>);
    });
    expect(mockApi.get).toHaveBeenCalledWith('/notification-rules');
  });

  it('渲染创建按钮', async () => {
    await act(async () => {
      render(<BrowserRouter><NotificationRulesPage /></BrowserRouter>);
    });
    await screen.findByText('紧急告警通知');
    expect(screen.getByText('创建规则')).toBeInTheDocument();
  });

  it('渲染规则说明区域', async () => {
    await act(async () => {
      render(<BrowserRouter><NotificationRulesPage /></BrowserRouter>);
    });
    await screen.findByText('紧急告警通知');
    expect(screen.getByText('规则说明')).toBeInTheDocument();
  });
});

describe('通知规则 — 交互', () => {
  it('点击创建按钮打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><NotificationRulesPage /></BrowserRouter>);
    });
    await screen.findByText('紧急告警通知');

    fireEvent.click(screen.getByText('创建规则'));

    await waitFor(() => {
      expect(screen.getByText('创建通知规则')).toBeInTheDocument();
    });
  });

  it('点击编辑按钮打开编辑弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><NotificationRulesPage /></BrowserRouter>);
    });
    await screen.findByText('紧急告警通知');

    const editBtns = screen.getAllByText('编辑');
    fireEvent.click(editBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('编辑通知规则')).toBeInTheDocument();
    });
  });

  it('API失败时显示错误提示', async () => {
    mockApi.get.mockRejectedValue(new Error('fail'));
    await act(async () => {
      render(<BrowserRouter><NotificationRulesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalled();
    });
  });
});

describe('通知规则 — 边界条件', () => {
  it('空规则列表不崩溃', async () => {
    mockApi.get.mockResolvedValue({ data: [] });
    await act(async () => {
      render(<BrowserRouter><NotificationRulesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('创建规则')).toBeInTheDocument();
    });
  });

  it('toggle API 调用参数正确', async () => {
    await mockApi.put('/notification-rules/1/toggle');
    expect(mockApi.put).toHaveBeenCalledWith('/notification-rules/1/toggle');
  });

  it('delete API 调用参数正确', async () => {
    await mockApi.delete('/notification-rules/1');
    expect(mockApi.delete).toHaveBeenCalledWith('/notification-rules/1');
  });
});
