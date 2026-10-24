/**
 * 订单管理 + 退款 — Vitest 单元测试
 * 测试覆盖: 订单列表渲染 / 订单详情费用拆解 / 退款审核
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock 数据
// ═══════════════════════════════════════════
const mockOrdersData = {
  items: [
    {
      id: 1, order_no: 'TL-ORD-001', station_name: '郑州充电站A', plate_number: '豫A12345',
      user_type: 'app', charged_kwh: 50.5, total_amount: 80.00, paid_amount: 75.00,
      discount_amount: 5.00, order_status: 'completed', payment_status: 'paid',
      payment_method: 'IM-B支付', duration_minutes: 60, created_at: '2026-07-01T10:00:00Z',
    },
    {
      id: 2, order_no: 'TL-ORD-002', station_name: '广州充电站B', plate_number: '粤B67890',
      user_type: 'enterprise', charged_kwh: 100.0, total_amount: 150.00, paid_amount: 150.00,
      discount_amount: 0, order_status: 'completed', payment_status: 'paid',
      payment_method: '支付宝', duration_minutes: 120, created_at: '2026-07-02T14:00:00Z',
    },
    {
      id: 3, order_no: 'TL-ORD-003', station_name: '南京储能站A', plate_number: '苏A99999',
      user_type: 'vin', charged_kwh: 0, total_amount: 0, paid_amount: 0,
      discount_amount: 0, order_status: 'failed', payment_status: 'unpaid',
      payment_method: null, duration_minutes: 5, created_at: '2026-07-03T09:00:00Z',
    },
  ],
  total: 3, page: 1, page_size: 20,
};

const mockFailedOrders = {
  items: [
    {
      id: 3, order_no: 'TL-ORD-003', station_name: '南京储能站A', plate_number: '苏A99999',
      user_type: 'vin', charged_kwh: 0, total_amount: 0, paid_amount: 0,
      order_status: 'failed', payment_status: 'unpaid', duration_minutes: 5,
      created_at: '2026-07-03T09:00:00Z',
    },
  ],
  total: 1, page: 1, page_size: 20,
};

const mockCancelledOrders = {
  items: [],
  total: 0, page: 1, page_size: 20,
};

const mockFeeItems = [
  { id: 1, order_id: 1, fee_type: 'electricity', fee_name: '平段电费', quantity: 50.5, unit_price: 0.8, amount: 40.40, unit: 'kWh', remark: null, created_at: '2026-07-01T10:00:00Z' },
  { id: 2, order_id: 1, fee_type: 'service', fee_name: '服务费', quantity: 50.5, unit_price: 0.5, amount: 25.25, unit: 'kWh', remark: null, created_at: '2026-07-01T10:00:00Z' },
  { id: 3, order_id: 1, fee_type: 'parking', fee_name: '停车费', quantity: 1.0, unit_price: 10.0, amount: 10.00, unit: '小时', remark: null, created_at: '2026-07-01T10:00:00Z' },
  { id: 4, order_id: 1, fee_type: 'occupancy', fee_name: '占桩费', quantity: 15, unit_price: 0.2, amount: 3.00, unit: '分钟', remark: null, created_at: '2026-07-01T10:00:00Z' },
  { id: 5, order_id: 1, fee_type: 'reservation', fee_name: '预约费', quantity: 5, unit_price: 0.3, amount: 1.35, unit: '分钟', remark: null, created_at: '2026-07-01T10:00:00Z' },
];

const mockRefunds = [
  { id: 10, order_id: 1, user_id: 1, refund_amount: 30.00, reason: '充电中断', status: 'pending', reviewer_id: null, reviewed_at: null, refunded_at: null, reject_reason: null, created_at: '2026-07-04T10:00:00Z' },
  { id: 11, order_id: 2, user_id: 2, refund_amount: 50.00, reason: '多收费', status: 'refunded', reviewer_id: 1, reviewed_at: '2026-07-03T15:00:00Z', refunded_at: '2026-07-03T16:00:00Z', reject_reason: null, created_at: '2026-07-02T12:00:00Z' },
];

// 订单充电曲线 — 3 个时间序列点 (功率/电量/SOC)
const mockChargeCurve = {
  order_id: 1,
  total: 3,
  items: [
    { record_time: '2026-07-01T10:00:00', current_power: 30.0, energy_this_minute: 0.5, voltage: 400.0, current: 75.0, soc: 20.0 },
    { record_time: '2026-07-01T10:01:00', current_power: 60.0, energy_this_minute: 1.0, voltage: 400.0, current: 150.0, soc: 21.0 },
    { record_time: '2026-07-01T10:02:00', current_power: 90.0, energy_this_minute: 1.5, voltage: 400.0, current: 225.0, soc: 22.0 },
  ],
};

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

vi.mock('echarts-for-react', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock'),
}));

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
// 导入组件 (在 mock 之后)
// ═══════════════════════════════════════════
import OrderListPage from '../OrderList';
import OrderDetailDrawer from '../OrderDetail';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  // 模拟已登录用户 — PendingRefunds 审核人 ID 从此处读取
  localStorage.clear();
  localStorage.setItem('admin_user', JSON.stringify({ id: '42', username: 'tester', role: 'admin', user_type: 'admin' }));
  mockApi.get.mockImplementation((url: string) => {
    // charge-curve 路径含 /operate/orders, 必须在通用订单判断之前匹配
    if (url.match(/\/operate\/orders\/\d+\/charge-curve/)) return Promise.resolve({ data: mockChargeCurve });
    if (url.includes('/operate/orders') && url.includes('status=failed')) return Promise.resolve({ data: mockFailedOrders });
    if (url.includes('/operate/orders') && url.includes('status=cancelled')) return Promise.resolve({ data: mockCancelledOrders });
    if (url.includes('/operate/orders')) return Promise.resolve({ data: mockOrdersData });
    if (url.match(/\/orders\/\d+\/fee-items/)) return Promise.resolve({ data: mockFeeItems });
    if (url.match(/\/orders\/\d+\/refunds/)) return Promise.resolve({ data: mockRefunds });
    return Promise.resolve({ data: [] });
  });
  mockApi.post.mockResolvedValue({ data: { id: 1 } });
  mockApi.put.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
});

// ═══════════════════════════════════════════
// 测试: 订单列表渲染
// ═══════════════════════════════════════════
describe('订单列表 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><OrderListPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('加载后表格渲染订单数据', async () => {
    await act(async () => {
      render(<BrowserRouter><OrderListPage /></BrowserRouter>);
    });
    expect(await screen.findByText('TL-ORD-001')).toBeInTheDocument();
    expect(screen.getByText('TL-ORD-002')).toBeInTheDocument();
    expect(screen.getByText('TL-ORD-003')).toBeInTheDocument();
  });

  it('统计卡片显示', async () => {
    await act(async () => {
      render(<BrowserRouter><OrderListPage /></BrowserRouter>);
    });
    await screen.findByText('TL-ORD-001');
    expect(screen.getByText('订单总数')).toBeInTheDocument();
    // 总金额 appears in both stat card and column header
    expect(screen.getAllByText('总金额').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('已支付').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('待支付')).toBeInTheDocument();
  });

  it('站点名正确显示', async () => {
    await act(async () => {
      render(<BrowserRouter><OrderListPage /></BrowserRouter>);
    });
    await screen.findByText('TL-ORD-001');
    expect(screen.getByText('郑州充电站A')).toBeInTheDocument();
    expect(screen.getByText('广州充电站B')).toBeInTheDocument();
    expect(screen.getByText('南京储能站A')).toBeInTheDocument();
  });

  it('点击详情按钮打开 Drawer', async () => {
    await act(async () => {
      render(<BrowserRouter><OrderListPage /></BrowserRouter>);
    });
    await screen.findByText('TL-ORD-001');

    const detailBtns = screen.getAllByText('详情');
    fireEvent.click(detailBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('订单详情 - TL-ORD-001')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 测试: 订单详情费用拆解
// ═══════════════════════════════════════════
describe('订单详情 — 5项费用拆解', () => {
  it('Drawer 打开后加载费用明细', async () => {
    const order = mockOrdersData.items[0];
    await act(async () => {
      render(
        <BrowserRouter>
          <OrderDetailDrawer open={true} order={order} onClose={() => {}} />
        </BrowserRouter>
      );
    });

    // 等待费用明细加载 — 平段电费 is unique (only in table)
    await waitFor(() => {
      expect(screen.getByText('平段电费')).toBeInTheDocument();
    });
    // 服务费/停车费/占桩费/预约费 appear in both Statistic title and table — use getAllByText
    expect(screen.getAllByText('服务费').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('停车费').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('占桩费').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('预约费').length).toBeGreaterThanOrEqual(1);
  });

  it('5项费用汇总金额正确', async () => {
    const order = mockOrdersData.items[0];
    await act(async () => {
      render(
        <BrowserRouter>
          <OrderDetailDrawer open={true} order={order} onClose={() => {}} />
        </BrowserRouter>
      );
    });

    // 等待费用明细加载
    await waitFor(() => {
      expect(screen.getByText('平段电费')).toBeInTheDocument();
    });
    // 电费 Statistic renders value as 40.4 (Statistic strips trailing zeros)
    // Table amount column shows ¥40.40
    expect(screen.getByText('¥40.40')).toBeInTheDocument();
    expect(screen.getByText('¥25.25')).toBeInTheDocument();
    expect(screen.getByText('¥10.00')).toBeInTheDocument();
    expect(screen.getByText('¥3.00')).toBeInTheDocument();
    expect(screen.getByText('¥1.35')).toBeInTheDocument();
  });

  it('订单基本信息正确展示', async () => {
    const order = mockOrdersData.items[0];
    await act(async () => {
      render(
        <BrowserRouter>
          <OrderDetailDrawer open={true} order={order} onClose={() => {}} />
        </BrowserRouter>
      );
    });

    expect(screen.getByText('基本信息')).toBeInTheDocument();
    // TL-ORD-001 appears in Drawer title and Descriptions
    expect(screen.getAllByText('TL-ORD-001').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('郑州充电站A')).toBeInTheDocument();
    expect(screen.getByText('豫A12345')).toBeInTheDocument();
    // user_type 'app' rendered as raw value in Drawer Descriptions
    expect(screen.getAllByText('app').length).toBeGreaterThanOrEqual(1);
  });

  it('无费用明细时显示空状态', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.match(/\/orders\/\d+\/fee-items/)) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });

    const order = mockOrdersData.items[0];
    await act(async () => {
      render(
        <BrowserRouter>
          <OrderDetailDrawer open={true} order={order} onClose={() => {}} />
        </BrowserRouter>
      );
    });

    await waitFor(() => {
      expect(screen.getByText('暂无费用明细，请先结算订单')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 测试: 退款审核 (通过 PendingRefunds 组件)
// ═══════════════════════════════════════════
describe('退款审核', () => {
  // 动态导入避免 mock 顺序问题
  const PendingRefundsModule = React.lazy(() => import('../../Refunds/PendingRefunds'));

  it('待审核退款列表渲染', async () => {
    // 模拟有退款中的订单
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/operate/orders')) {
        return Promise.resolve({
          data: {
            items: [{
              id: 1, order_no: 'TL-ORD-001', station_name: '郑州充电站A', plate_number: '豫A12345',
              total_amount: 80.00, paid_amount: 75.00,
            }],
            total: 1,
          },
        });
      }
      if (url.match(/\/orders\/\d+\/refunds/)) {
        return Promise.resolve({ data: mockRefunds.filter(r => r.status === 'pending') });
      }
      return Promise.resolve({ data: [] });
    });

    const PendingRefunds = (await import('../../Refunds/PendingRefunds')).default;

    await act(async () => {
      render(<BrowserRouter><PendingRefunds /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('待审核退款')).toBeInTheDocument();
    });
  });

  it('退款批准操作调用正确 API', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/operate/orders')) {
        return Promise.resolve({
          data: {
            items: [{
              id: 1, order_no: 'TL-ORD-001', station_name: '郑州充电站A', plate_number: '豫A12345',
              total_amount: 80.00, paid_amount: 75.00,
            }],
            total: 1,
          },
        });
      }
      if (url.match(/\/orders\/\d+\/refunds/)) {
        return Promise.resolve({ data: [mockRefunds[0]] });
      }
      return Promise.resolve({ data: [] });
    });
    mockApi.post.mockResolvedValue({ data: { id: 10, status: 'approved' } });

    const PendingRefunds = (await import('../../Refunds/PendingRefunds')).default;

    await act(async () => {
      render(<BrowserRouter><PendingRefunds /></BrowserRouter>);
    });

    // 等待数据加载 — refund_amount 30.00 is rendered in table with ¥ prefix
    await waitFor(() => {
      expect(screen.getByText('¥30.00')).toBeInTheDocument();
    });

    // 点击批准按钮
    const approveBtn = screen.getByText('批准');
    await act(async () => {
      fireEvent.click(approveBtn);
    });

    // 确认弹窗 — Popconfirm 的按钮
    await waitFor(() => {
      expect(screen.getByText('确认批准此退款？')).toBeInTheDocument();
    });

    // 点击 Popconfirm 确定按钮
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
});

// ═══════════════════════════════════════════
// 测试: 充电曲线图表 (OrderDetail 内 echarts 时间序列)
// ═══════════════════════════════════════════
describe('订单详情 — 充电曲线图表', () => {
  it('有曲线数据时渲染图表', async () => {
    const order = mockOrdersData.items[0];
    await act(async () => {
      render(
        <BrowserRouter>
          <OrderDetailDrawer open={true} order={order} onClose={() => {}} />
        </BrowserRouter>
      );
    });

    // 标题 + echarts 图表渲染
    await waitFor(() => {
      expect(screen.getByText('充电曲线')).toBeInTheDocument();
    });
    expect(screen.getByTestId('echarts-mock')).toBeInTheDocument();
  });

  it('无曲线数据时显示空状态', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.match(/\/orders\/\d+\/fee-items/)) return Promise.resolve({ data: mockFeeItems });
      if (url.match(/\/operate\/orders\/\d+\/charge-curve/)) return Promise.resolve({ data: { order_id: 1, items: [], total: 0 } });
      return Promise.resolve({ data: [] });
    });

    const order = mockOrdersData.items[0];
    await act(async () => {
      render(
        <BrowserRouter>
          <OrderDetailDrawer open={true} order={order} onClose={() => {}} />
        </BrowserRouter>
      );
    });

    await waitFor(() => {
      expect(screen.getByText('暂无充电曲线数据')).toBeInTheDocument();
    });
    // 空状态不应渲染图表
    expect(screen.queryByTestId('echarts-mock')).not.toBeInTheDocument();
  });
});
