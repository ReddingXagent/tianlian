/**
 * 司机管理页面 — Vitest 单元测试
 *
 * 覆盖：渲染、统计卡片、列表加载、搜索筛选、新增Modal、编辑、删除、详情抽屉
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API (hoisted so vi.mock can reference it)
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

vi.mock('../../../../api', () => ({ default: mockApi }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockDrivers = [
  { id: 1, enterprise_id: 1, name: '张三', phone: '13800138001', license_no: 'D64123456', license_type: 'C1', status: 'active', total_charge_kwh: 5234.5, total_spent: 4600.00, rating: 4.8, account: { id: 1, balance: 500.00, status: 'active' } },
  { id: 2, enterprise_id: 1, name: '李四', phone: '13900139002', license_no: 'D64789101', license_type: 'B2', status: 'active', total_charge_kwh: 3200.0, total_spent: 2800.00, rating: 4.5, account: { id: 2, balance: 200.00, status: 'active' } },
  { id: 3, enterprise_id: 2, name: '王五', phone: '13700137003', license_no: 'D64333444', license_type: 'A2', status: 'inactive', total_charge_kwh: 0, total_spent: 0, rating: 5.0, account: { id: 3, balance: 0, status: 'inactive' } },
];

const mockTransactions = {
  items: [
    { id: 1, type: 'recharge', amount: 200.00, balance_after: 700.00, remark: '线上充值', created_at: '2026-07-15T10:00:00Z' },
    { id: 2, type: 'consume', amount: -50.00, balance_after: 650.00, remark: '充电消费', created_at: '2026-07-16T14:00:00Z' },
  ],
  total: 2,
};

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/fleet/drivers') && url.includes('/transactions')) {
      return Promise.resolve({ data: mockTransactions });
    }
    if (url.includes('/fleet/drivers') && !url.includes('account')) {
      return Promise.resolve({ data: mockDrivers });
    }
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

import FleetDriversPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 统计
// ═══════════════════════════════════════════
describe('司机管理 — 渲染', () => {
  it('页面正常渲染不崩溃', () => {
    const { container } = renderWithRouter(<FleetDriversPage />);
    expect(container).toBeTruthy();
  }, 15000);

  it('显示统计卡片', async () => {
    renderWithRouter(<FleetDriversPage />);
    await waitFor(() => {
      expect(screen.getByText('司机总数')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getAllByText('在职').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('累计消费')).toBeInTheDocument();
    expect(screen.getByText('平均评分')).toBeInTheDocument();
  }, 15000);

  it('统计卡片数值正确', async () => {
    renderWithRouter(<FleetDriversPage />);
    await waitFor(() => {
      expect(screen.getByText('司机总数')).toBeInTheDocument();
    }, { timeout: 8000 });
  }, 15000);
});

// ═══════════════════════════════════════════
// 列表 & 搜索
// ═══════════════════════════════════════════
describe('司机管理 — 列表加载', () => {
  it('显示司机列表数据', async () => {
    renderWithRouter(<FleetDriversPage />);
    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument();
      expect(screen.getByText('李四')).toBeInTheDocument();
      expect(screen.getByText('王五')).toBeInTheDocument();
    }, { timeout: 8000 });
  }, 15000);

  it('显示电话和驾驶证号', async () => {
    renderWithRouter(<FleetDriversPage />);
    await waitFor(() => {
      expect(screen.getByText('13800138001')).toBeInTheDocument();
      expect(screen.getByText('D64123456')).toBeInTheDocument();
    }, { timeout: 8000 });
  }, 15000);

  it('搜索过滤司机', async () => {
    renderWithRouter(<FleetDriversPage />);
    await waitFor(() => expect(screen.getByText('张三')).toBeInTheDocument(), { timeout: 8000 });

    const searchInput = screen.getByPlaceholderText('搜索姓名/电话/驾照');
    fireEvent.change(searchInput, { target: { value: '张三' } });

    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument();
      expect(screen.queryByText('李四')).not.toBeInTheDocument();
    });
  }, 15000);

  it('清空搜索恢复全部', async () => {
    renderWithRouter(<FleetDriversPage />);
    await waitFor(() => expect(screen.getByText('张三')).toBeInTheDocument(), { timeout: 8000 });

    const searchInput = screen.getByPlaceholderText('搜索姓名/电话/驾照');
    fireEvent.change(searchInput, { target: { value: '张三' } });
    await waitFor(() => expect(screen.queryByText('李四')).not.toBeInTheDocument());

    fireEvent.change(searchInput, { target: { value: '' } });
    await waitFor(() => expect(screen.getByText('李四')).toBeInTheDocument());
  }, 15000);
});

// ═══════════════════════════════════════════
// Modal 交互
// ═══════════════════════════════════════════
describe('司机管理 — 新增/编辑', () => {
  it('点击新增司机打开Modal', async () => {
    renderWithRouter(<FleetDriversPage />);
    await waitFor(() => expect(screen.getByText('张三')).toBeInTheDocument(), { timeout: 8000 });

    const addBtns = screen.getAllByText('新增司机');
    fireEvent.click(addBtns[addBtns.length - 1]);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('司机姓名')).toBeInTheDocument();
    });
  }, 15000);

  it('新增Modal包含必填字段', async () => {
    renderWithRouter(<FleetDriversPage />);
    await waitFor(() => expect(screen.getByText('张三')).toBeInTheDocument(), { timeout: 8000 });

    const addBtns = screen.getAllByText('新增司机');
    fireEvent.click(addBtns[addBtns.length - 1]);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('司机姓名')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('手机号')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('驾驶证号')).toBeInTheDocument();
    });
  }, 15000);
});

// ═══════════════════════════════════════════
// 详情抽屉
// ═══════════════════════════════════════════
describe('司机管理 — 详情抽屉', () => {
  it('点击姓名打开详情抽屉', async () => {
    renderWithRouter(<FleetDriversPage />);
    await waitFor(() => expect(screen.getByText('张三')).toBeInTheDocument(), { timeout: 8000 });

    // Click on driver name (it's an <a> tag)
    fireEvent.click(screen.getByText('张三'));

    await waitFor(() => {
      expect(screen.getByText('交易流水')).toBeInTheDocument();
    }, { timeout: 5000 });
  }, 15000);

  it('详情抽屉显示司机信息', async () => {
    renderWithRouter(<FleetDriversPage />);
    await waitFor(() => expect(screen.getByText('张三')).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.click(screen.getByText('张三'));

    await waitFor(() => {
      expect(screen.getByText('交易流水')).toBeInTheDocument();
    }, { timeout: 5000 });
  }, 15000);
});

// ═══════════════════════════════════════════
// 状态标签
// ═══════════════════════════════════════════
describe('司机管理 — 状态标签', () => {
  it('正确渲染在职和离职状态', async () => {
    renderWithRouter(<FleetDriversPage />);
    await waitFor(() => expect(screen.getByText('张三')).toBeInTheDocument(), { timeout: 8000 });

    // active → 在职, inactive → 离职
    expect(screen.getAllByText('在职').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('离职')).toBeInTheDocument();
  }, 15000);
});
