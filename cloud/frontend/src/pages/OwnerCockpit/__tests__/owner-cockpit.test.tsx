/**
 * 经营驾驶舱 OwnerCockpit — Vitest 组件测试
 * 覆盖: KPI卡片渲染 / /owner-cockpit/overview 调用 / 站点明细表 / 空数据不崩溃
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API (页面读 res.data, 故 mock 返回 { data: payload })
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../api', () => ({ default: mockApi }));

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

import OwnerCockpit from '../index';

const PAYLOAD = {
  period: { start_date: '2026-06-29', end_date: '2026-07-29' },
  caliber: {
    revenue: 'Σ paid_amount',
    purchase_cost: 'Σ charged_kwh × 0.6',
    roi_rate: '累计毛利/投资额',
    gross_margin: 'revenue - purchase_cost',
    utilization_rate: 'Σ duration / (guns × days × 1440)',
    payback_months: 'total_cost / 月均毛利',
  },
  summary: {
    revenue: 12800.5, energy_kwh: 6000, order_count: 80, avg_per_order: 160,
    purchase_cost: 3600, gross_margin: 9200.5, gross_margin_rate: 71.9,
    utilization_rate: 42.35,
  },
  investment: {
    total_cost: 300000, cumulative_gross_margin: 45600,
    roi_rate: 15.2, payback_months: 65.7,
  },
  stations: [
    { station_id: 1, station_name: '资方站A', revenue: 8000, energy_kwh: 4000, order_count: 50,
      gross_margin: 5600, gross_margin_rate: 70, utilization_rate: 45.2, gun_count: 2,
      total_cost: 100000, cumulative_gross_margin: 28000, roi_rate: 28 },
    { station_id: 2, station_name: '资方站B', revenue: 4800, energy_kwh: 2000, order_count: 30,
      gross_margin: 3600, gross_margin_rate: 75, utilization_rate: 38.1, gun_count: 4,
      total_cost: 200000, cumulative_gross_margin: 17600, roi_rate: 8.8 },
  ],
  trend: [
    { date: '2026-07-28', revenue: 8000, energy_kwh: 4000, gross_margin: 5600 },
    { date: '2026-07-29', revenue: 4800, energy_kwh: 2000, gross_margin: 3600 },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/owner-cockpit/overview')) {
      return Promise.resolve({ data: PAYLOAD });
    }
    return Promise.resolve({ data: null });
  });
  mockApi.post.mockResolvedValue({});
  mockApi.put.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
});

describe('经营驾驶舱 OwnerCockpit — 渲染', () => {
  it('页面可渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><OwnerCockpit /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('渲染经营 KPI 卡片标题', async () => {
    await act(async () => {
      render(<BrowserRouter><OwnerCockpit /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('总收入')).toBeInTheDocument();
    });
    expect(screen.getByText('毛利')).toBeInTheDocument();
    // '毛利率' 同时出现在 KPI 卡片与表格列头, 用 getAllByText
    expect(screen.getAllByText('毛利率').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('枪位利用率')).toBeInTheDocument();
  });

  it('挂载时调用 /owner-cockpit/overview', async () => {
    await act(async () => {
      render(<BrowserRouter><OwnerCockpit /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith(
        '/owner-cockpit/overview',
        expect.objectContaining({
          params: expect.objectContaining({
            start_date: expect.any(String),
            end_date: expect.any(String),
          }),
        }),
      );
    });
  });

  it('渲染站点明细表与站点名', async () => {
    await act(async () => {
      render(<BrowserRouter><OwnerCockpit /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('资方站A')).toBeInTheDocument();
    });
    expect(screen.getByText('资方站B')).toBeInTheDocument();
    expect(screen.getByText(/站点经营明细/)).toBeInTheDocument();
  });

  it('渲染趋势图区块 (echarts mock)', async () => {
    await act(async () => {
      render(<BrowserRouter><OwnerCockpit /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText(/收入 · 毛利趋势/)).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('echarts-mock').length).toBeGreaterThanOrEqual(1);
  });
});

describe('经营驾驶舱 OwnerCockpit — 区间切换', () => {
  it('切换到近90天后以新区间重新拉取', async () => {
    await act(async () => {
      render(<BrowserRouter><OwnerCockpit /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('总收入')).toBeInTheDocument();
    });

    // 打开 Select 并点选"近90天"
    const selector = document.querySelector('.ant-select-selector');
    if (selector) fireEvent.mouseDown(selector);
    await waitFor(() => {
      const opt = Array.from(document.querySelectorAll('.ant-select-item-option')).find(
        (el) => el.textContent?.includes('近90天'),
      );
      if (opt) fireEvent.click(opt);
    });

    await waitFor(() => {
      const call = mockApi.get.mock.calls.find(
        (c: any[]) => c[0] === '/owner-cockpit/overview',
      );
      // 至少有一次调用 (可能多次: 初始 + 切换后)
      expect(call).toBeTruthy();
    });
    // 切换后调用次数应增加
    expect(mockApi.get.mock.calls.filter((c: any[]) => c[0] === '/owner-cockpit/overview').length).toBeGreaterThanOrEqual(2);
  });
});

describe('经营驾驶舱 OwnerCockpit — 空数据', () => {
  it('API 返回空时不崩溃, KPI 回退 0 仍渲染', async () => {
    mockApi.get.mockReset();
    mockApi.get.mockResolvedValue({ data: null });
    await act(async () => {
      render(<BrowserRouter><OwnerCockpit /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('总收入')).toBeInTheDocument();
    });
  });
});
