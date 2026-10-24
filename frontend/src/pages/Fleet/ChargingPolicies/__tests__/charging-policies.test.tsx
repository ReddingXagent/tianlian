/**
 * 企业充电策略管理页面 — Vitest 单元测试
 *
 * 覆盖：渲染、统计卡片、策略列表、新增策略Modal、策略校验Modal
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

const mockPolicies = [
  {
    id: 1, enterprise_id: 1, daily_kwh_limit: 300,
    allowed_time_slots: ['峰', '平', '谷'], allowed_station_ids: [1, 2],
    enable: true, created_at: '2026-07-01T10:00:00Z',
  },
  {
    id: 2, enterprise_id: 1, daily_kwh_limit: 0,
    allowed_time_slots: [], allowed_station_ids: [],
    enable: false, created_at: '2026-07-02T10:00:00Z',
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
    if (url.includes('/fleet/policies/check')) return Promise.resolve({ data: { allowed: true, reason: '通过' } });
    if (url.includes('/fleet/policies')) return Promise.resolve({ data: mockPolicies });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

import FleetChargingPoliciesPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 列表
// ═══════════════════════════════════════════
describe('充电策略 — 渲染', () => {
  it('页面正常渲染不崩溃', () => {
    const { container } = renderWithRouter(<FleetChargingPoliciesPage />);
    expect(container).toBeTruthy();
  }, 15000);

  it('显示四张统计卡片', async () => {
    renderWithRouter(<FleetChargingPoliciesPage />);
    await waitFor(() => {
      expect(screen.getByText('策略总数')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getByText('启用中')).toBeInTheDocument();
    expect(screen.getByText('限时段')).toBeInTheDocument();
    expect(screen.getByText('限站点')).toBeInTheDocument();
  }, 15000);

  it('渲染策略列表(所属企业 + 时段标签)', async () => {
    renderWithRouter(<FleetChargingPoliciesPage />);
    await waitFor(() => {
      expect(screen.getAllByText('顺达物流')[0]).toBeInTheDocument();
    }, { timeout: 8000 });
    // 时段 Tag
    expect(screen.getAllByText('峰').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('谷').length).toBeGreaterThanOrEqual(1);
    // 日限额值
    expect(screen.getByText('300')).toBeInTheDocument();
  }, 15000);
});

// ═══════════════════════════════════════════
// Modal 交互
// ═══════════════════════════════════════════
describe('充电策略 — 新增Modal', () => {
  it('点击新增策略打开Modal', async () => {
    renderWithRouter(<FleetChargingPoliciesPage />);
    await waitFor(() => expect(screen.getAllByText('顺达物流')[0]).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.click(screen.getByText('新增策略'));

    await waitFor(() => {
      expect(screen.getByText('新增充电策略')).toBeInTheDocument();
      expect(screen.getByText('日充电限额(kWh)')).toBeInTheDocument();
    });
  }, 15000);

  it('点击策略校验打开校验Modal', async () => {
    renderWithRouter(<FleetChargingPoliciesPage />);
    await waitFor(() => expect(screen.getAllByText('顺达物流')[0]).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.click(screen.getByText('策略校验'));

    await waitFor(() => {
      // Modal title 与按钮同为「策略校验」，改用 Modal 内唯一的「执行校验」断言
      expect(screen.getByText('执行校验')).toBeInTheDocument();
    });
  }, 15000);
});
