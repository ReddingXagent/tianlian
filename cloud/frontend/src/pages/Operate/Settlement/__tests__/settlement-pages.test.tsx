/**
 * 结算对账 + 发票管理 组件测试 (vitest)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { message } from 'antd';

// Mock antd message
vi.mock('antd', async () => {
  const actual = await vi.importActual('antd');
  return { ...actual, message: { success: vi.fn(), error: vi.fn() } };
});

// Mock API
vi.mock('../../../api/settlement', () => ({
  dailySettlementAPI: {
    list: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }),
    generate: vi.fn().mockResolvedValue({ data: { id: 1 } }),
    confirm: vi.fn().mockResolvedValue({ data: {} }),
  },
  reconciliationAPI: {
    list: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }),
    create: vi.fn().mockResolvedValue({ data: { id: 1 } }),
    reconcile: vi.fn().mockResolvedValue({ data: {} }),
  },
  enterpriseSettlementAPI: {
    list: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }),
  },
  interconnectAPI: {
    list: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }),
    create: vi.fn().mockResolvedValue({ data: { id: 1 } }),
    settle: vi.fn().mockResolvedValue({ data: {} }),
  },
  invoiceTitleAPI: {
    list: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }),
    create: vi.fn().mockResolvedValue({ data: { id: 1 } }),
    update: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
  opsInvoiceRequestAPI: {
    list: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }),
    upload: vi.fn().mockResolvedValue({ data: {} }),
    reject: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

// Import components after mock
import DailySettlementPage from '../DailySettlement';
import ReconciliationPage from '../Reconciliation';
import EnterpriseSettlementPage from '../EnterpriseSettlement';
import InterconnectPage from '../Interconnect';
import IssuedInvoicesPage from '../../Invoices/IssuedInvoices';
import InvoiceTitlesPage from '../../Invoices/InvoiceTitles';
import SettlementIndex from '../index';
import InvoicesIndex from '../../Invoices/index';

const renderWithRouter = (ui: React.ReactElement) =>
  render(<BrowserRouter>{ui}</BrowserRouter>);

describe('Settlement Pages', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('DailySettlementPage', () => {
    it('renders without crash', async () => {
      const { container } = renderWithRouter(<DailySettlementPage />);
      await waitFor(() => {
        expect(container).toBeTruthy();
      });
    });

    it('shows refresh button', async () => {
      renderWithRouter(<DailySettlementPage />);
      await waitFor(() => {
        expect(screen.getByText('刷新')).toBeInTheDocument();
      });
    });
  });

  describe('ReconciliationPage', () => {
    it('renders without crash', async () => {
      const { container } = renderWithRouter(<ReconciliationPage />);
      await waitFor(() => {
        expect(container).toBeTruthy();
      });
    });
  });

  describe('EnterpriseSettlementPage', () => {
    it('renders without crash', async () => {
      const { container } = renderWithRouter(<EnterpriseSettlementPage />);
      await waitFor(() => {
        expect(container).toBeTruthy();
      });
    });
  });

  describe('InterconnectPage', () => {
    it('renders without crash', async () => {
      const { container } = renderWithRouter(<InterconnectPage />);
      await waitFor(() => {
        expect(container).toBeTruthy();
      });
    });
  });

  describe('SettlementIndex', () => {
    it('renders all 4 tabs', async () => {
      const { container } = renderWithRouter(<SettlementIndex />);
      await waitFor(() => {
        expect(screen.getByText('日结汇总')).toBeInTheDocument();
        expect(screen.getByText('支付对账')).toBeInTheDocument();
        expect(screen.getByText('企业结算')).toBeInTheDocument();
        expect(screen.getByText('互联互通结算')).toBeInTheDocument();
      });
    });
  });
});

describe('Invoice Pages', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('IssuedInvoicesPage', () => {
    it('renders without crash', async () => {
      const { container } = renderWithRouter(<IssuedInvoicesPage />);
      await waitFor(() => {
        expect(container).toBeTruthy();
      });
    });
  });

  describe('InvoiceTitlesPage', () => {
    it('renders without crash and shows add button', async () => {
      renderWithRouter(<InvoiceTitlesPage />);
      await waitFor(() => {
        expect(screen.getByText('新增抬头')).toBeInTheDocument();
      });
    });
  });

  describe('InvoicesIndex', () => {
    it('renders all 3 tabs', async () => {
      renderWithRouter(<InvoicesIndex />);
      await waitFor(() => {
        expect(screen.getByText('待审核')).toBeInTheDocument();
        expect(screen.getByText('已开发票')).toBeInTheDocument();
        expect(screen.getByText('发票抬头')).toBeInTheDocument();
      });
    });
  });
});

// ═══════════════════════════════════════════
// 旧体系退役验证 (卡 6d06831d): api 层不得再导出 opsInvoiceAPI
// ═══════════════════════════════════════════
describe('opsInvoiceAPI 退役 (卡 6d06831d)', () => {
  it('settlement API 模块不再导出 opsInvoiceAPI', async () => {
    const mod = await import('../../../../api/settlement');
    expect((mod as Record<string, unknown>).opsInvoiceAPI).toBeUndefined();
  });

  it('新体系 opsInvoiceRequestAPI 仍导出', async () => {
    const mod = await import('../../../../api/settlement');
    expect((mod as Record<string, unknown>).opsInvoiceRequestAPI).toBeDefined();
  });
});
