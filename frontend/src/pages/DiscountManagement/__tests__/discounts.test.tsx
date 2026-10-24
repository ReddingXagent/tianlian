/**
 * 折扣管理 — Vitest 单元测试
 * 测试覆盖: 折扣方案列表 / 折扣组列表 / Tab切换 / CRUD交互
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
const mockDiscounts = {
  items: [
    { id: 1, name: 'APP用户9折', discount_type: 'percentage', discount_rate: 0.9, applicable_user_types: 'app', min_consumption: 10.00, max_discount_amount: null, start_time: '2026-07-01T00:00:00Z', end_time: '2026-12-31T23:59:59Z', priority: 10, is_active: true, description: 'APP用户专属折扣', created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z' },
    { id: 2, name: '企业满减', discount_type: 'fixed', discount_rate: 5.00, applicable_user_types: 'enterprise', min_consumption: 50.00, max_discount_amount: 20.00, start_time: '2026-07-01T00:00:00Z', end_time: '2026-12-31T23:59:59Z', priority: 20, is_active: false, description: '企业用户满50减5', created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z' },
  ],
};

const mockGroups = {
  items: [
    { id: 1, name: 'APP用户组A', discount_id: 1, user_type: 'app', user_ids: null, station_ids: '1,2,3', priority: 10, is_active: true, created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z' },
    { id: 2, name: '企业用户组B', discount_id: 2, user_type: 'enterprise', user_ids: '10,20', station_ids: null, priority: 20, is_active: true, created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z' },
  ],
};

// ═══════════════════════════════════════════
// 导入组件
// ═══════════════════════════════════════════
import DiscountManagement from '../index';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/operate/discount/groups')) return Promise.resolve({ data: mockGroups });
    if (url.includes('/operate/discount')) return Promise.resolve({ data: mockDiscounts });
    return Promise.resolve({ data: [] });
  });
  mockApi.post.mockResolvedValue({});
  mockApi.put.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
});

// ═══════════════════════════════════════════
// 测试: 页面渲染
// ═══════════════════════════════════════════
describe('折扣管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><DiscountManagement /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('渲染统计卡片', async () => {
    await act(async () => {
      render(<BrowserRouter><DiscountManagement /></BrowserRouter>);
    });
    expect(screen.getByText('折扣方案总数')).toBeInTheDocument();
    expect(screen.getByText('折扣组总数')).toBeInTheDocument();
    expect(screen.getByText('启用中')).toBeInTheDocument();
    expect(screen.getByText('停用中')).toBeInTheDocument();
  });

  it('默认显示折扣方案Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><DiscountManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('APP用户9折')).toBeInTheDocument();
    });
    expect(screen.getByText('企业满减')).toBeInTheDocument();
  });
});

// ═══════════════════════════════════════════
// 测试: 折扣方案
// ═══════════════════════════════════════════
describe('折扣方案 — 列表与交互', () => {
  it('折扣类型标签正确显示', async () => {
    await act(async () => {
      render(<BrowserRouter><DiscountManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('APP用户9折')).toBeInTheDocument();
    });
    expect(screen.getAllByText('百分比折扣').length).toBeGreaterThan(0);
    expect(screen.getAllByText('固定金额').length).toBeGreaterThan(0);
  });

  it('新建折扣方案按钮打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><DiscountManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('APP用户9折')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('新建折扣方案'));

    await waitFor(() => {
      // Modal opens — look for form label
      expect(screen.getByText('折扣类型')).toBeInTheDocument();
    });
  });

  it('编辑折扣方案打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><DiscountManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('APP用户9折')).toBeInTheDocument();
    });

    const editBtns = screen.getAllByText('编辑');
    fireEvent.click(editBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('折扣类型')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 测试: Tab切换到折扣组
// ═══════════════════════════════════════════
describe('折扣电价组 — Tab切换', () => {
  it('切换到折扣组Tab显示组数据', async () => {
    await act(async () => {
      render(<BrowserRouter><DiscountManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('APP用户9折')).toBeInTheDocument();
    });

    // 找到折扣电价组 Tab 并点击
    const groupTab = screen.getByText(/折扣电价组/);
    fireEvent.click(groupTab);

    await waitFor(() => {
      expect(screen.getByText('APP用户组A')).toBeInTheDocument();
    });
    expect(screen.getByText('企业用户组B')).toBeInTheDocument();
  });
});

// ═══════════════════════════════════════════
// 测试: 删除操作
// ═══════════════════════════════════════════
describe('折扣管理 — 删除操作', () => {
  it('删除折扣方案调用正确API', async () => {
    await act(async () => {
      render(<BrowserRouter><DiscountManagement /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('APP用户9折')).toBeInTheDocument();
    });

    const deleteBtns = screen.getAllByText('删除');
    fireEvent.click(deleteBtns[0]);

    // Popconfirm 确认
    await waitFor(() => {
      expect(screen.getByText('确认删除？')).toBeInTheDocument();
    });

    const popconfirmBtns = document.querySelectorAll('.ant-popconfirm-buttons .ant-btn-primary');
    expect(popconfirmBtns.length).toBeGreaterThan(0);
    await act(async () => {
      fireEvent.click(popconfirmBtns[0]);
    });

    await waitFor(() => {
      expect(mockApi.delete).toHaveBeenCalledWith('/operate/discount/1');
    });
  });
});
