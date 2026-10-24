/**
 * 车辆维保/保险档案页面 — Vitest 单元测试
 *
 * 覆盖：渲染、统计卡片、维保列表(类型标签)、Tabs(维保/保险/档案)、新增维保Modal
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

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockEnterprises = [{ id: 1, name: '顺达物流' }];
const mockVehicles = [{ id: 101, plate_number: '京A·12345' }];

const mockMaintenances = [
  { id: 1, vehicle_id: 101, type: 'maintenance', start_at: '2026-05-01', end_at: '2026-05-02', cost: 800, mileage: 50000, description: '常规保养', status: 'completed' },
  { id: 2, vehicle_id: 101, type: 'repair', start_at: '2026-06-10', end_at: '2026-06-12', cost: 2300, mileage: 52000, description: '刹车片更换', status: 'completed' },
];

const mockInsList = [
  { id: 1, vehicle_id: 101, insurance_type: 'compulsory', company: '人保财险', policy_no: 'P001', start_date: '2026-01-01', end_date: '2027-01-01', premium: 4500 },
];

const mockProfile = {
  vehicle_id: 101,
  maintenance: { total_count: 2, total_cost: 3100, by_status: { completed: 2 }, recent: mockMaintenances },
  insurance: { total_count: 1, active_count: 1, total_premium: 4500, current: mockInsList },
  expiry_reminders: [],
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
    if (url.includes('/fleet/vehicles') && url.includes('/profile')) return Promise.resolve({ data: mockProfile });
    if (url.includes('/fleet/vehicles') && url.includes('/insurance')) return Promise.resolve({ data: mockInsList });
    if (url.includes('/fleet/vehicles') && url.includes('/maintenance')) return Promise.resolve({ data: mockMaintenances });
    if (url.includes('/enterprises/') && url.includes('/vehicles')) return Promise.resolve({ data: mockVehicles });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

import FleetVehicleMaintenancePage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 维保列表
// ═══════════════════════════════════════════
describe('车辆维保 — 渲染', () => {
  it('页面正常渲染不崩溃', () => {
    const { container } = renderWithRouter(<FleetVehicleMaintenancePage />);
    expect(container).toBeTruthy();
  }, 15000);

  it('显示四张统计卡片', async () => {
    renderWithRouter(<FleetVehicleMaintenancePage />);
    await waitFor(() => {
      expect(screen.getByText('维保次数')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getByText('维保总费用')).toBeInTheDocument();
    expect(screen.getByText('保单数')).toBeInTheDocument();
    expect(screen.getByText('生效保单')).toBeInTheDocument();
  }, 15000);

  it('渲染维保列表(类型标签 + 描述)', async () => {
    renderWithRouter(<FleetVehicleMaintenancePage />);
    await waitFor(() => {
      expect(screen.getByText('常规保养')).toBeInTheDocument();
      expect(screen.getByText('刹车片更换')).toBeInTheDocument();
    }, { timeout: 8000 });
    // 维保类型 Tag：maintenance→保养 / repair→维修
    expect(screen.getAllByText('保养').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('维修').length).toBeGreaterThanOrEqual(1);
  }, 15000);
});

// ═══════════════════════════════════════════
// Tab 切换 & Modal
// ═══════════════════════════════════════════
describe('车辆维保 — 交互', () => {
  it('点击新增维保打开Modal', async () => {
    renderWithRouter(<FleetVehicleMaintenancePage />);
    await waitFor(() => expect(screen.getByText('常规保养')).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.click(screen.getByText('新增维保'));

    await waitFor(() => {
      expect(screen.getByText('新增维保记录')).toBeInTheDocument();
    });
  }, 15000);

  it('切换到聚合档案Tab显示档案', async () => {
    renderWithRouter(<FleetVehicleMaintenancePage />);
    await waitFor(() => expect(screen.getByText('常规保养')).toBeInTheDocument(), { timeout: 8000 });

    clickTab('聚合档案');

    await waitFor(() => {
      expect(screen.getByText('保险到期提醒')).toBeInTheDocument();
    });
  }, 15000);
});
