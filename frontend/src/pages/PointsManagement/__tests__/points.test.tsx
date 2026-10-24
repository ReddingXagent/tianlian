/**
 * 积分管理 — Vitest 单元测试
 * 测试覆盖: 积分规则列表 / 积分流水 / CRUD交互 / 统计
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
  return {
    ...actual,
    DatePicker: () => React.createElement('input', { type: 'date', 'data-testid': 'date-picker-mock' }),
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), warn: vi.fn() },
  };
});

// ═══════════════════════════════════════════
// Mock 数据
// ═══════════════════════════════════════════
const mockRules = {
  items: [
    { id: 1, name: '充电积分', rule_type: 'charge', points: 1, unit: '每kWh', daily_limit: 100, weekly_limit: 500, total_limit: null, applicable_user_types: null, min_amount: null, points_expire_days: 365, is_active: true, start_time: '2026-07-01T00:00:00Z', end_time: null, description: '每充电1kWh获得1积分', created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z' },
    { id: 2, name: '签到积分', rule_type: 'sign_in', points: 5, unit: '每次', daily_limit: 1, weekly_limit: 7, total_limit: null, applicable_user_types: 'app', min_amount: null, points_expire_days: 90, is_active: true, start_time: '2026-07-01T00:00:00Z', end_time: null, description: '每日签到获得5积分', created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z' },
    { id: 3, name: '生日积分', rule_type: 'birthday', points: 500, unit: '每年', daily_limit: null, weekly_limit: null, total_limit: null, applicable_user_types: null, min_amount: null, points_expire_days: 30, is_active: false, start_time: '2026-07-01T00:00:00Z', end_time: null, description: '生日月赠送500积分', created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z' },
  ],
};

const mockRecords = {
  items: [
    { id: 1, user_id: 100, user_type: 'app', rule_id: 1, record_type: 'earn', points: 50, balance_before: 100, balance_after: 150, description: '充电获得积分', order_id: 501, expires_at: '2027-07-01T00:00:00Z', created_at: '2026-07-10T14:00:00Z' },
    { id: 2, user_id: 200, user_type: 'card', rule_id: null, record_type: 'redeem', points: -30, balance_before: 80, balance_after: 50, description: '兑换充电券', order_id: null, expires_at: null, created_at: '2026-07-11T10:00:00Z' },
  ],
};

const mockStats = {
  total_rules: 3,
  active_rules: 2,
  total_earned: 15000,
  total_records: 500,
};

// ═══════════════════════════════════════════
// 导入组件
// ═══════════════════════════════════════════
import PointsManagement from '../index';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/operate/points/records')) return Promise.resolve({ data: mockRecords });
    if (url.includes('/operate/points/stats')) return Promise.resolve({ data: mockStats });
    if (url.includes('/operate/points')) return Promise.resolve({ data: mockRules });
    return Promise.resolve({ data: [] });
  });
  mockApi.post.mockResolvedValue({});
  mockApi.put.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
});

// ═══════════════════════════════════════════
// 辅助
// ═══════════════════════════════════════════
function waitForRules() {
  return waitFor(() => {
    expect(screen.getAllByText('充电积分').length).toBeGreaterThan(0);
  });
}

// ═══════════════════════════════════════════
// 测试: 页面渲染
// ═══════════════════════════════════════════
describe('积分管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><PointsManagement /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('渲染统计卡片', async () => {
    await act(async () => {
      render(<BrowserRouter><PointsManagement /></BrowserRouter>);
    });
    expect(screen.getByText('规则总数')).toBeInTheDocument();
    expect(screen.getByText('活跃规则')).toBeInTheDocument();
    expect(screen.getByText('累计获取')).toBeInTheDocument();
    expect(screen.getByText('流水总数')).toBeInTheDocument();
  });

  it('默认显示积分规则Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><PointsManagement /></BrowserRouter>);
    });
    // '充电积分' appears as both rule name and rule_type tag
    await waitForRules();
    expect(screen.getAllByText('签到积分').length).toBeGreaterThan(0);
    expect(screen.getAllByText('生日积分').length).toBeGreaterThan(0);
  });
});

// ═══════════════════════════════════════════
// 测试: 积分规则列表
// ═══════════════════════════════════════════
describe('积分规则 — 列表与交互', () => {
  it('规则名称正确显示', async () => {
    await act(async () => {
      render(<BrowserRouter><PointsManagement /></BrowserRouter>);
    });
    await waitForRules();
    // All three rule names are present
    expect(screen.getAllByText('充电积分').length).toBeGreaterThan(0);
    expect(screen.getAllByText('签到积分').length).toBeGreaterThan(0);
    expect(screen.getAllByText('生日积分').length).toBeGreaterThan(0);
  });

  it('状态标签正确显示', async () => {
    await act(async () => {
      render(<BrowserRouter><PointsManagement /></BrowserRouter>);
    });
    await waitForRules();
    expect(screen.getAllByText('启用').length).toBeGreaterThan(0);
    expect(screen.getAllByText('停用').length).toBeGreaterThan(0);
  });

  it('新建积分规则按钮打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><PointsManagement /></BrowserRouter>);
    });
    await waitForRules();

    fireEvent.click(screen.getByText('新建积分规则'));

    await waitFor(() => {
      expect(screen.getByText('规则类型')).toBeInTheDocument();
    });
  });

  it('编辑规则打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><PointsManagement /></BrowserRouter>);
    });
    await waitForRules();

    const editBtns = screen.getAllByText('编辑');
    fireEvent.click(editBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('规则类型')).toBeInTheDocument();
    });
  });

  it('删除规则调用正确API', async () => {
    await act(async () => {
      render(<BrowserRouter><PointsManagement /></BrowserRouter>);
    });
    await waitForRules();

    const deleteBtns = screen.getAllByText('删除');
    fireEvent.click(deleteBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('确认删除？')).toBeInTheDocument();
    });

    const popconfirmBtns = document.querySelectorAll('.ant-popconfirm-buttons .ant-btn-primary');
    expect(popconfirmBtns.length).toBeGreaterThan(0);
    await act(async () => {
      fireEvent.click(popconfirmBtns[0]);
    });

    await waitFor(() => {
      expect(mockApi.delete).toHaveBeenCalledWith('/operate/points/1');
    });
  });
});

// ═══════════════════════════════════════════
// 测试: Tab切换到积分流水
// ═══════════════════════════════════════════
describe('积分流水 — Tab切换', () => {
  it('切换到积分流水Tab显示流水数据', async () => {
    await act(async () => {
      render(<BrowserRouter><PointsManagement /></BrowserRouter>);
    });
    await waitForRules();

    const recordsTab = screen.getByText(/积分流水/);
    fireEvent.click(recordsTab);

    await waitFor(() => {
      expect(screen.getByText('兑换充电券')).toBeInTheDocument();
    });
  });
});
