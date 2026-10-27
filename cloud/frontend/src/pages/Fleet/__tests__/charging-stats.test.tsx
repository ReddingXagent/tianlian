/**
 * 车队 - 充电统计页面 Vitest 组件测试
 *
 * 覆盖：渲染+车队汇总卡片 / 车辆排行+场站分布 / 单车统计卡片+趋势图 / 企业切换重拉 / 错误降级
 *
 * mock 模式对齐 vehicle-insurance.test.tsx；字段契约对齐 backend fleet_charging_stats.py
 * 注：响应拦截器会自动剥 success_response 外层，故 mock 直接返回业务对象。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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

vi.mock('../../../api', () => ({ default: mockApi }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('echarts-for-react', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock'),
}));

// ═══════════════════════════════════════════
// 测试数据（字段对齐 backend success_response.data）
// ═══════════════════════════════════════════
const mockEnterprises = {
  items: [
    { id: 1, name: '顺达物流有限公司' },
    { id: 2, name: '鹏程货运公司' },
  ],
};

const mockVehicles = {
  items: [
    { id: 101, plate_number: '京A12345' },
    { id: 102, plate_number: '京B67890' },
  ],
};

// 车队级汇总
const mockFleetStats = {
  enterprise_id: 1,
  summary: {
    total_orders: 50,
    total_kwh: 5000,
    total_amount: 6000,
    avg_kwh_per_order: 100,
    avg_amount_per_order: 120,
  },
  active_vehicles: 2,
  top_vehicles: [
    { vehicle_id: 101, plate_number: '京A12345', charged_kwh: 3000, total_amount: 3600, order_count: 30 },
    { vehicle_id: 102, plate_number: '京B67890', charged_kwh: 2000, total_amount: 2400, order_count: 20 },
  ],
  station_distribution: [
    { station_id: 1, station_name: '东站充电站', charged_kwh: 3500, order_count: 35 },
    { station_id: 2, station_name: '西站充电站', charged_kwh: 1500, order_count: 15 },
  ],
};

// 单车统计
const mockVehicleStats = {
  vehicle: { id: 101, plate_number: '京A12345', vin: 'LVSHFFAL1HF000001' },
  summary: {
    total_orders: 30,
    total_kwh: 3000,
    total_amount: 3600,
    avg_kwh_per_order: 100,
    avg_amount_per_order: 120,
  },
  monthly_trend: [
    { month: '2026-01', charged_kwh: 1000, total_amount: 1200 },
    { month: '2026-02', charged_kwh: 2000, total_amount: 2400 },
  ],
};

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

const defaultGet = (url: string): Promise<any> => {
  if (url.includes('/fleet/enterprises')) return Promise.resolve({ data: mockEnterprises });
  // 顺序敏感：单车统计 URL 同时含 vehicles 与 charging-stats，需先匹配
  if (url.includes('/charging-stats') && url.includes('/vehicles/')) return Promise.resolve({ data: mockVehicleStats });
  if (url.includes('/charging-stats')) return Promise.resolve({ data: mockFleetStats });
  if (url.includes('/enterprises/') && url.includes('/vehicles')) return Promise.resolve({ data: mockVehicles });
  return Promise.resolve({ data: { items: [] } });
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mockApi.get.mockImplementation(defaultGet);
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
});

import FleetChargingStatsPage from '../ChargingStats';

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
describe('FleetChargingStatsPage 充电统计', () => {
  it('1. 渲染页面，默认选首个企业并拉取车队汇总统计卡片', async () => {
    renderWithRouter(<FleetChargingStatsPage />);

    await waitFor(() => {
      expect(screen.getByText('总电量(kWh)')).toBeInTheDocument();
    }, { timeout: 3000 });
    expect(screen.getByText('总费用(¥)')).toBeInTheDocument();
    // 「充电次数」同时出现在卡片标题与排行/场站表头，断言至少一处
    expect(screen.getAllByText('充电次数').length).toBeGreaterThan(0);
    expect(screen.getByText('活跃车辆')).toBeInTheDocument();

    // 默认企业 id=1 → 调用 /enterprises/1/charging-stats
    const fleetCalls = mockApi.get.mock.calls.filter(c => c[0].includes('/charging-stats') && !c[0].includes('/vehicles/'));
    expect(fleetCalls.some(c => c[0].includes('/enterprises/1/charging-stats'))).toBe(true);
  });

  it('2. 车队汇总展示车辆排行与场站分布表格', async () => {
    renderWithRouter(<FleetChargingStatsPage />);

    // 车辆排行：车牌
    await waitFor(() => {
      expect(screen.getByText('京A12345')).toBeInTheDocument();
    }, { timeout: 3000 });
    expect(screen.getByText('京B67890')).toBeInTheDocument();
    // 场站分布：场站名
    expect(screen.getByText('东站充电站')).toBeInTheDocument();
    expect(screen.getByText('西站充电站')).toBeInTheDocument();
  });

  it('3. 切到「单车统计」Tab，自动选车并渲染单车卡片+趋势图', async () => {
    renderWithRouter(<FleetChargingStatsPage />);

    // 等车队汇总渲染完成（说明企业已就绪）
    await waitFor(() => expect(screen.getByText('京A12345')).toBeInTheDocument(), { timeout: 3000 });

    // 切换到单车统计 Tab
    fireEvent.click(screen.getByText('单车统计'));

    // 单车卡片标题（平均单次电量 仅在单车统计出现，用作切换成功的标志）
    await waitFor(() => {
      expect(screen.getByText('平均单次电量(kWh)')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 单车统计接口被调用（含 vehicles 与 charging-stats）
    const vehicleCalls = mockApi.get.mock.calls.filter(c => c[0].includes('/vehicles/') && c[0].includes('/charging-stats'));
    expect(vehicleCalls.length).toBeGreaterThan(0);

    // 趋势图渲染
    expect(screen.getByTestId('echarts-mock')).toBeInTheDocument();
  });

  it('4. 切换企业后以新企业ID重新拉取车队汇总', async () => {
    const { container } = renderWithRouter(<FleetChargingStatsPage />);

    await waitFor(() => expect(screen.getByText('京A12345')).toBeInTheDocument(), { timeout: 3000 });

    // 第一个 Select 为企业选择
    const enterpriseSelector = container.querySelectorAll('.ant-select-selector')[0] as HTMLElement;
    fireEvent.mouseDown(enterpriseSelector);

    const dropdown = await waitFor(() => {
      const el = document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)') as HTMLElement;
      expect(el).toBeInTheDocument();
      return el;
    });
    fireEvent.click(within(dropdown).getByText('鹏程货运公司'));

    await waitFor(() => {
      const fleetCalls = mockApi.get.mock.calls.filter(c => c[0].includes('/charging-stats') && !c[0].includes('/vehicles/'));
      expect(fleetCalls.some(c => c[0].includes('/enterprises/2/charging-stats'))).toBe(true);
    }, { timeout: 3000 });
  });

  it('5. 车队汇总接口报错时降级为空态（不崩溃，卡片标题保留）', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/charging-stats') && !url.includes('/vehicles/')) return Promise.reject(new Error('boom'));
      return defaultGet(url);
    });

    renderWithRouter(<FleetChargingStatsPage />);

    await waitFor(() => {
      expect(screen.getByText('总电量(kWh)')).toBeInTheDocument();
    }, { timeout: 3000 });
    // 接口失败 → 排行数据不渲染
    expect(screen.queryByText('京A12345')).not.toBeInTheDocument();
  });
});
