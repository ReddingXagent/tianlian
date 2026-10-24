/**
 * 运营看板 Dashboard — Vitest 组件测试
 * 测试: KPI卡片渲染 / 3个聚合API调用 / 区间切换重取 / 站点排行Top10
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

vi.mock('../../../../api', () => ({ default: mockApi }));

vi.mock('echarts-for-react', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock'),
}));

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

import OperateDashboard from '../index';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string, opts?: any) => {
    const range = opts?.params?.range || 'day';
    if (url.includes('/analytics/revenue')) {
      return Promise.resolve({
        data: {
          data: {
            summary: { total_revenue: 15000, total_kwh: 8000, total_orders: 120, avg_per_order: 125 },
            trend: [{ period: '2026-07-20', revenue: 5000, kwh: 2500, orders: 40 }],
          },
        },
      });
    }
    if (url.includes('/analytics/fee-breakdown')) {
      return Promise.resolve({
        data: {
          data: {
            total: 15000,
            breakdown: [
              { fee_type: 'electricity', fee_name: '充电费', amount: 9000, percentage: 60 },
              { fee_type: 'service', fee_name: '服务费', amount: 4500, percentage: 30 },
              { fee_type: 'parking', fee_name: '停车费', amount: 750, percentage: 5 },
              { fee_type: 'occupancy', fee_name: '占桩费', amount: 375, percentage: 2.5 },
              { fee_type: 'reservation', fee_name: '预约费', amount: 375, percentage: 2.5 },
            ],
          },
        },
      });
    }
    if (url.includes('/analytics/station-rank')) {
      return Promise.resolve({
        data: {
          data: {
            ranking: [
              { station_id: 1, station_name: `郑州东站_${range}`, revenue: 5000, kwh: 2500, orders: 40, utilization_rate: 75, revenue_per_pile: 500, avg_revenue_per_order: 125 },
              { station_id: 2, station_name: '郑州火车站', revenue: 3000, kwh: 1500, orders: 25, utilization_rate: 50, revenue_per_pile: 300, avg_revenue_per_order: 120 },
            ],
          },
        },
      });
    }
    return Promise.resolve({ data: { data: null } });
  });
  mockApi.post.mockResolvedValue({});
  mockApi.put.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
});

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
describe('运营看板 Dashboard — 渲染', () => {
  it('页面可渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><OperateDashboard /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('渲染4个KPI卡片标题', async () => {
    await act(async () => {
      render(<BrowserRouter><OperateDashboard /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('总营收')).toBeInTheDocument();
    });
    expect(screen.getByText('总充电量')).toBeInTheDocument();
    expect(screen.getByText('总订单数')).toBeInTheDocument();
    expect(screen.getByText('客单价')).toBeInTheDocument();
  });

  it('挂载时调用3个聚合API', async () => {
    await act(async () => {
      render(<BrowserRouter><OperateDashboard /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/analytics/revenue', expect.objectContaining({ params: expect.any(Object) }));
    });
    const urls = mockApi.get.mock.calls.map((c: any[]) => c[0]);
    expect(urls).toContain('/analytics/revenue');
    expect(urls.some((u: string) => u.includes('/analytics/fee-breakdown'))).toBe(true);
    expect(urls.some((u: string) => u.includes('/analytics/station-rank'))).toBe(true);
  });

  it('渲染站点收益排行Top10区块与站点名', async () => {
    await act(async () => {
      render(<BrowserRouter><OperateDashboard /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('郑州火车站')).toBeInTheDocument();
    });
    expect(screen.getByText(/站点收益排行/)).toBeInTheDocument();
  });
});

describe('运营看板 Dashboard — 区间切换', () => {
  it('切换到按月后以 range=month 重新拉取', async () => {
    await act(async () => {
      render(<BrowserRouter><OperateDashboard /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('总营收')).toBeInTheDocument();
    });

    // 切换区间为"按月"
    const monthTab = Array.from(document.querySelectorAll('.ant-select-item-option, .ant-segmented-item, [role="tab"], .ant-radio-button-wrapper'))
      .find((el) => el.textContent?.includes('月'));
    // 优先尝试 Select 下拉(打开)
    const rangeSelector = document.querySelector('.ant-select-selector');
    if (rangeSelector) {
      fireEvent.mouseDown(rangeSelector);
    }
    await waitFor(() => {
      const opt = Array.from(document.querySelectorAll('.ant-select-item-option')).find((el) => el.textContent?.includes('月'));
      if (opt) fireEvent.click(opt);
    });

    // 至少有一次以 month 调用 revenue
    await waitFor(() => {
      const monthCall = mockApi.get.mock.calls.some(
        (c: any[]) => c[0] === '/analytics/revenue' && c[1]?.params?.range === 'month',
      );
      expect(monthCall).toBe(true);
    });
  });
});

describe('运营看板 Dashboard — 空数据', () => {
  it('API返回空时不崩溃', async () => {
    mockApi.get.mockReset();
    mockApi.get.mockResolvedValue({ data: { data: null } });
    await act(async () => {
      render(<BrowserRouter><OperateDashboard /></BrowserRouter>);
    });
    // KPI 回退为 0 仍渲染标题
    await waitFor(() => {
      expect(screen.getByText('总营收')).toBeInTheDocument();
    });
  });
});
