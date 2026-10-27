/**
 * 优惠券管理 — Vitest 单元测试
 * 测试覆盖: 优惠券列表 / 发放批次 / 核销记录 / CRUD交互
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
const mockCoupons = {
  items: [
    { id: 1, name: '新用户10元券', coupon_type: 'fixed', face_value: 10.00, min_order_amount: 20.00, max_discount_amount: null, applicable_user_types: 'app', applicable_stations: null, total_stock: 1000, remaining_stock: 800, per_user_limit: 1, valid_days: 30, start_time: '2026-07-01T00:00:00Z', end_time: '2026-12-31T23:59:59Z', is_active: true, description: '新用户首单优惠', created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z' },
    { id: 2, name: '充电9折券', coupon_type: 'percentage', face_value: 0.9, min_order_amount: 0, max_discount_amount: 50.00, applicable_user_types: null, applicable_stations: null, total_stock: 500, remaining_stock: 0, per_user_limit: 3, valid_days: 15, start_time: '2026-07-01T00:00:00Z', end_time: '2026-08-31T23:59:59Z', is_active: false, description: '充电9折', created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z' },
  ],
};

const mockBatches = {
  items: [
    { id: 1, coupon_id: 1, batch_name: '新用户发放', quantity: 200, user_type: 'app', user_ids: null, distributed_at: '2026-07-05T10:00:00Z', created_at: '2026-07-05T10:00:00Z' },
  ],
};

const mockUsages = {
  items: [
    { id: 1, coupon_id: 1, batch_id: 1, user_id: 100, user_type: 'app', coupon_code: 'CPN-ABC123', order_id: 501, status: 'used', discount_amount: 10.00, used_at: '2026-07-10T14:00:00Z', expires_at: '2026-08-10T00:00:00Z', received_at: '2026-07-05T10:00:00Z', created_at: '2026-07-05T10:00:00Z' },
    { id: 2, coupon_id: 2, user_id: 200, user_type: 'card', coupon_code: 'CPN-XYZ789', order_id: null, status: 'active', discount_amount: null, used_at: null, expires_at: '2026-08-15T00:00:00Z', received_at: '2026-07-06T10:00:00Z', created_at: '2026-07-06T10:00:00Z' },
  ],
};

const mockStats = {
  total_coupons: 2,
  total_stock: 1500,
  remaining_stock: 800,
  total_distributed: 700,
  total_used: 500,
  usage_rate: 71.4,
  total_discount_amount: 5000.00,
};

// ═══════════════════════════════════════════
// 导入组件
// ═══════════════════════════════════════════
import CouponManagement from '../index';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/operate/coupon/batches')) return Promise.resolve({ data: mockBatches });
    if (url.includes('/operate/coupon/usages')) return Promise.resolve({ data: mockUsages });
    if (url.includes('/operate/coupon/stats')) return Promise.resolve({ data: mockStats });
    if (url.includes('/operate/coupon')) return Promise.resolve({ data: mockCoupons });
    return Promise.resolve({ data: [] });
  });
  mockApi.post.mockResolvedValue({});
  mockApi.put.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
});

// ═══════════════════════════════════════════
// 测试: 页面渲染
// ═══════════════════════════════════════════
describe('优惠券管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><CouponManagement /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('渲染统计卡片', async () => {
    await act(async () => {
      render(<BrowserRouter><CouponManagement /></BrowserRouter>);
    });
    expect(screen.getByText('优惠券总数')).toBeInTheDocument();
    expect(screen.getByText('已发放')).toBeInTheDocument();
  });

  it('默认显示优惠券管理Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><CouponManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('新用户10元券')).toBeInTheDocument();
    });
    expect(screen.getByText('充电9折券')).toBeInTheDocument();
  });
});

// ═══════════════════════════════════════════
// 测试: 优惠券CRUD
// ═══════════════════════════════════════════
describe('优惠券管理 — CRUD', () => {
  it('优惠券类型标签正确显示', async () => {
    await act(async () => {
      render(<BrowserRouter><CouponManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('新用户10元券')).toBeInTheDocument();
    });
    expect(screen.getAllByText('固定金额').length).toBeGreaterThan(0);
    expect(screen.getAllByText('百分比折扣').length).toBeGreaterThan(0);
  });

  it('新建优惠券按钮打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><CouponManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('新用户10元券')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('新建优惠券'));

    await waitFor(() => {
      // Modal opens — look for form label that doesn't trigger DatePicker
      expect(screen.getByText('券类型')).toBeInTheDocument();
    });
  });

  it('编辑优惠券打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><CouponManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('新用户10元券')).toBeInTheDocument();
    });

    const editBtns = screen.getAllByText('编辑');
    fireEvent.click(editBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('券类型')).toBeInTheDocument();
    });
  });

  it('删除优惠券调用正确API', async () => {
    await act(async () => {
      render(<BrowserRouter><CouponManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('新用户10元券')).toBeInTheDocument();
    });

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
      expect(mockApi.delete).toHaveBeenCalledWith('/operate/coupon/1');
    });
  });
});

// ═══════════════════════════════════════════
// 测试: Tab切换
// ═══════════════════════════════════════════
describe('优惠券管理 — Tab切换', () => {
  it('切换到发放批次Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><CouponManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('新用户10元券')).toBeInTheDocument();
    });

    const batchTab = screen.getByText(/发放批次/);
    fireEvent.click(batchTab);

    await waitFor(() => {
      expect(screen.getByText('新用户发放')).toBeInTheDocument();
    });
  });

  it('切换到核销记录Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><CouponManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('新用户10元券')).toBeInTheDocument();
    });

    const usageTab = screen.getByText(/核销记录/);
    fireEvent.click(usageTab);

    await waitFor(() => {
      expect(screen.getByText('CPN-ABC123')).toBeInTheDocument();
    });
    expect(screen.getByText('CPN-XYZ789')).toBeInTheDocument();
  });

  it('发放按钮打开批次弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><CouponManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('新用户10元券')).toBeInTheDocument();
    });

    const distributeBtns = screen.getAllByText('发放');
    fireEvent.click(distributeBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('批量发放优惠券')).toBeInTheDocument();
    });
  });
});
