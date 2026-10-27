/**
 * 用户类型管理 — Vitest 单元测试
 * 测试覆盖: 用户类型Tab(含活跃用户) / 列表渲染 / 编辑交互 / 板块精简校验
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ default: mockApi }));

// Mock PageWrapper to avoid importing complex child components
vi.mock('../../../components/PageWrapper', () => ({
  default: ({ children }: { children: React.ReactNode }) => React.createElement('div', null, children),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), warn: vi.fn() } };
});

// ═══════════════════════════════════════════
// Mock 数据
// ═══════════════════════════════════════════
const mockUsersData = {
  items: [
    { id: 1, username: 'appuser01', real_name: '张三', phone: '13800138001', email: 'zhangsan@example.com', role: 'app', status: 'active', last_login: '2026-07-10T08:00:00Z', created_at: '2026-01-15T10:00:00Z' },
    { id: 2, username: 'carduser01', real_name: '李四', phone: '13800138002', email: 'lisi@example.com', role: 'card', status: 'active', last_login: '2026-07-09T14:00:00Z', created_at: '2026-02-20T10:00:00Z' },
    { id: 3, username: 'vinuser01', real_name: null, phone: null, email: null, role: 'vin', status: 'inactive', last_login: null, created_at: '2026-03-01T10:00:00Z' },
    { id: 4, username: 'interconnect01', real_name: '王五', phone: '13800138004', email: null, role: 'interconnect', status: 'active', last_login: '2026-07-11T09:00:00Z', created_at: '2026-04-10T10:00:00Z' },
    { id: 5, username: 'enterprise01', real_name: '赵六', phone: '13800138005', email: 'zhao6@corp.com', role: 'enterprise', status: 'suspended', last_login: '2026-06-15T12:00:00Z', created_at: '2026-05-01T10:00:00Z' },
  ],
};

const mockStats = {
  total: 150,
  active_count: 120,
  by_user_type: { app: 60, card: 30, vin: 25, interconnect: 20, enterprise: 15 },
};

// ═══════════════════════════════════════════
// 导入组件
// ═══════════════════════════════════════════
import UserTypeManagement from '../index';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/operate/users/stats')) return Promise.resolve({ data: mockStats });
    if (url.includes('/operate/users')) return Promise.resolve({ data: mockUsersData });
    return Promise.resolve({ data: [] });
  });
  mockApi.put.mockResolvedValue({});
  mockApi.post.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
});

// ═══════════════════════════════════════════
// 测试: 页面渲染
// ═══════════════════════════════════════════
describe('用户类型管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><UserTypeManagement /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('渲染5种用户类型Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><UserTypeManagement /></BrowserRouter>);
    });
    // These texts appear in both type cards and tabs
    expect(screen.getAllByText('APP用户').length).toBeGreaterThan(0);
    expect(screen.getAllByText('卡用户').length).toBeGreaterThan(0);
    expect(screen.getAllByText('VIN用户').length).toBeGreaterThan(0);
    expect(screen.getAllByText('互联互通用户').length).toBeGreaterThan(0);
    expect(screen.getAllByText('企业用户').length).toBeGreaterThan(0);
  });

  it('不渲染用户类型分布板块与统计卡片', async () => {
    await act(async () => {
      render(<BrowserRouter><UserTypeManagement /></BrowserRouter>);
    });
    expect(screen.queryByText('用户类型分布')).not.toBeInTheDocument();
    expect(screen.queryByText('用户总数')).not.toBeInTheDocument();
  });

  it('渲染活跃用户Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><UserTypeManagement /></BrowserRouter>);
    });
    // Tab 标签完整文本为 "活跃用户 (N)"，用正则匹配
    expect(screen.getByText(/活跃用户/)).toBeInTheDocument();
  });

  it('点击活跃用户Tab后请求带status=active且不带user_type', async () => {
    await act(async () => {
      render(<BrowserRouter><UserTypeManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('appuser01')).toBeInTheDocument();
    });
    mockApi.get.mockClear();
    await act(async () => {
      fireEvent.click(screen.getByText(/活跃用户/));
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith(
        '/operate/users',
        expect.objectContaining({ params: expect.objectContaining({ status: 'active' }) })
      );
    });
    // active Tab 不应附带 user_type（status 与 user_type 互斥）
    const usersCalls = mockApi.get.mock.calls.filter(([url]: [string]) => url === '/operate/users');
    expect(usersCalls.length).toBeGreaterThan(0);
    expect(usersCalls[usersCalls.length - 1][1]).not.toHaveProperty('params.user_type');
  });
});

// ═══════════════════════════════════════════
// 测试: 用户列表
// ═══════════════════════════════════════════
describe('用户类型管理 — 列表数据', () => {
  it('加载后表格渲染用户数据', async () => {
    await act(async () => {
      render(<BrowserRouter><UserTypeManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('appuser01')).toBeInTheDocument();
    });
    expect(screen.getByText('carduser01')).toBeInTheDocument();
    expect(screen.getByText('vinuser01')).toBeInTheDocument();
    expect(screen.getByText('interconnect01')).toBeInTheDocument();
    expect(screen.getByText('enterprise01')).toBeInTheDocument();
  });

  it('用户类型标签正确显示', async () => {
    await act(async () => {
      render(<BrowserRouter><UserTypeManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('appuser01')).toBeInTheDocument();
    });
    // 用户类型标签在卡片和表格中都有
    expect(screen.getAllByText('APP用户').length).toBeGreaterThan(0);
  });

  it('状态标签正确显示', async () => {
    await act(async () => {
      render(<BrowserRouter><UserTypeManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getAllByText('正常').length).toBeGreaterThan(0);
    });
    expect(screen.getByText('停用')).toBeInTheDocument();
    expect(screen.getByText('冻结')).toBeInTheDocument();
  });
});

// ═══════════════════════════════════════════
// 测试: 编辑交互
// ═══════════════════════════════════════════
describe('用户类型管理 — 编辑交互', () => {
  it('点击编辑按钮打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><UserTypeManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('appuser01')).toBeInTheDocument();
    });

    const editBtns = screen.getAllByText('编辑');
    fireEvent.click(editBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('编辑用户信息')).toBeInTheDocument();
    });
  });

  it('编辑提交调用正确API', async () => {
    await act(async () => {
      render(<BrowserRouter><UserTypeManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('appuser01')).toBeInTheDocument();
    });

    const editBtns = screen.getAllByText('编辑');
    fireEvent.click(editBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('编辑用户信息')).toBeInTheDocument();
    });

    // 点击 Modal 确定按钮
    const modalOkBtns = document.querySelectorAll('.ant-modal-footer .ant-btn-primary');
    expect(modalOkBtns.length).toBeGreaterThan(0);
    await act(async () => {
      fireEvent.click(modalOkBtns[0]);
    });

    await waitFor(() => {
      expect(mockApi.put).toHaveBeenCalledWith(
        expect.stringContaining('/operate/users/'),
        expect.any(Object)
      );
    });
  });
});
