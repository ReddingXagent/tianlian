/**
 * 退款管理 — Vitest 单元测试
 * 测试覆盖: 待审核退款列表渲染 / 批准操作 / 驳回操作 / 退款历史
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
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
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), warn: vi.fn() } };
});

// ═══════════════════════════════════════════
// Mock 数据
// ═══════════════════════════════════════════
const mockOrdersWithRefunding = {
  items: [
    {
      id: 1, order_no: 'TL-ORD-001', station_name: '郑州充电站A', plate_number: '豫A12345',
      total_amount: 80.00, paid_amount: 75.00,
    },
  ],
};

// Order 1 has both a pending and a refunded record, so both PendingRefunds and RefundHistory work
const mockOrder1Refunds = [
  { id: 10, order_id: 1, user_id: 1, refund_amount: 30.00, reason: '充电中断', status: 'pending', reviewer_id: null, reviewed_at: null, refunded_at: null, reject_reason: null, created_at: '2026-07-04T10:00:00Z' },
  { id: 12, order_id: 1, user_id: 3, refund_amount: 15.00, reason: '系统多扣', status: 'refunded', reviewer_id: 1, reviewed_at: '2026-07-03T15:00:00Z', refunded_at: '2026-07-03T16:00:00Z', reject_reason: null, created_at: '2026-07-02T12:00:00Z' },
];
const mockOrder2Refunds = [
  { id: 11, order_id: 2, user_id: 2, refund_amount: 50.00, reason: '多收费', status: 'rejected', reviewer_id: 1, reviewed_at: '2026-07-03T15:00:00Z', refunded_at: null, reject_reason: '不符合退款条件', created_at: '2026-07-02T12:00:00Z' },
];

const mockAllOrders = {
  items: [
    { id: 1, order_no: 'TL-ORD-001', station_name: '郑州充电站A' },
    { id: 2, order_no: 'TL-ORD-002', station_name: '广州充电站B' },
  ],
};

// 卡 34ec1d55: 全局退款记录端点 (分页形状, 后端 JOIN 返回 order_no/station_name)
const mockGlobalRefunds = {
  items: [
    ...mockOrder1Refunds.map(r => ({ ...r, order_no: 'TL-ORD-001', station_name: '郑州充电站A' })),
    ...mockOrder2Refunds.map(r => ({ ...r, order_no: 'TL-ORD-002', station_name: '广州充电站B' })),
  ],
  total: 3,
};

// ═══════════════════════════════════════════
// 导入组件
// ═══════════════════════════════════════════
import PendingRefundsPage from '../PendingRefunds';
import RefundHistoryPage from '../RefundHistory';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  // 模拟已登录用户 — id 与后端 login 响应一致为字符串
  localStorage.clear();
  localStorage.setItem('admin_user', JSON.stringify({ id: '42', username: 'tester', role: 'admin', user_type: 'admin' }));
  mockApi.get.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
    if (url === '/orders/refunds') {
      // 多页翻页模拟: 第1页不满页(3 < 100) → fetchAllPages 一页取尽
      if (config?.params?.page === 1) {
        return Promise.resolve({ data: { ...mockGlobalRefunds } });
      }
      return Promise.resolve({ data: { items: [], total: mockGlobalRefunds.total } });
    }
    if (url.includes('/operate/orders') && url.includes('refunding')) return Promise.resolve({ data: mockOrdersWithRefunding });
    if (url.includes('/operate/orders')) return Promise.resolve({ data: mockAllOrders });
    if (url.match(/\/orders\/1\/refunds/)) return Promise.resolve({ data: mockOrder1Refunds });
    if (url.match(/\/orders\/2\/refunds/)) return Promise.resolve({ data: mockOrder2Refunds });
    if (url.match(/\/orders\/\d+\/refunds/)) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
  mockApi.post.mockResolvedValue({ data: { id: 10, status: 'approved' } });
  mockApi.put.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
});

// ═══════════════════════════════════════════
// 测试: 待审核退款
// ═══════════════════════════════════════════
describe('待审核退款 — 渲染与交互', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><PendingRefundsPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('渲染统计卡片', async () => {
    await act(async () => {
      render(<BrowserRouter><PendingRefundsPage /></BrowserRouter>);
    });
    expect(screen.getByText('待审核退款')).toBeInTheDocument();
    expect(screen.getByText('退款总金额')).toBeInTheDocument();
    expect(screen.getByText('涉及订单')).toBeInTheDocument();
  });

  it('加载后表格渲染待审核退款数据', async () => {
    await act(async () => {
      render(<BrowserRouter><PendingRefundsPage /></BrowserRouter>);
    });
    // PendingRefundsPage filters status === 'pending', so only id=10 shows (¥30.00)
    await waitFor(() => {
      expect(screen.getByText('¥30.00')).toBeInTheDocument();
    });
    expect(screen.getByText('充电中断')).toBeInTheDocument();
  });

  it('批准操作调用正确API', async () => {
    await act(async () => {
      render(<BrowserRouter><PendingRefundsPage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('¥30.00')).toBeInTheDocument();
    });

    const approveBtn = screen.getByText('批准');
    await act(async () => {
      fireEvent.click(approveBtn);
    });

    await waitFor(() => {
      expect(screen.getByText('确认批准此退款？')).toBeInTheDocument();
    });

    const popconfirmBtns = document.querySelectorAll('.ant-popconfirm-buttons .ant-btn-primary');
    expect(popconfirmBtns.length).toBeGreaterThan(0);
    await act(async () => {
      fireEvent.click(popconfirmBtns[0]);
    });

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith(
        expect.stringContaining('/refunds/10/approve'),
        expect.objectContaining({ reviewer_id: 42 })
      );
    });
  });

  it('驳回操作打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><PendingRefundsPage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('¥30.00')).toBeInTheDocument();
    });

    const rejectBtn = screen.getByText('驳回');
    await act(async () => {
      fireEvent.click(rejectBtn);
    });

    await waitFor(() => {
      expect(screen.getByText('驳回退款')).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText('请输入驳回原因')).toBeInTheDocument();
  });

  it('驳回提交携带当前用户reviewer_id', async () => {
    await act(async () => {
      render(<BrowserRouter><PendingRefundsPage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('¥30.00')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText('驳回'));
    });

    await waitFor(() => {
      expect(screen.getByText('驳回退款')).toBeInTheDocument();
    });

    const reasonInput = screen.getByPlaceholderText('请输入驳回原因');
    await act(async () => {
      fireEvent.change(reasonInput, { target: { value: '不符合退款条件' } });
    });

    const okBtn = document.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLElement;
    expect(okBtn).toBeTruthy();
    await act(async () => {
      fireEvent.click(okBtn);
    });

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith(
        expect.stringContaining('/refunds/10/reject'),
        expect.objectContaining({ reviewer_id: 42, reject_reason: '不符合退款条件' })
      );
    });
  });
});

// ═══════════════════════════════════════════
// 测试: 退款历史
// ═══════════════════════════════════════════
describe('退款历史 — 渲染与交互', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><RefundHistoryPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('渲染统计卡片', async () => {
    await act(async () => {
      render(<BrowserRouter><RefundHistoryPage /></BrowserRouter>);
    });
    expect(screen.getByText('退款总数')).toBeInTheDocument();
    expect(screen.getByText('已批准/退款')).toBeInTheDocument();
  });

  it('加载后表格渲染退款历史数据', async () => {
    await act(async () => {
      render(<BrowserRouter><RefundHistoryPage /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('¥30.00')).toBeInTheDocument();
    });
    expect(screen.getByText('¥50.00')).toBeInTheDocument();
    expect(screen.getByText('充电中断')).toBeInTheDocument();
    expect(screen.getByText('多收费')).toBeInTheDocument();
    expect(screen.getByText('不符合退款条件')).toBeInTheDocument();
  });

  it('搜索框可输入', async () => {
    await act(async () => {
      render(<BrowserRouter><RefundHistoryPage /></BrowserRouter>);
    });
    const searchInput = screen.getByPlaceholderText('搜索订单号/原因');
    expect(searchInput).toBeInTheDocument();
    fireEvent.change(searchInput, { target: { value: 'TL-ORD-001' } });
    expect((searchInput as HTMLInputElement).value).toBe('TL-ORD-001');
  });

  it('单端点分页加载, 无逐单 N+1 请求 (卡 34ec1d55)', async () => {
    await act(async () => {
      render(<BrowserRouter><RefundHistoryPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('¥30.00')).toBeInTheDocument();
    });

    const calls = mockApi.get.mock.calls as unknown as [string, { params?: Record<string, unknown> }][];
    // 只打全局退款端点, 不再先拉 /operate/orders、也不再逐单 /orders/{id}/refunds
    const listCalls = calls.filter(([url]) => url === '/orders/refunds');
    expect(listCalls.length).toBe(1); // 尾页不满页, 一页取尽
    expect(listCalls[0][1]?.params).toMatchObject({ page: 1, page_size: 100 });
    expect(calls.some(([url]) => url.includes('/operate/orders'))).toBe(false);
    expect(calls.some(([url]) => /\/orders\/\d+\/refunds/.test(url))).toBe(false);
  });

  it('加载失败时 message.error 可见降级, 不静默吞', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url === '/orders/refunds') return Promise.reject(new Error('network down'));
      return Promise.resolve({ data: [] });
    });
    const { message: antdMessage } = await import('antd');
    await act(async () => {
      render(<BrowserRouter><RefundHistoryPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(antdMessage.error).toHaveBeenCalledWith('退款记录加载失败，请稍后重试');
    });
  });
});
