/**
 * 车队概览看板页面 — Vitest 单元测试
 *
 * 覆盖：渲染、六区块卡片、概览数据、近期交易、刷新交互
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
const mockEnterprises = { items: [{ id: 1, name: '顺达物流', code: 'TL-FLEET-001', status: 'active' }] };

const mockOverview = {
  enterprise: { id: 1, name: '顺达物流', code: 'TL-FLEET-001', balance: 5200, status: 'active' },
  total_vehicles: 10,
  active_vehicles: 8,
  maintenance_vehicles: 1,
  retired_vehicles: 1,
  total_charged_kwh: 45678,
  total_spent: 4600.5,
  recent_transactions: [
    { id: 1, type: 'recharge', amount: 200, balance_after: 5200, created_at: '2026-07-20T10:00:00Z' },
    { id: 2, type: 'consume', amount: -50, balance_after: 5150, created_at: '2026-07-21T10:00:00Z' },
  ],
};

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url === '/enterprises') return Promise.resolve({ data: mockEnterprises });
    if (url.includes('/fleet/overview')) return Promise.resolve({ data: mockOverview });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

import FleetDashboardPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 数据
// ═══════════════════════════════════════════
describe('车队概览 — 渲染', () => {
  it('页面正常渲染不崩溃', () => {
    const { container } = renderWithRouter(<FleetDashboardPage />);
    expect(container).toBeTruthy();
  }, 15000);

  it('显示标题与六个区块卡片标题', async () => {
    renderWithRouter(<FleetDashboardPage />);
    await waitFor(() => {
      expect(screen.getByText('车队概览看板')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getByText('企业基础信息')).toBeInTheDocument();
    expect(screen.getByText('车队规模')).toBeInTheDocument();
    expect(screen.getByText('充电运营')).toBeInTheDocument();
    expect(screen.getByText('V2G 收益')).toBeInTheDocument();
    expect(screen.getByText('碳减排')).toBeInTheDocument();
    expect(screen.getByText('近期交易')).toBeInTheDocument();
  }, 15000);

  it('渲染概览数据(企业名/编码/近期交易类型)', async () => {
    renderWithRouter(<FleetDashboardPage />);
    await waitFor(() => {
      // 企业名出现在基础信息区与下拉 options，用 getAllByText
      expect(screen.getAllByText('顺达物流').length).toBeGreaterThanOrEqual(1);
    }, { timeout: 8000 });
    // 编码 Tag
    expect(screen.getByText('TL-FLEET-001')).toBeInTheDocument();
    // 近期交易：充值 / 消费 标签
    expect(screen.getAllByText('充值').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('消费').length).toBeGreaterThanOrEqual(1);
  }, 15000);
});

// ═══════════════════════════════════════════
// 刷新交互
// ═══════════════════════════════════════════
describe('车队概览 — 交互', () => {
  it('点击刷新重新拉取概览', async () => {
    renderWithRouter(<FleetDashboardPage />);
    await waitFor(() => expect(screen.getByText('车队概览看板')).toBeInTheDocument(), { timeout: 8000 });

    const overviewCallsBefore = mockApi.get.mock.calls.filter((c: any[]) => c[0].includes('/fleet/overview')).length;

    fireEvent.click(screen.getByText('刷新'));

    await waitFor(() => {
      const overviewCallsAfter = mockApi.get.mock.calls.filter((c: any[]) => c[0].includes('/fleet/overview')).length;
      expect(overviewCallsAfter).toBeGreaterThan(overviewCallsBefore);
    });
  }, 15000);
});
