/**
 * 消息通知中心页面 — Vitest 单元测试
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

import MessageCenter from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockStats = {
  total_templates: 5,
  total_messages: 120,
  sent_today: 15,
  failed_count: 3,
  channel_distribution: { sms: 30, email: 50, app_push: 40 },
};

const mockTemplates = {
  items: [
    { id: 1, name: '充电完成通知', template_type: 'charging', title: '充电完成', content: '您的设备已充电完成', channels: ['sms', 'app_push'], variables: {}, enabled: true, created_at: '2024-01-01T00:00:00Z' },
    { id: 2, name: '维护通知', template_type: 'maintenance', title: '设备维护', content: '设备将于明日维护', channels: ['email'], variables: {}, enabled: false, created_at: '2024-02-01T00:00:00Z' },
  ],
};

const mockMessages = {
  items: [
    { id: 1, template_id: 1, template_name: '充电完成通知', title: '充电完成', content: '内容...', channel: 'sms', receivers: ['user:admin'], sender: 'system', status: 'sent', result_message: null, sent_at: '2024-05-15T10:00:00Z', created_at: '2024-05-15T09:50:00Z' },
    { id: 2, template_id: null, template_name: null, title: '紧急告警', content: '告警内容', channel: 'email', receivers: ['team:ops'], sender: 'admin', status: 'failed', result_message: 'SMTP错误', sent_at: null, created_at: '2024-05-15T11:00:00Z' },
  ],
  total: 2,
};

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/notifications/stats')) return Promise.resolve({ data: mockStats });
    if (url.includes('/notifications/templates')) return Promise.resolve({ data: mockTemplates });
    if (url.includes('/notifications/messages')) return Promise.resolve({ data: mockMessages });
    return Promise.resolve({ data: {} });
  });
  mockApi.post.mockResolvedValue({ data: { id: 99 } });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
});

describe('消息中心 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><MessageCenter /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('渲染三个Tab（消息发送、消息模板、发送记录）', async () => {
    await act(async () => {
      render(<BrowserRouter><MessageCenter /></BrowserRouter>);
    });
    await waitFor(() => {
      // Tabs have role=tab
      const tabs = screen.getAllByRole('tab');
      const tabTexts = tabs.map(t => t.textContent || '');
      expect(tabTexts.some(t => t.includes('消息发送'))).toBe(true);
      expect(tabTexts.some(t => t.includes('消息模板'))).toBe(true);
      expect(tabTexts.some(t => t.includes('发送记录'))).toBe(true);
    });
  });

  it('渲染统计概览数据', async () => {
    await act(async () => {
      render(<BrowserRouter><MessageCenter /></BrowserRouter>);
    });
    await waitFor(() => {
      // Stats titles
      const statsTitles = screen.getAllByText('总消息数');
      expect(statsTitles.length).toBeGreaterThan(0);
      expect(screen.getAllByText('今日发送').length).toBeGreaterThan(0);
    });
  });
});

describe('消息中心 — 数据展示', () => {
  it('stats API 被调用', async () => {
    await act(async () => {
      render(<BrowserRouter><MessageCenter /></BrowserRouter>);
    });
    expect(mockApi.get).toHaveBeenCalledWith('/notifications/stats');
  });

  it('切换到模板Tab加载模板列表', async () => {
    await act(async () => {
      render(<BrowserRouter><MessageCenter /></BrowserRouter>);
    });

    // Click the tab (not the statistic title)
    const tabs = screen.getAllByRole('tab');
    const tplTab = tabs.find(t => (t.textContent || '').includes('消息模板'));
    expect(tplTab).toBeTruthy();
    fireEvent.click(tplTab!);

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/notifications/templates', expect.any(Object));
    });
  });

  it('切换到记录Tab加载消息列表', async () => {
    await act(async () => {
      render(<BrowserRouter><MessageCenter /></BrowserRouter>);
    });

    fireEvent.click(screen.getByText('发送记录'));

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/notifications/messages', expect.any(Object));
    });
  });
});

describe('消息中心 — 交互', () => {
  it('默认显示消息发送表单', async () => {
    await act(async () => {
      render(<BrowserRouter><MessageCenter /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('消息标题')).toBeInTheDocument();
      expect(screen.getByText('消息内容')).toBeInTheDocument();
      expect(screen.getByText('发送渠道')).toBeInTheDocument();
    });
  });

  it('切换到模板Tab显示创建按钮', async () => {
    await act(async () => {
      render(<BrowserRouter><MessageCenter /></BrowserRouter>);
    });

    const tabs = screen.getAllByRole('tab');
    const tplTab = tabs.find(t => (t.textContent || '').includes('消息模板'));
    fireEvent.click(tplTab!);

    await waitFor(() => {
      expect(screen.getByText('创建模板')).toBeInTheDocument();
    });
  });

  it('stats API失败时静默处理不崩溃', async () => {
    mockApi.get.mockRejectedValue(new Error('fail'));
    await act(async () => {
      const { container } = render(<BrowserRouter><MessageCenter /></BrowserRouter>);
      expect(container).toBeTruthy();
    });
  });
});
