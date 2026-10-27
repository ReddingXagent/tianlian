/**
 * 发票管理 — Vitest 单元测试
 * 测试覆盖: 已开发票(新体系) / 发票抬头 / 开票平台
 *
 * 卡 6d06831d (B1 下线旧 OpsInvoice):
 * - PendingInvoices 页已删 (旧审核流), 待审核用例移至 manual-invoice-requests.test.tsx
 * - IssuedInvoices 改指 /ops/invoice-requests?status=issued (契约 v1.3 §5.4)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock settlement API
// ═══════════════════════════════════════════
const { mockOpsInvoiceRequestAPI, mockInvoiceTitleAPI, mockInvoicePlatformAPI } = vi.hoisted(() => ({
  mockOpsInvoiceRequestAPI: {
    list: vi.fn(),
    upload: vi.fn(),
    reject: vi.fn(),
    void: vi.fn(),
  },
  mockInvoiceTitleAPI: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
  mockInvoicePlatformAPI: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    setDefault: vi.fn(),
  },
}));

vi.mock('../../../../api/settlement', () => ({
  opsInvoiceRequestAPI: mockOpsInvoiceRequestAPI,
  invoiceTitleAPI: mockInvoiceTitleAPI,
  invoicePlatformAPI: mockInvoicePlatformAPI,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), warn: vi.fn() } };
});

// ═══════════════════════════════════════════
// Mock 数据 (契约 v1.3 §5.4 字段口径)
// ═══════════════════════════════════════════
const mockIssuedRequests = {
  items: [
    {
      id: 3, user_id: 101, team_id: 1, status: 'issued',
      amount: 320000, amount_yuan: 3200.0,
      title_type: 'company', title_name: '南京集团', tax_number: '91320100MA66ZZZZZZ',
      order_ids: ['TL20260801001', 'TL20260801002'],
      invoice_file_name: '电子发票_0001.pdf', invoice_file_type: 'pdf',
      issuer: 9, issued_at: '2026-08-03T16:00:00+00:00', applied_at: '2026-08-01T10:00:00+00:00',
    },
    {
      id: 4, user_id: 102, team_id: 1, status: 'issued',
      amount: 50000, amount_yuan: 500.0,
      title_type: 'personal', title_name: '王五', tax_number: null,
      order_ids: ['TL20260802001'],
      invoice_file_name: '发票_0002.ofd', invoice_file_type: 'ofd',
      issuer: 9, issued_at: '2026-08-04T10:00:00+00:00', applied_at: '2026-08-02T09:00:00+00:00',
    },
    {
      // 已红冲行 (卡 f42bdf5a, R1 方案b: status 保持 issued + voided 标记)
      id: 5, user_id: 103, team_id: 1, status: 'issued',
      amount: 8000, amount_yuan: 80.0,
      title_type: 'personal', title_name: '赵六', tax_number: null,
      order_ids: ['TL20260803001'],
      invoice_file_name: '发票_0003.pdf', invoice_file_type: 'pdf',
      issuer: 9, issued_at: '2026-08-05T10:00:00+00:00', applied_at: '2026-08-03T09:00:00+00:00',
      voided: true, void_reason: '开票信息有误', voided_by: 9,
      voided_at: '2026-08-06T10:00:00+00:00',
    },
  ],
  total: 3,
};

const mockTitles = {
  items: [
    { id: 1, title_type: 'enterprise', title_name: '郑州科技有限公司', tax_id: '91410100MA44XXXXXX', register_address: '郑州市金水区', register_phone: '0371-12345678', bank_name: '郑州银行', bank_account: '6217001234567890', email: 'finance@example.com', is_default: true },
    { id: 2, title_type: 'personal', title_name: '张三', tax_id: null, register_address: null, register_phone: null, bank_name: null, bank_account: null, email: 'zhangsan@example.com', is_default: false },
  ],
  total: 2,
};

// ═══════════════════════════════════════════
// 导入组件
// ═══════════════════════════════════════════
import IssuedInvoicesPage from '../IssuedInvoices';
import InvoiceTitlesPage from '../InvoiceTitles';
import InvoicePlatformsPage from '../InvoicePlatforms';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockOpsInvoiceRequestAPI.list.mockResolvedValue({ data: mockIssuedRequests });
  mockOpsInvoiceRequestAPI.upload.mockResolvedValue({});
  mockOpsInvoiceRequestAPI.reject.mockResolvedValue({});
  mockOpsInvoiceRequestAPI.void.mockResolvedValue({});
  mockInvoiceTitleAPI.list.mockResolvedValue({ data: mockTitles });
  mockInvoiceTitleAPI.create.mockResolvedValue({});
  mockInvoiceTitleAPI.update.mockResolvedValue({});
  mockInvoiceTitleAPI.delete.mockResolvedValue({});
  mockInvoicePlatformAPI.list.mockResolvedValue({ data: { items: [] } });
});

// ═══════════════════════════════════════════
// 测试: 已开发票 (InvoiceRequest 新体系, 卡 6d06831d)
// ═══════════════════════════════════════════
describe('已开发票 — 新体系切换 (卡 6d06831d)', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><IssuedInvoicesPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('列表请求走新体系 /ops/invoice-requests 且固定 status=issued', async () => {
    await act(async () => {
      render(<BrowserRouter><IssuedInvoicesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockOpsInvoiceRequestAPI.list).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'issued', page: 1, page_size: 20 }),
      );
    });
  });

  it('加载后表格渲染已开具申请 (抬头/金额元/发票文件)', async () => {
    await act(async () => {
      render(<BrowserRouter><IssuedInvoicesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('南京集团')).toBeInTheDocument();
    });
    // amount_yuan (后端预折算) 直接展示, 不再本地 /100
    expect(screen.getByText('¥3200.00')).toBeInTheDocument();
    expect(screen.getByText('¥500.00')).toBeInTheDocument();
    // 发票文件列 (新体系: 落盘文件, 无 invoice_no/pdf_url)
    expect(screen.getByText('电子发票_0001.pdf (PDF)')).toBeInTheDocument();
    expect(screen.getByText('发票_0002.ofd (OFD)')).toBeInTheDocument();
    expect(screen.getAllByText('已开具').length).toBe(3); // 三条 mock 均为 issued
  });

  it('多订单合并开票显示「等N单」', async () => {
    await act(async () => {
      render(<BrowserRouter><IssuedInvoicesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText(/等2单/)).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 测试: 已开发票 — 红冲 (卡 f42bdf5a, R1 方案b: voided 标记)
// ═══════════════════════════════════════════
describe('已开发票 — 红冲 (卡 f42bdf5a)', () => {
  it('未红冲行渲染红冲按钮; 已红冲行显示「已红冲」标记且无入口', async () => {
    await act(async () => {
      render(<BrowserRouter><IssuedInvoicesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('南京集团')).toBeInTheDocument();
    });
    // 未红冲两行 (id 3/4) 各有红冲按钮
    expect(screen.getAllByText('红冲').length).toBe(2);
    // 已红冲行 (id 5, voided=true) 显示标记, 操作列显示 '-'
    expect(screen.getByText('已红冲')).toBeInTheDocument();
  });

  it('点红冲弹理由输入框, 填理由确认后调 void API 并刷新', async () => {
    await act(async () => {
      render(<BrowserRouter><IssuedInvoicesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('南京集团')).toBeInTheDocument();
    });
    await act(async () => {
      fireEvent.click(screen.getAllByText('红冲')[0]);
    });
    // 理由弹窗出现
    expect(screen.getByPlaceholderText(/请填写红冲原因/)).toBeInTheDocument();
    await act(async () => {
      fireEvent.change(screen.getByPlaceholderText(/请填写红冲原因/), {
        target: { value: '开票信息有误' },
      });
    });
    await act(async () => {
      fireEvent.click(screen.getByText('确认红冲'));
    });
    await waitFor(() => {
      expect(mockOpsInvoiceRequestAPI.void).toHaveBeenCalledWith(
        3, { reason: '开票信息有误' },
      );
    });
    // 红冲成功后刷新列表
    await waitFor(() => {
      expect(mockOpsInvoiceRequestAPI.list.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('红冲理由为空时提示不调 API', async () => {
    await act(async () => {
      render(<BrowserRouter><IssuedInvoicesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('南京集团')).toBeInTheDocument();
    });
    await act(async () => {
      fireEvent.click(screen.getAllByText('红冲')[0]);
    });
    await act(async () => {
      fireEvent.click(screen.getByText('确认红冲'));
    });
    expect(mockOpsInvoiceRequestAPI.void).not.toHaveBeenCalled();
  });
});

// ═══════════════════════════════════════════
// 测试: 发票抬头管理
// ═══════════════════════════════════════════
describe('发票抬头 — 渲染与交互', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><InvoiceTitlesPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('加载后表格渲染抬头数据', async () => {
    await act(async () => {
      render(<BrowserRouter><InvoiceTitlesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('郑州科技有限公司')).toBeInTheDocument();
    });
    expect(screen.getByText('张三')).toBeInTheDocument();
    expect(screen.getByText('企业')).toBeInTheDocument();
    expect(screen.getByText('个人')).toBeInTheDocument();
  });

  it('新增抬头按钮打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><InvoiceTitlesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('郑州科技有限公司')).toBeInTheDocument();
    });

    const addBtn = screen.getByText('新增抬头');
    fireEvent.click(addBtn);

    await waitFor(() => {
      // Modal opens — look for the form label '抬头类型'
      expect(screen.getByText('抬头类型')).toBeInTheDocument();
    });
  });

  it('编辑抬头打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><InvoiceTitlesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('郑州科技有限公司')).toBeInTheDocument();
    });

    const editBtns = screen.getAllByText('编辑');
    fireEvent.click(editBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('抬头类型')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 测试: 开票平台表单 (卡 6d92ffc6)
// ═══════════════════════════════════════════
describe('开票平台表单 — 字段渲染', () => {
  it('平台表单显示所有基础字段', async () => {
    await act(async () => {
      render(<BrowserRouter><InvoicePlatformsPage /></BrowserRouter>);
    });

    await act(async () => {
      fireEvent.click(screen.getByText('新增平台'));
    });

    await waitFor(() => {
      expect(screen.getByText('Token换取地址')).toBeInTheDocument();
    });
    expect(screen.getByText('开票回调地址')).toBeInTheDocument();
    expect(screen.getByText('高级配置')).toBeInTheDocument();
  });

  it('选择诺诺平台时显示RSA私钥字段', async () => {
    await act(async () => {
      render(<BrowserRouter><InvoicePlatformsPage /></BrowserRouter>);
    });

    await act(async () => {
      fireEvent.click(screen.getByText('新增平台'));
    });

    // 默认 baiwang，此时无 RSA 私钥
    await waitFor(() => {
      expect(screen.queryByText('RSA私钥')).not.toBeInTheDocument();
    });

    // 切换到诺诺
    await act(async () => {
      fireEvent.mouseDown(document.querySelector('.ant-select-selector') as HTMLElement);
    });
    const nuonuoOpt = await waitFor(() =>
      Array.from(document.querySelectorAll('.ant-select-item-option')).find(
        (el) => el.textContent?.includes('诺诺'),
      ) as HTMLElement,
    );
    await act(async () => {
      fireEvent.click(nuonuoOpt);
    });

    await waitFor(() => {
      expect(screen.getByText('RSA私钥')).toBeInTheDocument();
    });
  });

  it('选择百旺平台时显示设备编号字段', async () => {
    await act(async () => {
      render(<BrowserRouter><InvoicePlatformsPage /></BrowserRouter>);
    });

    await act(async () => {
      fireEvent.click(screen.getByText('新增平台'));
    });

    // 默认即 baiwang → 应直接显示设备编号
    await waitFor(() => {
      expect(screen.getByText('设备/终端编号')).toBeInTheDocument();
    });
  });
});
