/**
 * 运营分析 6大报表 — Vitest 组件测试
 * 测试: Analytics index 渲染 + 6个子页面渲染 + Tab 切换
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══ Mock API ═══
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

import AnalyticsPage from '../index';
import RevenueOverview from '../RevenueOverview';
import FeeBreakdown from '../FeeBreakdown';
import UserRevenue from '../UserRevenue';
import StationRank from '../StationRank';
import TimeSlotAnalysis from '../TimeSlotAnalysis';
import CouponEffect from '../CouponEffect';

// ═══ beforeEach ═══
beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
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
            breakdown: [
              { fee_type: 'electricity', fee_name: '充电费', amount: 9000, percentage: 60 },
              { fee_type: 'service', fee_name: '服务费', amount: 4500, percentage: 30 },
              { fee_type: 'parking', fee_name: '停车费', amount: 750, percentage: 5 },
              { fee_type: 'occupancy', fee_name: '占桩费', amount: 375, percentage: 2.5 },
              { fee_type: 'reservation', fee_name: '预约费', amount: 375, percentage: 2.5 },
            ],
            total: 15000,
            trend: [{ period: '2026-07-20', electricity: 3000, service: 1500, parking: 250, occupancy: 125, reservation: 125 }],
          },
        },
      });
    }
    if (url.includes('/analytics/user-revenue')) {
      return Promise.resolve({
        data: {
          data: {
            breakdown: [
              { user_type: 'app', type_label: 'APP用户', revenue: 10000, kwh: 5000, orders: 80, unique_users: 50, avg_per_user: 200, orders_per_user: 1.6, recharge_rate: 60.0 },
              { user_type: 'card', type_label: '卡用户', revenue: 5000, kwh: 3000, orders: 40, unique_users: 30, avg_per_user: 166.67, orders_per_user: 1.33, recharge_rate: 33.3 },
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
              { station_id: 1, station_name: '测试站A', station_code: 'STA001', revenue: 8000, kwh: 4000, orders: 60, utilization_rate: 45.5, revenue_per_pile: 800, avg_revenue_per_order: 133.33 },
              { station_id: 2, station_name: '测试站B', station_code: 'STA002', revenue: 7000, kwh: 4000, orders: 60, utilization_rate: 38.2, revenue_per_pile: 700, avg_revenue_per_order: 116.67 },
            ],
          },
        },
      });
    }
    if (url.includes('/analytics/time-slot')) {
      return Promise.resolve({
        data: {
          data: {
            slots: [
              { slot_name: '尖峰', slot_key: 'peak', kwh: 2000, kwh_percentage: 25 },
              { slot_name: '平段', slot_key: 'flat', kwh: 4000, kwh_percentage: 50 },
              { slot_name: '谷段', slot_key: 'valley', kwh: 1500, kwh_percentage: 18.75 },
              { slot_name: '深谷', slot_key: 'trough', kwh: 500, kwh_percentage: 6.25 },
            ],
            summary: { total_kwh: 8000, total_electricity_fee: 6000, total_service_fee: 3000, electricity_fee_ratio: 66.67, service_fee_ratio: 33.33, total_orders: 120 },
          },
        },
      });
    }
    if (url.includes('/analytics/coupon-effect')) {
      return Promise.resolve({
        data: {
          data: {
            summary: { total_coupons_issued: 100, used_coupons: 60, expired_coupons: 20, redemption_rate: 60.0, coupon_orders: 60, total_discount_cost: 3000, total_revenue: 15000, total_orders: 120, roi: 4.0 },
            by_type: [{ coupon_type: 'fixed', type_name: '固定金额券', used_count: 60, total_cost: 3000 }],
          },
        },
      });
    }
    return Promise.resolve({ data: { data: {} } });
  });
  mockApi.post.mockResolvedValue({});
  mockApi.put.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
});

// ═══ Tests ═══

describe('运营分析 — Analytics 主页', () => {
  it('Analytics 主页渲染 6 个 Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><AnalyticsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('营收总览')).toBeInTheDocument();
    });
    expect(screen.getByText('费用占比')).toBeInTheDocument();
    expect(screen.getByText('用户收入')).toBeInTheDocument();
    expect(screen.getByText('站点排行')).toBeInTheDocument();
    expect(screen.getByText('时段分析')).toBeInTheDocument();
    expect(screen.getByText('优惠效果')).toBeInTheDocument();
  });

  it('默认显示营收总览 Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><AnalyticsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('总营收(元)')).toBeInTheDocument();
    });
  });
});

describe('营收总览 — RevenueOverview', () => {
  it('渲染统计卡片和趋势图', async () => {
    await act(async () => {
      render(<BrowserRouter><RevenueOverview /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('总营收(元)')).toBeInTheDocument();
    });
    expect(screen.getByText('总充电量(kWh)')).toBeInTheDocument();
    expect(screen.getByText('总订单数')).toBeInTheDocument();
    expect(screen.getByText('客单价(元)')).toBeInTheDocument();
  });
});

describe('费用占比 — FeeBreakdown', () => {
  it('渲染饼图和费用明细', async () => {
    await act(async () => {
      render(<BrowserRouter><FeeBreakdown /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('五项费用占比分析')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('费用总额(元)')).toBeInTheDocument();
    });
  });
});

describe('用户收入 — UserRevenue', () => {
  it('渲染用户类型表格', async () => {
    await act(async () => {
      render(<BrowserRouter><UserRevenue /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('用户收入分析')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('APP用户')).toBeInTheDocument();
    });
    expect(screen.getByText('卡用户')).toBeInTheDocument();
  });
});

describe('站点排行 — StationRank', () => {
  it('渲染站点排行表格', async () => {
    await act(async () => {
      render(<BrowserRouter><StationRank /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('站点收益排行')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('测试站A')).toBeInTheDocument();
    });
  });
});

describe('时段分析 — TimeSlotAnalysis', () => {
  it('渲染时段电量分布', async () => {
    await act(async () => {
      render(<BrowserRouter><TimeSlotAnalysis /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('时段收益分析(尖峰平谷)')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('总电量(kWh)')).toBeInTheDocument();
    });
  });
});

describe('优惠效果 — CouponEffect', () => {
  it('渲染 ROI 卡片和核销数据', async () => {
    await act(async () => {
      render(<BrowserRouter><CouponEffect /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('优惠效果分析')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('发券总数')).toBeInTheDocument();
    });
    expect(screen.getByText('已核销')).toBeInTheDocument();
    expect(screen.getByText('核销率')).toBeInTheDocument();
    expect(screen.getByText('ROI')).toBeInTheDocument();
  });
});

describe('Tab 切换测试', () => {
  it('从营收总览切到费用占比', async () => {
    await act(async () => {
      render(<BrowserRouter><AnalyticsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('总营收(元)')).toBeInTheDocument();
    });

    const allTabs = document.querySelectorAll('.ant-tabs-tab');
    const feeTab = Array.from(allTabs).find(t => t.textContent?.includes('费用占比'));
    expect(feeTab).toBeTruthy();
    if (feeTab) fireEvent.click(feeTab);

    await waitFor(() => {
      expect(screen.getByText('五项费用占比分析')).toBeInTheDocument();
    });
  });

  it('从营收总览切到优惠效果', async () => {
    await act(async () => {
      render(<BrowserRouter><AnalyticsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('总营收(元)')).toBeInTheDocument();
    });

    const allTabs = document.querySelectorAll('.ant-tabs-tab');
    const couponTab = Array.from(allTabs).find(t => t.textContent?.includes('优惠效果'));
    expect(couponTab).toBeTruthy();
    if (couponTab) fireEvent.click(couponTab);

    await waitFor(() => {
      expect(screen.getByText('发券总数')).toBeInTheDocument();
    });
  });
});
