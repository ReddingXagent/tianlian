/**
 * 碳减排核证/交易页面 — Vitest 单元测试
 *
 * 覆盖：渲染、统计卡片、核证列表、状态标签、申请核证Modal
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

const mockCerts = [
  {
    id: 1, enterprise_id: 1, summary_id: 10, certificate_no: 'TL-CERT-2026-001',
    status: 'pending', verified_at: null, trade_volume: 0, trade_price: 0,
    created_at: '2026-07-01T10:00:00Z',
  },
  {
    id: 2, enterprise_id: 1, summary_id: 11, certificate_no: 'TL-CERT-2026-002',
    status: 'verified', verified_at: '2026-07-10T10:00:00Z', trade_volume: 0, trade_price: 0,
    created_at: '2026-07-05T10:00:00Z',
  },
  {
    id: 3, enterprise_id: 1, summary_id: 12, certificate_no: 'TL-CERT-2026-003',
    status: 'traded', verified_at: '2026-07-08T10:00:00Z',
    trade_volume: 12.5, trade_price: 65.00, created_at: '2026-07-03T10:00:00Z',
  },
];

const mockReports = [
  { id: 10, report_year: 2026, report_month: 1, total_reduction_kg: 8000, verified: true },
  { id: 11, report_year: 2026, report_month: 2, total_reduction_kg: 9500, verified: true },
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
    if (url.includes('/fleet/carbon/reports')) return Promise.resolve({ data: mockReports });
    if (url.includes('/fleet/carbon/certificates')) return Promise.resolve({ data: mockCerts });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

import FleetCarbonCertificatesPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 列表
// ═══════════════════════════════════════════
describe('碳核证 — 渲染', () => {
  it('页面正常渲染不崩溃', () => {
    const { container } = renderWithRouter(<FleetCarbonCertificatesPage />);
    expect(container).toBeTruthy();
  }, 15000);

  it('显示四张统计卡片', async () => {
    renderWithRouter(<FleetCarbonCertificatesPage />);
    await waitFor(() => {
      expect(screen.getByText('核证总数')).toBeInTheDocument();
    }, { timeout: 8000 });
    // 卡片标题与列表状态 Tag 共用文案，断言至少存在
    expect(screen.getAllByText('待核证').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('已核证').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('已交易').length).toBeGreaterThanOrEqual(1);
  }, 15000);

  it('渲染核证列表(编号 + 状态标签)', async () => {
    renderWithRouter(<FleetCarbonCertificatesPage />);
    await waitFor(() => {
      expect(screen.getByText('TL-CERT-2026-001')).toBeInTheDocument();
      expect(screen.getByText('TL-CERT-2026-003')).toBeInTheDocument();
    }, { timeout: 8000 });
    // pending→待核证 / verified→已核证 / traded→已交易
    expect(screen.getAllByText('待核证').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('已核证').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('已交易').length).toBeGreaterThanOrEqual(1);
  }, 15000);
});

// ═══════════════════════════════════════════
// 申请核证 Modal
// ═══════════════════════════════════════════
describe('碳核证 — 申请核证', () => {
  it('点击申请核证打开Modal', async () => {
    renderWithRouter(<FleetCarbonCertificatesPage />);
    await waitFor(() => expect(screen.getByText('TL-CERT-2026-001')).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.click(screen.getByText('申请核证'));

    await waitFor(() => {
      expect(screen.getByText('申请碳核证')).toBeInTheDocument();
      expect(screen.getByText('碳减排月度汇总')).toBeInTheDocument();
    });
  }, 15000);
});
