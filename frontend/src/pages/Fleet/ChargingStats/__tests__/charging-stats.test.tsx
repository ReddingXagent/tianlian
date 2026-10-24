/**
 * 充电统计页面 — Vitest 单元测试
 *
 * 覆盖：渲染、车队汇总卡片、车辆排行/场站分布、Tab切换(车队汇总/单车统计)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
    patch: vi.fn(),
  },
}));

vi.mock('../../../../api', () => ({ default: mockApi }));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

vi.mock('echarts-for-react', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock'),
}));

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockEnterprises = [{ id: 1, name: '顺达物流' }];

const mockVehicles = [
  { id: 101, plate_number: '京A·12345' },
  { id: 102, plate_number: '京A·23456' },
];

const mockFleetStats = {
  enterprise_id: 1,
  summary: {
    total_orders: 120, total_kwh: 15600, total_amount: 13800.5,
    avg_kwh_per_order: 130, avg_amount_per_order: 115,
  },
  active_vehicles: 8,
  top_vehicles: [
    { vehicle_id: 101, plate_number: '京A·12345', charged_kwh: 4200, total_amount: 3700, order_count: 30 },
    { vehicle_id: 102, plate_number: '京A·23456', charged_kwh: 3100, total_amount: 2800, order_count: 22 },
  ],
  station_distribution: [
    { station_id: 1, station_name: '东郊充电站', charged_kwh: 9000, order_count: 70 },
    { station_id: 2, station_name: '西站快充', charged_kwh: 6600, order_count: 50 },
  ],
};

const mockVehicleStats = {
  vehicle: { id: 101, plate_number: '京A·12345', vin: 'LSGAB52L7DF000001' },
  summary: {
    total_orders: 30, total_kwh: 4200, total_amount: 3700,
    avg_kwh_per_order: 140, avg_amount_per_order: 123.3,
  },
  monthly_trend: [
    { month: '2026-05', charged_kwh: 1300, total_amount: 1200 },
    { month: '2026-06', charged_kwh: 1400, total_amount: 1250 },
  ],
};

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

function clickTab(label: string) {
  const tabs = document.querySelectorAll('.ant-tabs-tab');
  for (let i = 0; i < tabs.length; i++) {
    if (tabs[i].textContent?.includes(label)) {
      fireEvent.click(tabs[i]);
      return;
    }
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/fleet/enterprises')) return Promise.resolve({ data: mockEnterprises });
    if (url.includes('/charging-stats') && url.includes('/vehicles/')) return Promise.resolve({ data: mockVehicleStats });
    if (url.includes('/charging-stats')) return Promise.resolve({ data: mockFleetStats });
    if (url.includes('/vehicles')) return Promise.resolve({ data: mockVehicles });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

import FleetChargingStatsPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 车队汇总
// ═══════════════════════════════════════════
describe('充电统计 — 渲染', () => {
  it('页面正常渲染不崩溃', () => {
    const { container } = renderWithRouter(<FleetChargingStatsPage />);
    expect(container).toBeTruthy();
  }, 15000);

  it('显示车队汇总统计卡片', async () => {
    renderWithRouter(<FleetChargingStatsPage />);
    await waitFor(() => {
      expect(screen.getByText('总电量(kWh)')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getByText('总费用(¥)')).toBeInTheDocument();
    // 「充电次数」同时是卡片标题与车辆排行表列名
    expect(screen.getAllByText('充电次数').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('活跃车辆')).toBeInTheDocument();
  }, 15000);

  it('渲染车辆排行与场站分布', async () => {
    renderWithRouter(<FleetChargingStatsPage />);
    await waitFor(() => {
      expect(screen.getByText('车辆排行（充电量 Top）')).toBeInTheDocument();
      expect(screen.getByText('场站分布')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getByText('东郊充电站')).toBeInTheDocument();
    expect(screen.getByText('西站快充')).toBeInTheDocument();
  }, 15000);
});

// ═══════════════════════════════════════════
// Tab 切换
// ═══════════════════════════════════════════
describe('充电统计 — Tab切换', () => {
  it('切换到单车统计Tab', async () => {
    renderWithRouter(<FleetChargingStatsPage />);
    await waitFor(() => expect(screen.getByText('总电量(kWh)')).toBeInTheDocument(), { timeout: 8000 });

    clickTab('单车统计');

    await waitFor(() => {
      expect(screen.getByText('月度充电趋势')).toBeInTheDocument();
      expect(screen.getByText('平均单次电量(kWh)')).toBeInTheDocument();
    });
  }, 15000);
});
