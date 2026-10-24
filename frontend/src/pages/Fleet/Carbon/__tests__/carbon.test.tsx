/**
 * 碳排放管理页面 — Vitest 单元测试
 *
 * 覆盖：渲染、Tab切换(概览/明细/报告/因子)、统计卡片、排放因子Modal
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
const mockOverview = {
  enterprise: { id: 1, name: '顺达物流' },
  year: 2026,
  total_charge_kwh: 45678.9,
  total_reduction_kg: 12345.6,
  total_fuel_saved_liters: 25580.0,
  vehicle_count: 8,
  monthly_trend: [
    { month: 1, charge_kwh: 3000, reduction_kg: 800 },
    { month: 2, charge_kwh: 3500, reduction_kg: 950 },
    { month: 3, charge_kwh: 4200, reduction_kg: 1100 },
  ],
};

const mockDetails = {
  items: [
    { id: 1, record_date: '2026-07-01', vehicle_id: 101, charge_energy_kwh: 45.5, grid_factor: 0.5810, carbon_reduction_kg: 12.34, equivalent_fuel_saved_liters: 5.67 },
    { id: 2, record_date: '2026-07-02', vehicle_id: 102, charge_energy_kwh: 30.0, grid_factor: 0.5810, carbon_reduction_kg: 8.15, equivalent_fuel_saved_liters: 3.75 },
  ],
  total: 2,
};

const mockReports = [
  { id: 1, report_month: 1, total_charge_kwh: 3000, total_reduction_kg: 800, total_fuel_saved_liters: 1800, vehicle_count: 5, verified: true },
  { id: 2, report_month: 2, total_charge_kwh: 3500, total_reduction_kg: 950, total_fuel_saved_liters: 2100, vehicle_count: 6, verified: false },
];

const mockFactors = {
  items: [
    { id: 1, year: 2026, region: '全国', factor_type: 'grid', emission_factor: 0.5810, source: '生态环境部' },
    { id: 2, year: 2026, region: '华北', factor_type: 'fuel', emission_factor: 2.1623, source: 'GB/T 32150' },
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
    if (url.includes('/fleet/carbon/overview')) return Promise.resolve({ data: mockOverview });
    if (url.includes('/fleet/carbon/details')) return Promise.resolve({ data: mockDetails });
    if (url.includes('/fleet/carbon/reports')) return Promise.resolve({ data: mockReports });
    if (url.includes('/fleet/carbon/factors')) return Promise.resolve({ data: mockFactors });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
});

import FleetCarbonPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 概览
// ═══════════════════════════════════════════
describe('碳排放 — 渲染 & 概览', () => {
  it('页面正常渲染', async () => {
    renderWithRouter(<FleetCarbonPage />);
    await waitFor(() => {
      expect(screen.getByText('碳减排概览')).toBeInTheDocument();
    });
  });

  it('显示统计卡片', async () => {
    renderWithRouter(<FleetCarbonPage />);
    await waitFor(() => {
      expect(screen.getByText('年度充电量(kWh)')).toBeInTheDocument();
      expect(screen.getByText('碳减排量(kg)')).toBeInTheDocument();
      expect(screen.getByText('等效节油(L)')).toBeInTheDocument();
      expect(screen.getByText('车辆数')).toBeInTheDocument();
    });
  });

  it('概览显示月度趋势表', async () => {
    renderWithRouter(<FleetCarbonPage />);
    await waitFor(() => {
      expect(screen.getByText('碳减排概览')).toBeInTheDocument();
    });
    // Monthly trend data should appear
    await waitFor(() => {
      expect(screen.getByText('1月')).toBeInTheDocument();
      expect(screen.getByText('2月')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// Tab 切换
// ═══════════════════════════════════════════
describe('碳排放 — Tab切换', () => {
  it('切换到减排明细Tab', async () => {
    renderWithRouter(<FleetCarbonPage />);
    await waitFor(() => expect(screen.getByText('碳减排概览')).toBeInTheDocument());

    clickTab('减排明细');

    await waitFor(() => {
      expect(screen.getByText('日期')).toBeInTheDocument();
      expect(screen.getByText('车辆ID')).toBeInTheDocument();
    });
  });

  it('切换到月度报告Tab', async () => {
    renderWithRouter(<FleetCarbonPage />);
    await waitFor(() => expect(screen.getByText('碳减排概览')).toBeInTheDocument());

    clickTab('月度报告');

    await waitFor(() => {
      // Report columns should appear
      expect(screen.getAllByText('月份').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('切换到排放因子Tab', async () => {
    renderWithRouter(<FleetCarbonPage />);
    await waitFor(() => expect(screen.getByText('碳减排概览')).toBeInTheDocument());

    clickTab('排放因子');

    await waitFor(() => {
      expect(screen.getByText('新增因子')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 排放因子 Modal
// ═══════════════════════════════════════════
describe('碳排放 — 排放因子Modal', () => {
  it('点击新增因子打开Modal', async () => {
    renderWithRouter(<FleetCarbonPage />);
    await waitFor(() => expect(screen.getByText('碳减排概览')).toBeInTheDocument());

    clickTab('排放因子');
    await waitFor(() => expect(screen.getByText('新增因子')).toBeInTheDocument());

    fireEvent.click(screen.getByText('新增因子'));

    await waitFor(() => {
      expect(screen.getByText('新增排放因子')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 报告审核
// ═══════════════════════════════════════════
describe('碳排放 — 月度报告', () => {
  it('未审核报告显示审核按钮', async () => {
    renderWithRouter(<FleetCarbonPage />);
    await waitFor(() => expect(screen.getByText('碳减排概览')).toBeInTheDocument());

    clickTab('月度报告');

    await waitFor(() => {
      expect(screen.getByText('待审核')).toBeInTheDocument();
    });
  });
});
