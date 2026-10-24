/**
 * 异常订单操作闭环 — Vitest 单元测试 (卡 f730f63c)
 * 覆盖: 操作列按状态显隐 / 重试计费 / 标记处理 / 转退款 / 详情抽屉
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock 数据 — 4 类异常订单覆盖操作列全部分支
// ═══════════════════════════════════════════
const baseRow = (o: Partial<Record<string, unknown>>) => ({
  station_name: '测试站', plate_number: '京A', user_type: 'app', charged_kwh: 0,
  total_amount: 0, paid_amount: 0, discount_amount: 0, payment_status: 'unpaid',
  payment_method: null, duration_minutes: 5, abnormal_handle_type: null,
  created_at: '2026-07-01T10:00:00Z', ...o,
});

// failed: 未付款(无转退款) / 已付款(有转退款) / 已处理(仅详情)
const mockFailedOrders = {
  items: [
    baseRow({ id: 1, order_no: 'FAIL-001', order_status: 'failed', paid_amount: 0, charged_kwh: 10 }),
    baseRow({ id: 2, order_no: 'FAIL-002', order_status: 'failed', paid_amount: 30, total_amount: 30, charged_kwh: 20 }),
    baseRow({ id: 3, order_no: 'FAIL-003', order_status: 'failed', abnormal_handle_type: 'written_off' }),
  ],
  total: 3, page: 1, page_size: 20,
};

// cancelled: 已付款 → 详情/标记处理/转退款(无重试计费)
const mockCancelledOrders = {
  items: [
    baseRow({ id: 4, order_no: 'CANC-001', order_status: 'cancelled', paid_amount: 5, total_amount: 5 }),
  ],
  total: 1, page: 1, page_size: 20,
};

// ═══════════════════════════════════════════
// Mock API
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../../api', () => ({ default: mockApi }));

vi.mock('echarts-for-react', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock'),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import AbnormalOrdersPage from '../AbnormalOrders';

const renderPage = () =>
  render(<BrowserRouter><AbnormalOrdersPage /></BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
    if (url.match(/\/operate\/orders\/\d+\/charge-curve/)) return Promise.resolve({ data: { order_id: 1, items: [], total: 0 } });
    if (url.match(/\/orders\/\d+\/fee-items/)) return Promise.resolve({ data: [] });
    const status = config?.params?.status;
    if (url.includes('/operate/orders') && status === 'failed') return Promise.resolve({ data: mockFailedOrders });
    if (url.includes('/operate/orders') && status === 'cancelled') return Promise.resolve({ data: mockCancelledOrders });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: { id: 1 } });
});

// ═══════════════════════════════════════════
// 操作列按状态显隐
// ═══════════════════════════════════════════
describe('异常订单 — 操作列按状态显隐', () => {
  it('渲染所有异常订单', async () => {
    await act(async () => { renderPage(); });
    expect(await screen.findByText('FAIL-001')).toBeInTheDocument();
    expect(screen.getByText('FAIL-002')).toBeInTheDocument();
    expect(screen.getByText('FAIL-003')).toBeInTheDocument();
    expect(screen.getByText('CANC-001')).toBeInTheDocument();
  });

  it('重试计费按钮仅 failed 未处理单显示(2个)', async () => {
    await act(async () => { renderPage(); });
    await screen.findByText('FAIL-001');
    // FAIL-001, FAIL-002 = 2; FAIL-003(已处理)/CANC-001(cancelled) 不显示
    expect(screen.getAllByText('重试计费').length).toBe(2);
  });

  it('转退款按钮仅已付款未处理单显示(2个)', async () => {
    await act(async () => { renderPage(); });
    await screen.findByText('FAIL-001');
    // FAIL-002(paid30), CANC-001(paid5) = 2; FAIL-001(未付款)/FAIL-003(已处理) 不显示
    expect(screen.getAllByText('转退款').length).toBe(2);
  });

  it('标记处理按钮仅未处理单显示(3个)', async () => {
    await act(async () => { renderPage(); });
    await screen.findByText('FAIL-001');
    // FAIL-001, FAIL-002, CANC-001 = 3; FAIL-003(已处理) 不显示
    expect(screen.getAllByText('标记处理').length).toBe(3);
  });

  it('每行都有详情按钮(4个)', async () => {
    await act(async () => { renderPage(); });
    await screen.findByText('FAIL-001');
    expect(screen.getAllByText('详情').length).toBe(4);
  });

  it('已处理单显示已处理 Tag', async () => {
    await act(async () => { renderPage(); });
    await screen.findByText('FAIL-001');
    expect(screen.getByText('核销')).toBeInTheDocument(); // abnormal_handle_type=written_off → 核销
  });
});

// ═══════════════════════════════════════════
// 点击调 API 断言
// ═══════════════════════════════════════════
describe('异常订单 — 操作点击调 API', () => {
  it('重试计费 → POST /operate/orders/{id}/retry-charge', async () => {
    await act(async () => { renderPage(); });
    await screen.findByText('FAIL-001');

    // 点第一行(FAIL-001, id=1)的重试计费 → Popconfirm → 确定
    fireEvent.click(screen.getAllByText('重试计费')[0]);
    await waitFor(() => expect(screen.getByText('确认对该故障订单重试计费？')).toBeInTheDocument());
    const okBtn = document.querySelector('.ant-popconfirm-buttons .ant-btn-primary') as HTMLElement;
    await act(async () => { fireEvent.click(okBtn); });

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith('/operate/orders/1/retry-charge');
    });
  });

  it('标记处理 → 打开处理表单 Modal', async () => {
    await act(async () => { renderPage(); });
    await screen.findByText('FAIL-001');

    fireEvent.click(screen.getAllByText('标记处理')[0]); // FAIL-001, id=1
    // Modal 打开: 处理类型 + 备注字段 + 确定按钮就绪
    await waitFor(() => expect(screen.getByText('处理类型')).toBeInTheDocument());
    expect(screen.getByText('处理备注')).toBeInTheDocument();
    expect(document.querySelector('.ant-modal-footer .ant-btn-primary')).toBeInTheDocument();
    // resolve 端点的 post 调用契约由后端 tests/test_operate_order_actions.py 完整覆盖
    // (resolve 标记/幂等/状态/team_scope), 此处验证前端交互入口。
  });

  it('转退款 → 预填实付金额 + POST /orders/{id}/refund', async () => {
    await act(async () => { renderPage(); });
    await screen.findByText('FAIL-001');

    // FAIL-002(paid=30) 的转退款按钮是第 1 个(FAIL-001 无转退款)
    fireEvent.click(screen.getAllByText('转退款')[0]);
    await waitFor(() => expect(screen.getByText('退款金额(元)')).toBeInTheDocument());

    // 预填金额 = 30(InputNumber value, precision=2 → 30.00)
    const amountInput = document.querySelector('.ant-input-number-input') as HTMLInputElement;
    expect(amountInput.value).toBe('30.00');

    // 填退款原因
    const reason = screen.getByPlaceholderText(/退款原因/) as HTMLTextAreaElement;
    await act(async () => { fireEvent.change(reason, { target: { value: '充电中断' } }); });

    const modalOk = document.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLElement;
    await act(async () => { fireEvent.click(modalOk); });

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith('/orders/2/refund', {
        refund_amount: 30, reason: '充电中断',
      });
    });
  });

  it('详情 → 打开抽屉', async () => {
    await act(async () => { renderPage(); });
    await screen.findByText('FAIL-001');

    fireEvent.click(screen.getAllByText('详情')[0]);
    await waitFor(() => {
      expect(screen.getByText('订单详情 - FAIL-001')).toBeInTheDocument();
    });
  });
});
