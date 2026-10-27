/**
 * 车辆保险档案页面 — Vitest 单元测试
 *
 * 覆盖：渲染、统计卡片、保险列表(险种标签)、新增保险Modal
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

// end_date 取远期保证「生效中」，避免「即将到期」分支
const mockInsurances = [
  {
    id: 1, vehicle_id: 101, insurance_type: 'compulsory',
    company: '人保财险', policy_no: 'P20260001',
    start_date: '2026-01-01', end_date: '2027-12-31', premium: 4500, attachment_url: null,
  },
  {
    id: 2, vehicle_id: 101, insurance_type: 'commercial',
    company: '平安保险', policy_no: 'P20260002',
    start_date: '2026-01-01', end_date: '2027-06-30', premium: 8200, attachment_url: null,
  },
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
    if (url.includes('/fleet/vehicles') && url.includes('/insurance')) return Promise.resolve({ data: mockInsurances });
    if (url.includes('/enterprises/') && url.includes('/vehicles')) return Promise.resolve({ data: mockVehicles });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

import FleetVehicleInsurancePage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 列表
// ═══════════════════════════════════════════
describe('车辆保险 — 渲染', () => {
  it('页面正常渲染不崩溃', () => {
    const { container } = renderWithRouter(<FleetVehicleInsurancePage />);
    expect(container).toBeTruthy();
  }, 15000);

  it('显示四张统计卡片', async () => {
    renderWithRouter(<FleetVehicleInsurancePage />);
    await waitFor(() => {
      expect(screen.getByText('保单总数')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getByText('生效保单')).toBeInTheDocument();
    expect(screen.getByText('即将到期')).toBeInTheDocument();
    expect(screen.getByText('保费合计')).toBeInTheDocument();
  }, 15000);

  it('渲染保险列表(险种标签 + 保险公司)', async () => {
    renderWithRouter(<FleetVehicleInsurancePage />);
    await waitFor(() => {
      expect(screen.getByText('人保财险')).toBeInTheDocument();
      expect(screen.getByText('平安保险')).toBeInTheDocument();
    }, { timeout: 8000 });
    // 险种 Tag（compulsory→交强险 / commercial→商业险）
    expect(screen.getAllByText('交强险').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('商业险').length).toBeGreaterThanOrEqual(1);
  }, 15000);
});

// ═══════════════════════════════════════════
// 新增保险 Modal
// ═══════════════════════════════════════════
describe('车辆保险 — 新增Modal', () => {
  it('点击新增保险打开Modal', async () => {
    renderWithRouter(<FleetVehicleInsurancePage />);
    await waitFor(() => expect(screen.getByText('人保财险')).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.click(screen.getByText('新增保险'));

    await waitFor(() => {
      expect(screen.getByText('新增保险记录')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('保险公司')).toBeInTheDocument();
    });
  }, 15000);
});
