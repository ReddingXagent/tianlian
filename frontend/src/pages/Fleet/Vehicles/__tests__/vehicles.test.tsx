/**
 * 车辆管理页面 — Vitest 单元测试
 *
 * 覆盖：渲染、统计卡片、车辆列表、搜索筛选、绑定新车Modal
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
const mockDrivers = [{ id: 1, name: '赵刚', phone: '13600136001' }];
const mockVehicles = [
  { id: 1, enterprise_id: 1, plate_number: '京A·12345', vin: 'LSGAB52L7DF000001', brand: '比亚迪', model: 'T5', driver_name: '赵刚', driver_phone: '13600136001', status: 'active', approval_status: 'confirmed', created_at: '2026-07-01T10:00:00Z' },
  { id: 2, enterprise_id: 1, plate_number: '京A·23456', vin: 'LSGAB52L7DF000002', brand: '东风', model: '天龙KL', driver_name: '钱明', driver_phone: '13500135002', status: 'maintenance', approval_status: 'pending', created_at: '2026-06-15T10:00:00Z' },
];

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/fleet/enterprises')) return Promise.resolve({ data: mockEnterprises });
    if (url.includes('/fleet/drivers')) return Promise.resolve({ data: mockDrivers });
    if (url.includes('/enterprises/') && url.includes('/vehicles')) return Promise.resolve({ data: mockVehicles });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

import FleetVehiclesPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 列表
// ═══════════════════════════════════════════
describe('车辆管理 — 渲染', () => {
  it('页面正常渲染不崩溃', () => {
    const { container } = renderWithRouter(<FleetVehiclesPage />);
    expect(container).toBeTruthy();
  }, 15000);

  it('显示四张统计卡片', async () => {
    renderWithRouter(<FleetVehiclesPage />);
    await waitFor(() => {
      expect(screen.getByText('车辆总数')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getAllByText('在役').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('维修中')).toBeInTheDocument();
    // 「待确认」同时是卡片标题与列表确认状态 Tag
    expect(screen.getAllByText('待确认').length).toBeGreaterThanOrEqual(1);
  }, 15000);

  it('渲染车辆列表(车牌 + 品牌车型)', async () => {
    renderWithRouter(<FleetVehiclesPage />);
    await waitFor(() => {
      expect(screen.getByText('京A·12345')).toBeInTheDocument();
      expect(screen.getByText('京A·23456')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getByText(/比亚迪/)).toBeInTheDocument();
    expect(screen.getByText(/东风/)).toBeInTheDocument();
  }, 15000);
});

// ═══════════════════════════════════════════
// 搜索筛选
// ═══════════════════════════════════════════
describe('车辆管理 — 搜索', () => {
  it('搜索车牌号过滤列表', async () => {
    renderWithRouter(<FleetVehiclesPage />);
    await waitFor(() => expect(screen.getByText('京A·12345')).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.change(screen.getByPlaceholderText('搜索车牌/VIN/司机'), { target: { value: '12345' } });

    await waitFor(() => {
      expect(screen.queryByText('京A·23456')).not.toBeInTheDocument();
    });
    expect(screen.getByText('京A·12345')).toBeInTheDocument();
  }, 15000);
});

// ═══════════════════════════════════════════
// 绑定新车 Modal
// ═══════════════════════════════════════════
describe('车辆管理 — 绑定新车', () => {
  it('点击绑定新车打开Modal', async () => {
    renderWithRouter(<FleetVehiclesPage />);
    await waitFor(() => expect(screen.getByText('京A·12345')).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.click(screen.getByText('绑定新车'));

    await waitFor(() => {
      // 按钮与 Modal title 同为「绑定新车」，改用 Modal 内唯一 placeholder 断言
      expect(screen.getByPlaceholderText('17位车架号')).toBeInTheDocument();
    });
  }, 15000);
});
