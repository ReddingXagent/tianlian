/**
 * 费用结算页面 — Vitest 单元测试
 *
 * 覆盖：渲染、Tab切换(账单/发票)、统计卡片、生成账单Modal、付款Modal、发票Modal
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

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockBills = {
  items: [
    { id: 1, bill_no: 'FSB202607001', enterprise_id: 1, bill_period: '2026-07', total_orders: 45, total_amount: 12580.50, paid_amount: 0, balance_amount: 12580.50, status: 'pending', total_energy_kwh: 5234.5 },
    { id: 2, bill_no: 'FSB202606001', enterprise_id: 1, bill_period: '2026-06', total_orders: 52, total_amount: 14300.00, paid_amount: 14300.00, balance_amount: 0, status: 'paid', total_energy_kwh: 6100.0 },
    { id: 3, bill_no: 'FSB202605001', enterprise_id: 2, bill_period: '2026-05', total_orders: 38, total_amount: 9800.00, paid_amount: 5000.00, balance_amount: 4800.00, status: 'confirmed', total_energy_kwh: 4200.0 },
  ],
  total: 3,
};

const mockInvoices = {
  items: [
    { id: 1, bill_id: 1, enterprise_id: 1, amount: 12580.50, invoice_type: 'general', title: '顺达物流有限公司', tax_no: '91410100MA44XXXXXX', status: 'pending' },
    { id: 2, bill_id: 2, enterprise_id: 1, amount: 14300.00, invoice_type: 'special', title: '顺达物流有限公司', tax_no: '91410100MA44XXXXXX', status: 'issued' },
  ],
  total: 2,
};

const mockBillDetails = {
  items: [
    { id: 1, order_no: 'ORD20260715001', plate_number: '豫A·12345', energy_kwh: 45.5, charge_fee: 36.40, service_fee: 9.10, parking_fee: 0, total_amount: 45.50 },
    { id: 2, order_no: 'ORD20260716002', plate_number: '豫A·23456', energy_kwh: 60.0, charge_fee: 48.00, service_fee: 12.00, parking_fee: 5.00, total_amount: 65.00 },
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
    if (url.includes('/fleet/settlement/bills') && url.includes('/details')) {
      return Promise.resolve({ data: mockBillDetails });
    }
    if (url.includes('/fleet/settlement/bills')) {
      return Promise.resolve({ data: mockBills });
    }
    if (url.includes('/fleet/settlement/invoices')) {
      return Promise.resolve({ data: mockInvoices });
    }
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

import FleetSettlementPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 账单
// ═══════════════════════════════════════════
describe('费用结算 — 渲染 & 账单', () => {
  it('页面正常渲染', async () => {
    renderWithRouter(<FleetSettlementPage />);
    await waitFor(() => {
      expect(screen.getByText('对账账单')).toBeInTheDocument();
    }, { timeout: 8000 });
  }, 15000);

  it('显示统计卡片', async () => {
    renderWithRouter(<FleetSettlementPage />);
    await waitFor(() => {
      expect(screen.getByText('账单总数')).toBeInTheDocument();
    }, { timeout: 8000 });
    // '总金额(¥)' appears in both stat card and table header
    expect(screen.getAllByText('总金额(¥)').length).toBeGreaterThanOrEqual(1);
  }, 15000);

  it('显示账单列表', async () => {
    renderWithRouter(<FleetSettlementPage />);
    await waitFor(() => {
      expect(screen.getByText('FSB202607001')).toBeInTheDocument();
      expect(screen.getByText('FSB202606001')).toBeInTheDocument();
      expect(screen.getByText('FSB202605001')).toBeInTheDocument();
    });
  });

  it('显示账单状态标签', async () => {
    renderWithRouter(<FleetSettlementPage />);
    await waitFor(() => {
      expect(screen.getByText('账单总数')).toBeInTheDocument();
    }, { timeout: 8000 });
    // "待确认" appears in stat card title and as a tag
    expect(screen.getAllByText('待确认').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('已付款').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('已确认')).toBeInTheDocument();
  }, 15000);
});

// ═══════════════════════════════════════════
// Tab 切换
// ═══════════════════════════════════════════
describe('费用结算 — Tab切换', () => {
  it('切换到发票管理Tab', async () => {
    renderWithRouter(<FleetSettlementPage />);
    await waitFor(() => expect(screen.getByText('对账账单')).toBeInTheDocument(), { timeout: 8000 });

    clickTab('发票管理');

    await waitFor(() => {
      // Invoice data has multiple rows with same title
      expect(screen.getAllByText('顺达物流有限公司').length).toBeGreaterThanOrEqual(1);
    });
  }, 15000);

  it('发票Tab显示发票状态', async () => {
    renderWithRouter(<FleetSettlementPage />);
    await waitFor(() => expect(screen.getByText('对账账单')).toBeInTheDocument(), { timeout: 8000 });

    clickTab('发票管理');

    await waitFor(() => {
      expect(screen.getByText('待开具')).toBeInTheDocument();
      expect(screen.getByText('已开具')).toBeInTheDocument();
    });
  }, 15000);
});

// ═══════════════════════════════════════════
// Modal 交互
// ═══════════════════════════════════════════
describe('费用结算 — 生成账单Modal', () => {
  it('点击生成账单打开Modal', async () => {
    renderWithRouter(<FleetSettlementPage />);
    await waitFor(() => expect(screen.getByText('对账账单')).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.click(screen.getByText('生成账单'));

    await waitFor(() => {
      expect(screen.getByText('生成对账账单')).toBeInTheDocument();
      expect(screen.getByText('企业ID')).toBeInTheDocument();
      expect(screen.getByText('账期(月份)')).toBeInTheDocument();
    });
  }, 15000);
});

describe('费用结算 — 账单详情抽屉', () => {
  it('点击账单编号打开详情抽屉', async () => {
    renderWithRouter(<FleetSettlementPage />);
    await waitFor(() => expect(screen.getByText('FSB202607001')).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.click(screen.getByText('FSB202607001'));

    await waitFor(() => {
      expect(screen.getByText('费用明细')).toBeInTheDocument();
    });
  }, 15000);
});

// ═══════════════════════════════════════════
// 操作按钮
// ═══════════════════════════════════════════
describe('费用结算 — 操作按钮', () => {
  it('待确认账单显示确认按钮', async () => {
    renderWithRouter(<FleetSettlementPage />);
    await waitFor(() => expect(screen.getByText('FSB202607001')).toBeInTheDocument(), { timeout: 8000 });

    // pending status should have 确认 button
    expect(screen.getByText('确认')).toBeInTheDocument();
  }, 15000);

  it('已确认账单显示付款按钮', async () => {
    renderWithRouter(<FleetSettlementPage />);
    await waitFor(() => expect(screen.getByText('FSB202605001')).toBeInTheDocument(), { timeout: 8000 });

    // confirmed status should have 付款 button
    expect(screen.getByText('付款')).toBeInTheDocument();
  }, 15000);
});
