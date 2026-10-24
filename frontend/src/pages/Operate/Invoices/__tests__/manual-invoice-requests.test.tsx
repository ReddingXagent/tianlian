/**
 * 手动开票申请 — Vitest 单元测试 (卡 a09f8a21 契约 §5.4)
 * 测试覆盖: 列表渲染 / 上传弹窗 / 拒绝弹窗 / 拒绝调用 API / 金额(分→元)展示
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock settlement API (仅 mock 手动开票 API)
// ═══════════════════════════════════════════
const { mockOpsInvoiceRequestAPI } = vi.hoisted(() => ({
  mockOpsInvoiceRequestAPI: {
    list: vi.fn(),
    upload: vi.fn(),
    reject: vi.fn(),
  },
}));

vi.mock('../../../../api/settlement', () => ({
  opsInvoiceRequestAPI: mockOpsInvoiceRequestAPI,
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
// Mock 数据 (金额为「分」)
// ═══════════════════════════════════════════
const mockPendingRequests = {
  items: [
    { id: 101, user_id: 5, team_id: 1, status: 'pending', amount: 12800, amount_yuan: 128.0, title_type: 'company', title_name: '某某科技有限公司', tax_number: '91110000XXXXXXXX', email: 'fin@example.com', order_ids: ['ord_001'], remark: null, applied_at: '2026-08-07T04:30:00Z', reject_reason: null },
    { id: 102, user_id: 6, team_id: 1, status: 'pending', amount: 5500, amount_yuan: 55.0, title_type: 'personal', title_name: '张三', tax_number: null, email: null, order_ids: ['ord_002', 'ord_003'], remark: null, applied_at: '2026-08-07T05:00:00Z', reject_reason: null },
  ],
  total: 2,
};

import ManualInvoiceRequestsPage from '../ManualInvoiceRequests';

beforeEach(() => {
  vi.clearAllMocks();
  mockOpsInvoiceRequestAPI.list.mockResolvedValue({ data: mockPendingRequests });
  mockOpsInvoiceRequestAPI.upload.mockResolvedValue({});
  mockOpsInvoiceRequestAPI.reject.mockResolvedValue({});
});

describe('手动开票申请 — 渲染与交互', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><ManualInvoiceRequestsPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('加载后渲染开票申请列表 (含金额分→元)', async () => {
    await act(async () => {
      render(<BrowserRouter><ManualInvoiceRequestsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('某某科技有限公司')).toBeInTheDocument();
    });
    expect(screen.getByText('张三')).toBeInTheDocument();
    // 12800 分 → ¥128.00
    expect(screen.getByText('¥128.00')).toBeInTheDocument();
    // 5500 分 → ¥55.00
    expect(screen.getByText('¥55.00')).toBeInTheDocument();
  });

  it('点击上传发票打开上传弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><ManualInvoiceRequestsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('某某科技有限公司')).toBeInTheDocument();
    });

    const uploadBtns = screen.getAllByText('上传发票');
    fireEvent.click(uploadBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('上传发票文件')).toBeInTheDocument();
    });
  });

  it('点击拒绝打开拒绝弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><ManualInvoiceRequestsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('某某科技有限公司')).toBeInTheDocument();
    });

    const rejectBtns = screen.getAllByText('拒绝');
    fireEvent.click(rejectBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('拒绝开票')).toBeInTheDocument();
    });
  });

  it('拒绝操作调用正确 API (id + reject_reason)', async () => {
    await act(async () => {
      render(<BrowserRouter><ManualInvoiceRequestsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('某某科技有限公司')).toBeInTheDocument();
    });

    // 打开拒绝弹窗 (第一条 → id=101)
    fireEvent.click(screen.getAllByText('拒绝')[0]);
    await waitFor(() => {
      expect(screen.getByText('拒绝开票')).toBeInTheDocument();
    });

    // 填写拒绝原因
    const textarea = document.querySelector('.ant-modal textarea') as HTMLTextAreaElement;
    expect(textarea).toBeTruthy();
    fireEvent.change(textarea, { target: { value: '抬头信息有误' } });

    // 点击 Modal 确认
    const modalOkBtns = document.querySelectorAll('.ant-modal-footer .ant-btn-primary');
    expect(modalOkBtns.length).toBeGreaterThan(0);
    await act(async () => {
      fireEvent.click(modalOkBtns[0]);
    });

    await waitFor(() => {
      expect(mockOpsInvoiceRequestAPI.reject).toHaveBeenCalledWith(101, { reject_reason: '抬头信息有误' });
    });
  });

  it('请求参数带 status=pending', async () => {
    await act(async () => {
      render(<BrowserRouter><ManualInvoiceRequestsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockOpsInvoiceRequestAPI.list).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'pending' }),
      );
    });
  });
});
