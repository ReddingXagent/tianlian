/**
 * 安全管理页面 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块
// ═══════════════════════════════════════════
const { mockSecurityAPI, mockOperationLogAPI } = vi.hoisted(() => ({
  mockSecurityAPI: {
    logs: vi.fn(),
    stats: vi.fn(),
  },
  mockOperationLogAPI: {
    list: vi.fn(),
    stats: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  securityAPI: mockSecurityAPI,
  operationLogAPI: mockOperationLogAPI,
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

import SecurityPage from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockLogs = [
  { id: 1, username: 'admin', action: '登录系统', ip: '192.168.1.1', timestamp: '2024-05-15 10:00:00', result: 'success' },
  { id: 2, username: 'operator', action: '远程控制', ip: '10.0.0.5', timestamp: '2024-05-15 11:00:00', result: 'success' },
  { id: 3, username: 'guest', action: '登录系统', ip: '192.168.1.200', timestamp: '2024-05-15 12:00:00', result: 'failed' },
];

const mockSecurityStats = {
  blocked_ips: { '192.168.1.200': 5 },
  last_blocked_time: '2024-05-15T12:00:00Z',
};

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockOperationLogAPI.list.mockResolvedValue({ data: { items: mockLogs } });
  mockSecurityAPI.stats.mockResolvedValue({ data: mockSecurityStats });
});

describe('安全管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><SecurityPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('渲染4个Tab标签', async () => {
    await act(async () => {
      render(<BrowserRouter><SecurityPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('安全概览')).toBeInTheDocument();
      expect(screen.getByText('操作日志')).toBeInTheDocument();
      expect(screen.getByText('威胁管理')).toBeInTheDocument();
      expect(screen.getByText('安全设置')).toBeInTheDocument();
    });
  });

  it('默认渲染安全概览Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><SecurityPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('安全评分')).toBeInTheDocument();
      expect(screen.getByText('今日登录')).toBeInTheDocument();
    });
  });
});

describe('安全管理 — 数据展示', () => {
  it('operationLogAPI.list 被调用加载日志', async () => {
    await act(async () => {
      render(<BrowserRouter><SecurityPage /></BrowserRouter>);
    });
    expect(mockOperationLogAPI.list).toHaveBeenCalled();
  });

  it('securityAPI.stats 被调用加载统计数据', async () => {
    await act(async () => {
      render(<BrowserRouter><SecurityPage /></BrowserRouter>);
    });
    expect(mockSecurityAPI.stats).toHaveBeenCalled();
  });

  it('安全设置Tab渲染所有安全开关', async () => {
    await act(async () => {
      render(<BrowserRouter><SecurityPage /></BrowserRouter>);
    });
    // 点击"安全设置" Tab
    fireEvent.click(screen.getByText('安全设置'));

    await waitFor(() => {
      expect(screen.getByText('登录保护')).toBeInTheDocument();
      expect(screen.getByText('双因素认证')).toBeInTheDocument();
      expect(screen.getByText('IP白名单')).toBeInTheDocument();
      expect(screen.getByText('数据加密')).toBeInTheDocument();
    });
  });
});

describe('安全管理 — 交互', () => {
  it('切换到操作日志Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><SecurityPage /></BrowserRouter>);
    });

    // Click the tab (not the settings card)
    const tabs = screen.getAllByRole('tab');
    const logTab = tabs.find(t => (t.textContent || '').includes('操作日志'));
    expect(logTab).toBeTruthy();
    fireEvent.click(logTab!);

    await waitFor(() => {
      // Use findByPlaceholder with partial match
      const searchInput = screen.queryByPlaceholderText(/搜索用户/);
      expect(searchInput).toBeInTheDocument();
    });
  });

  it('切换到威胁管理Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><SecurityPage /></BrowserRouter>);
    });

    fireEvent.click(screen.getByText('威胁管理'));

    await waitFor(() => {
      expect(screen.getByText('手动拉黑')).toBeInTheDocument();
    });
  });

  it('securityAPI.stats 失败时不崩溃', async () => {
    mockSecurityAPI.stats.mockRejectedValue(new Error('fail'));
    await act(async () => {
      const { container } = render(<BrowserRouter><SecurityPage /></BrowserRouter>);
      expect(container).toBeTruthy();
    });
  });
});
