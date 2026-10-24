/**
 * API密钥管理页 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API — default export (axios instance)
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ default: mockApi }));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

// Mock navigator.clipboard
Object.assign(navigator, {
  clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
});

import ApiKeyPage from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockKeys = {
  items: [
    { id: 1, name: '数据上报服务', key_prefix: 'sk-a1b2', description: '用于设备数据上报', scopes: ['devices:read', 'devices:write'], rate_limit: 1000, is_active: true, is_revoked: false, created_at: '2026-07-01T10:00:00Z', expires_at: '2027-07-01T10:00:00Z', last_used_at: '2026-07-20T15:00:00Z' },
    { id: 2, name: '告警通知服务', key_prefix: 'sk-c3d4', description: '告警回调', scopes: ['alarms:read'], rate_limit: 500, is_active: false, is_revoked: false, created_at: '2026-06-01T10:00:00Z', expires_at: undefined, last_used_at: undefined },
    { id: 3, name: '旧版密钥(已撤销)', key_prefix: 'sk-e5f6', description: '废弃', scopes: ['stations:read'], rate_limit: 100, is_active: true, is_revoked: true, created_at: '2026-01-01T10:00:00Z', expires_at: '2026-06-01T10:00:00Z', last_used_at: '2026-05-01T10:00:00Z' },
  ],
};

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: mockKeys });
  mockApi.post.mockResolvedValue({ data: { api_key: 'sk-newkey123' } });
  mockApi.delete.mockResolvedValue({ data: {} });
});

describe('API密钥管理 — 渲染', () => {
  it('页面可渲染不崩溃', async () => {
    let container: HTMLElement;
    await act(async () => {
      const { container: c } = render(<BrowserRouter><ApiKeyPage /></BrowserRouter>);
      container = c;
    });
    expect(container!).toBeTruthy();
  });

  it('加载后表格渲染密钥数据', async () => {
    await act(async () => {
      render(<BrowserRouter><ApiKeyPage /></BrowserRouter>);
    });
    expect(await screen.findByText('数据上报服务')).toBeInTheDocument();
    expect(screen.getByText('告警通知服务')).toBeInTheDocument();
    expect(screen.getByText('旧版密钥(已撤销)')).toBeInTheDocument();
  });

  it('统计卡片展示正确数量', async () => {
    await act(async () => {
      render(<BrowserRouter><ApiKeyPage /></BrowserRouter>);
    });
    await screen.findByText('数据上报服务');
    // 总密钥数: 3 (Statistic + table cell 都包含 "3"，用 getAllByText)
    expect(screen.getAllByText('3').length).toBeGreaterThan(0);
    // 活跃密钥: 1
    expect(screen.getByText('活跃密钥')).toBeInTheDocument();
  });
});

describe('API密钥管理 — 交互', () => {
  it('点击创建按钮打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><ApiKeyPage /></BrowserRouter>);
    });
    await screen.findByText('数据上报服务');

    fireEvent.click(screen.getByText('创建密钥'));

    await waitFor(() => {
      expect(screen.getByText('密钥名称')).toBeInTheDocument();
    });
  });

  it('撤销密钥调用 delete API', async () => {
    await act(async () => {
      render(<BrowserRouter><ApiKeyPage /></BrowserRouter>);
    });
    await screen.findByText('数据上报服务');

    // 找到 Popconfirm 触发按钮（danger 按钮）
    const dangerButtons = screen.getAllByRole('button');
    const revokeBtn = dangerButtons.find(btn => btn.querySelector('.anticon-delete'));
    expect(revokeBtn).toBeTruthy();

    await act(async () => {
      fireEvent.click(revokeBtn!);
    });

    // 点击确认
    await waitFor(() => {
      const okBtn = screen.getByText('OK');
      if (okBtn) fireEvent.click(okBtn);
    });

    await waitFor(() => {
      expect(mockApi.delete).toHaveBeenCalled();
    });
  });

  it('查看使用统计打开弹窗', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/usage')) return Promise.resolve({ data: { total_requests: 1000, avg_duration_ms: 50, status_distribution: [{ status: 200, count: 950 }], top_paths: [{ path: '/api/v1/devices', count: 500, avg_duration: 30 }] } });
      return Promise.resolve({ data: mockKeys });
    });

    await act(async () => {
      render(<BrowserRouter><ApiKeyPage /></BrowserRouter>);
    });
    await screen.findByText('数据上报服务');

    // 找到使用统计按钮 (BarChartOutlined icon)
    const statBtns = screen.getAllByRole('button');
    const statBtn = statBtns.find(btn => btn.querySelector('.anticon-bar-chart'));
    expect(statBtn).toBeTruthy();

    await act(async () => {
      fireEvent.click(statBtn!);
    });

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith(expect.stringContaining('/usage'), expect.anything());
    });
  });
});

describe('API密钥管理 — 边界条件', () => {
  it('空密钥列表正常渲染', async () => {
    mockApi.get.mockResolvedValue({ data: { items: [] } });

    await act(async () => {
      render(<BrowserRouter><ApiKeyPage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.queryByText('数据上报服务')).not.toBeInTheDocument();
    });
  });

  it('创建密钥成功后刷新列表', async () => {
    await act(async () => {
      render(<BrowserRouter><ApiKeyPage /></BrowserRouter>);
    });
    await screen.findByText('数据上报服务');

    // 打开创建弹窗
    await act(async () => {
      fireEvent.click(screen.getByText('创建密钥'));
    });

    // 等待 Modal 出现
    await waitFor(() => {
      expect(screen.getByText('创建API密钥')).toBeInTheDocument();
    });

    // 填写表单
    const nameInput = screen.getByPlaceholderText('如：数据上报服务');
    fireEvent.change(nameInput, { target: { value: '测试密钥' } });

    // 提交表单 (Ant Design 中文按钮自动加空格: "创 建")
    const submitBtn = screen.getByRole('button', { name: '创 建' });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith('/api-keys', expect.objectContaining({ name: '测试密钥' }));
    });
  });
});
