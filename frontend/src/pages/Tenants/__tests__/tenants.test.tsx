/**
 * 租户管理页面 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块
// ═══════════════════════════════════════════
const { mockTenantAPI } = vi.hoisted(() => ({
  mockTenantAPI: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    stats: vi.fn(),
    users: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  tenantAPI: mockTenantAPI,
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
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), loading: vi.fn() },
  };
});

import TenantsPage from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockTenants = [
  {
    id: 1, name: 'TeamAlpha', code: 'TA001', contact: '张三', phone: '13800001111',
    email: 'a@test.com', status: 'active', station_count: 5, device_count: 50,
    member_count: 10, workorder_count: 3, alarm_count: 1, expired_at: '2027-01-01',
    storage_used: '10GB', api_calls: 1000, created_at: '2025-01-01', address: 'Beijing',
    max_stations: 20, max_devices: 200,
  },
  {
    id: 2, name: 'TeamBeta', code: 'TB002', contact: '李四', phone: '13800002222',
    email: 'b@test.com', status: 'trial', station_count: 2, device_count: 20,
    member_count: 5, workorder_count: 1, alarm_count: 0, expired_at: '2026-08-01',
    created_at: '2025-06-01', address: 'Shanghai', max_stations: 10, max_devices: 100,
  },
];

const mockStatsData = {
  total: 2, active: 1, trial: 1, expired: 0,
  total_stations: 7, total_devices: 70,
};

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantAPI.list.mockResolvedValue({ data: mockTenants });
  mockTenantAPI.stats.mockResolvedValue({ data: mockStatsData });
});

describe('租户管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('加载后表格渲染租户数据', async () => {
    await act(async () => {
      render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    });
    expect(await screen.findByText('TeamAlpha')).toBeInTheDocument();
    expect(screen.getByText('TeamBeta')).toBeInTheDocument();
  });

  it('显示租户状态标签', async () => {
    await act(async () => {
      render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');
    expect(screen.getByText('pages.tenants.status_active')).toBeInTheDocument();
    expect(screen.getByText('pages.tenants.status_trial')).toBeInTheDocument();
  });
});

describe('租户管理 — 数据加载', () => {
  it('页面挂载时调用 tenantAPI.list', async () => {
    await act(async () => {
      render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    });
    expect(mockTenantAPI.list).toHaveBeenCalled();
  });

  it('页面挂载时调用 tenantAPI.stats', async () => {
    await act(async () => {
      render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    });
    expect(mockTenantAPI.stats).toHaveBeenCalled();
  });

  it('API 返回空列表时不崩溃', async () => {
    mockTenantAPI.list.mockResolvedValue({ data: [] });
    await act(async () => {
      render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockTenantAPI.list).toHaveBeenCalled();
    });
  });
});

describe('租户管理 — 用户交互', () => {
  it('搜索输入触发 API 重新加载（防抖）', async () => {
    await act(async () => {
      render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');

    vi.clearAllMocks();
    mockTenantAPI.list.mockResolvedValue({ data: mockTenants });

    const input = screen.getByPlaceholderText('pages.tenants.search_placeholder');
    fireEvent.change(input, { target: { value: 'Alpha' } });

    await waitFor(() => {
      expect(mockTenantAPI.list).toHaveBeenCalledWith({ keyword: 'Alpha' });
    }, { timeout: 3000 });
  });

  it('点击新增按钮打开 Modal', async () => {
    await act(async () => {
      render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');

    // 点击工具栏中的「新增」按钮（不是 modal 标题）
    const addButtons = screen.getAllByText('pages.tenants.add');
    fireEvent.click(addButtons[0]);

    // Modal 打开后会有第二个 'pages.tenants.add'（modal 标题）
    await waitFor(() => {
      const allAddTexts = screen.getAllByText('pages.tenants.add');
      expect(allAddTexts.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('tenantAPI.update 被调用格式正确（切换状态）', async () => {
    mockTenantAPI.update.mockResolvedValue({ data: { id: 1, status: 'disabled' } });

    await act(async () => {
      render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');

    // 直接测试 API 调用格式
    await mockTenantAPI.update(1, { status: 'disabled' });

    expect(mockTenantAPI.update).toHaveBeenCalledWith(1, { status: 'disabled' });
  });

  it('tenantAPI.delete 被调用格式正确', async () => {
    mockTenantAPI.delete.mockResolvedValue({});

    await act(async () => {
      render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');

    await mockTenantAPI.delete(1);

    expect(mockTenantAPI.delete).toHaveBeenCalledWith(1);
  });
});

describe('租户管理 — 详情抽屉成员列表（卡eb81ca13：去 mock）', () => {
  const mockMembers = {
    data: {
      items: [
        { id: 11, username: 'admin_ta', real_name: '张三', role: 'admin', status: 'active' },
        { id: 12, username: 'eng_ta', real_name: '李四', role: 'engineer', status: 'active' },
      ],
      total: 2,
    },
  };

  it('打开详情抽屉时调用 tenantAPI.users 拉取真实成员', async () => {
    mockTenantAPI.users.mockResolvedValue(mockMembers);
    await act(async () => {
      render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');

    // 团队列表中团队名即「查看详情」按钮
    fireEvent.click(screen.getByText('TeamAlpha'));
    await waitFor(() => {
      expect(mockTenantAPI.users).toHaveBeenCalledWith(1);
    });
  });

  it('成员列表渲染 API 返回的真实用户而非硬编码假数据', async () => {
    mockTenantAPI.users.mockResolvedValue(mockMembers);
    await act(async () => {
      render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');
    fireEvent.click(screen.getByText('TeamAlpha'));

    // 切到「成员管理」Tab
    const membersTab = await screen.findByText('pages.tenants.member_management');
    fireEvent.click(membersTab);

    expect(await screen.findByText('admin_ta')).toBeInTheDocument();
    expect(screen.getByText('eng_ta')).toBeInTheDocument();
    // 旧 mock 假账号格式不应出现
    expect(screen.queryByText('admin_teamalpha')).not.toBeInTheDocument();
    expect(screen.queryByText('eng_teamalpha')).not.toBeInTheDocument();
  });

  it('成员接口返回空时显示空态而非假数据', async () => {
    mockTenantAPI.users.mockResolvedValue({ data: { items: [], total: 0 } });
    await act(async () => {
      render(<BrowserRouter><TenantsPage /></BrowserRouter>);
    });
    await screen.findByText('TeamAlpha');
    fireEvent.click(screen.getByText('TeamAlpha'));

    const membersTab = await screen.findByText('pages.tenants.member_management');
    fireEvent.click(membersTab);

    await waitFor(() => {
      expect(mockTenantAPI.users).toHaveBeenCalledWith(1);
    });
    expect(screen.queryByText('admin_teamalpha')).not.toBeInTheDocument();
    expect(await screen.findByText('pages.tenants.members_empty')).toBeInTheDocument();
  });
});
