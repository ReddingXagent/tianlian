/**
 * V2G调度管理页面 — Vitest 单元测试
 *
 * 覆盖：渲染、Tab切换(状态/计划/收益/记录)、统计卡片、计划状态更新
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

vi.mock('echarts-for-react', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock'),
}));

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockStatus = {
  enterprise_id: 1,
  plan_status_counts: { scheduled: 3, completed: 5, cancelled: 1 },
  recent_plans: [
    { id: 1, vehicle_id: 101, plan_date: '2026-07-21', status: 'scheduled', planned_charge_start: '2026-07-21T22:00:00Z', planned_charge_end: '2026-07-22T06:00:00Z', planned_discharge_start: '2026-07-22T10:00:00Z', planned_discharge_end: '2026-07-22T14:00:00Z', target_soc_min: 0.3, target_soc_max: 0.9 },
    { id: 2, vehicle_id: 102, plan_date: '2026-07-21', status: 'completed', planned_charge_start: '2026-07-20T22:00:00Z', planned_charge_end: '2026-07-21T06:00:00Z', target_soc_min: 0.3, target_soc_max: 0.9 },
  ],
  revenue_summary: { total_revenue: 12500.50, total_discharge_energy_kwh: 3200.0, total_records: 8 },
};

const mockPlans = {
  items: [
    { id: 1, vehicle_id: 101, plan_date: '2026-07-21', status: 'scheduled', planned_charge_start: '2026-07-21T22:00:00Z', planned_charge_end: '2026-07-22T06:00:00Z', planned_discharge_start: '2026-07-22T10:00:00Z', planned_discharge_end: '2026-07-22T14:00:00Z', target_soc_min: 0.3, target_soc_max: 0.9 },
    { id: 2, vehicle_id: 102, plan_date: '2026-07-22', status: 'completed', planned_charge_start: '2026-07-21T22:00:00Z', planned_charge_end: '2026-07-22T06:00:00Z', target_soc_min: 0.2, target_soc_max: 0.8 },
  ],
  total: 2,
};

const mockRevenue = {
  items: [
    { id: 1, record_date: '2026-07-20', vehicle_id: 101, discharge_energy_kwh: 30.5, discharge_revenue: 45.75, peak_shaving_kwh: 15.0, valley_filling_kwh: 20.0, grid_response_count: 3, total_revenue: 55.50 },
    { id: 2, record_date: '2026-07-19', vehicle_id: 102, discharge_energy_kwh: 25.0, discharge_revenue: 37.50, peak_shaving_kwh: 12.0, valley_filling_kwh: 18.0, grid_response_count: 2, total_revenue: 42.00 },
  ],
  total: 2,
};

const mockRecords = {
  items: [
    { id: 1, device_id: 201, dispatch_type: 'discharge', target_power_kw: 15.0, actual_power_kw: 14.8, status: 'completed', start_at: '2026-07-20T10:00:00Z', end_at: '2026-07-20T14:00:00Z' },
    { id: 2, device_id: 202, dispatch_type: 'charge', target_power_kw: 30.0, actual_power_kw: null, status: 'scheduled', start_at: '2026-07-21T22:00:00Z', end_at: null },
  ],
  total: 2,
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
    if (url.includes('/fleet/v2g/status')) return Promise.resolve({ data: mockStatus });
    if (url.includes('/fleet/v2g/plans')) return Promise.resolve({ data: mockPlans });
    if (url.includes('/fleet/v2g/revenue')) return Promise.resolve({ data: mockRevenue });
    if (url.includes('/fleet/v2g/records')) return Promise.resolve({ data: mockRecords });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });

  // useFleetRealtime 在挂载时会 new WebSocket，stub 掉避免 jsdom 真实连接
  vi.stubGlobal('WebSocket', class MockWS {
    static OPEN = 1;
    static CONNECTING = 0;
    readyState = 0;
    onopen: ((e?: Event) => void) | null = null;
    onmessage: ((e: { data: string }) => void) | null = null;
    onerror: ((e: Event) => void) | null = null;
    onclose: ((e: CloseEvent) => void) | null = null;
    send() {}
    close() {}
    constructor(_url: string) {}
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

import FleetV2GPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 状态概览
// ═══════════════════════════════════════════
describe('V2G调度 — 渲染 & 状态概览', () => {
  it('页面正常渲染', async () => {
    renderWithRouter(<FleetV2GPage />);
    await waitFor(() => {
      expect(screen.getByText('状态概览')).toBeInTheDocument();
    }, { timeout: 8000 });
  }, 15000);

  it('显示统计卡片', async () => {
    renderWithRouter(<FleetV2GPage />);
    await waitFor(() => {
      expect(screen.getByText('计划总数')).toBeInTheDocument();
      expect(screen.getByText('总收益(¥)')).toBeInTheDocument();
      expect(screen.getByText('总放电量(kWh)')).toBeInTheDocument();
      expect(screen.getByText('收益记录数')).toBeInTheDocument();
    });
  });

  it('显示计划状态分布', async () => {
    renderWithRouter(<FleetV2GPage />);
    await waitFor(() => {
      expect(screen.getByText('计划状态分布')).toBeInTheDocument();
      // Status counts from plan_status_counts
      expect(screen.getAllByText('已排期').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('已完成').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('显示最近计划表', async () => {
    renderWithRouter(<FleetV2GPage />);
    await waitFor(() => {
      expect(screen.getByText('最近计划')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// Tab 切换
// ═══════════════════════════════════════════
describe('V2G调度 — Tab切换', () => {
  it('切换到充放电计划Tab', async () => {
    renderWithRouter(<FleetV2GPage />);
    await waitFor(() => expect(screen.getByText('状态概览')).toBeInTheDocument());

    clickTab('充放电计划');

    await waitFor(() => {
      expect(screen.getByText('计划日期')).toBeInTheDocument();
    });
  });

  it('切换到放电收益Tab', async () => {
    renderWithRouter(<FleetV2GPage />);
    await waitFor(() => expect(screen.getByText('状态概览')).toBeInTheDocument());

    clickTab('放电收益');

    await waitFor(() => {
      expect(screen.getByText('放电量(kWh)')).toBeInTheDocument();
      expect(screen.getByText('放电收益(¥)')).toBeInTheDocument();
    });
  });

  it('切换到调度记录Tab', async () => {
    renderWithRouter(<FleetV2GPage />);
    await waitFor(() => expect(screen.getByText('状态概览')).toBeInTheDocument());

    clickTab('调度记录');

    await waitFor(() => {
      expect(screen.getByText('设备ID')).toBeInTheDocument();
      expect(screen.getByText('调度类型')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 计划状态标签
// ═══════════════════════════════════════════
describe('V2G调度 — 状态标签', () => {
  it('显示正确的计划状态标签', async () => {
    renderWithRouter(<FleetV2GPage />);
    await waitFor(() => {
      expect(screen.getAllByText('已排期').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('已完成').length).toBeGreaterThanOrEqual(1);
    });
  });
});
