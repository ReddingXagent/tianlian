/**
 * 车队五大模块 — Vitest 组件测试
 *
 * 测试：司机管理、碳排放、充电队列、V2G调度、费用结算
 * 覆盖：渲染、Tab切换、表格加载、搜索筛选、Modal打开
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

vi.mock('../../../api', () => ({ default: mockApi }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('echarts-for-react', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock'),
}));

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockDrivers = {
  items: [
    { id: 1, name: '张三', phone: '13800138001', license_no: 'D64123456', license_type: 'C1', status: 'active', total_charge_kwh: 5234.5, total_spent: 4600.00, rating: 4.8, account: { balance: 500.00 } },
    { id: 2, name: '李四', phone: '13900139002', license_no: 'D64789101', license_type: 'B2', status: 'active', total_charge_kwh: 3200.0, total_spent: 2800.00, rating: 4.5, account: { balance: 200.00 } },
  ],
  total: 2,
};

const mockCarbonOverview = {
  enterprise: { id: 1, name: '顺达物流' },
  year: 2026,
  total_charge_kwh: 45678.9,
  total_reduction_kg: 12345.6,
  total_fuel_saved_liters: 25580.0,
  vehicle_count: 8,
  monthly_trend: [
    { month: 1, charge_kwh: 3000, reduction_kg: 800 },
    { month: 2, charge_kwh: 3500, reduction_kg: 950 },
  ],
};

const mockQueue = [
  { id: 1, vehicle_id: 101, priority: 50, status: 'waiting', required_energy_kwh: 40.5, current_soc: 0.3, target_soc: 0.8, estimated_wait_minutes: 15 },
  { id: 2, vehicle_id: 102, priority: 80, status: 'waiting', required_energy_kwh: 25.0, current_soc: 0.5, target_soc: 0.8, estimated_wait_minutes: 5 },
];

const mockV2GStatus = {
  enterprise_id: 1,
  plan_status_counts: { scheduled: 3, completed: 5 },
  recent_plans: [
    { id: 1, vehicle_id: 101, plan_date: '2026-07-21', status: 'scheduled', target_soc_min: 0.3, target_soc_max: 0.9 },
  ],
  revenue_summary: { total_revenue: 12500.50, total_discharge_energy_kwh: 3200.0, total_records: 8 },
};

const mockBills = {
  items: [
    { id: 1, bill_no: 'FSB202607001', enterprise_id: 1, bill_period: '2026-07', total_orders: 45, total_amount: 12580.50, paid_amount: 0, balance_amount: 12580.50, status: 'pending', total_energy_kwh: 5234.5 },
    { id: 2, bill_no: 'FSB202606001', enterprise_id: 1, bill_period: '2026-06', total_orders: 52, total_amount: 14300.00, paid_amount: 14300.00, balance_amount: 0, status: 'paid', total_energy_kwh: 6100.0 },
  ],
  total: 2,
};

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  // 默认 API 返回空数据
  mockApi.get.mockResolvedValue({ data: { items: [], total: 0 } });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

// ═══════════════════════════════════════════
// 1. 司机管理页面测试
// ═══════════════════════════════════════════
import FleetDriversPage from '../Drivers';

describe('FleetDriversPage', () => {
  it('渲染司机管理页面', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/drivers')) return Promise.resolve({ data: mockDrivers });
      return Promise.resolve({ data: { items: [] } });
    });

    renderWithRouter(<FleetDriversPage />);

    await waitFor(() => {
      expect(screen.getByText('司机总数')).toBeInTheDocument();
    });
  });

  it('加载并显示司机列表', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/drivers') && !url.includes('account') && !url.includes('transactions')) {
        return Promise.resolve({ data: mockDrivers });
      }
      return Promise.resolve({ data: { items: [] } });
    });

    renderWithRouter(<FleetDriversPage />);

    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument();
      expect(screen.getByText('李四')).toBeInTheDocument();
    });
  });

  it('点击新增司机按钮打开Modal', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/drivers') && !url.includes('account') && !url.includes('transactions')) {
        return Promise.resolve({ data: mockDrivers });
      }
      return Promise.resolve({ data: { items: [] } });
    });

    renderWithRouter(<FleetDriversPage />);

    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument();
    });

    // 点击新增司机按钮
    const addBtns = screen.getAllByText('新增司机');
    fireEvent.click(addBtns[addBtns.length - 1]);

    // Modal 打开后应出现「请输入姓名」placeholder
    await waitFor(() => {
      expect(screen.getByPlaceholderText('司机姓名')).toBeInTheDocument();
    }, { timeout: 3000 });
  });
});

// ═══════════════════════════════════════════
// 2. 碳排放管理页面测试
// ═══════════════════════════════════════════
import FleetCarbonPage from '../Carbon';

describe('FleetCarbonPage', () => {
  it('渲染碳排放页面', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/carbon/overview')) return Promise.resolve({ data: mockCarbonOverview });
      return Promise.resolve({ data: { items: [] } });
    });

    renderWithRouter(<FleetCarbonPage />);

    await waitFor(() => {
      expect(screen.getByText('碳减排概览')).toBeInTheDocument();
    });
  });

  it('显示碳排放统计卡片', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/carbon/overview')) return Promise.resolve({ data: mockCarbonOverview });
      return Promise.resolve({ data: { items: [] } });
    });

    renderWithRouter(<FleetCarbonPage />);

    await waitFor(() => {
      expect(screen.getByText('年度充电量(kWh)')).toBeInTheDocument();
      expect(screen.getByText('碳减排量(kg)')).toBeInTheDocument();
    });
  });

  it('切换到排放因子Tab', async () => {
    mockApi.get.mockResolvedValue({ data: { items: [] } });

    renderWithRouter(<FleetCarbonPage />);

    await waitFor(() => {
      expect(screen.getByText('排放因子')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('排放因子'));

    await waitFor(() => {
      expect(screen.getByText('新增因子')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 3. 充电队列页面测试
// ═══════════════════════════════════════════
import FleetChargingQueuePage from '../ChargingQueue';

describe('FleetChargingQueuePage', () => {
  it('渲染充电队列页面', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/charging/queue')) return Promise.resolve({ data: mockQueue });
      return Promise.resolve({ data: [] });
    });

    renderWithRouter(<FleetChargingQueuePage />);

    await waitFor(() => {
      expect(screen.getByText('队列总数')).toBeInTheDocument();
    });
  });

  it('显示队列中的车辆', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/charging/queue')) return Promise.resolve({ data: mockQueue });
      return Promise.resolve({ data: [] });
    });

    renderWithRouter(<FleetChargingQueuePage />);

    await waitFor(() => {
      expect(screen.getByText('101')).toBeInTheDocument();
      expect(screen.getByText('102')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 4. V2G 调度页面测试
// ═══════════════════════════════════════════
import FleetV2GPage from '../V2G';

describe('FleetV2GPage', () => {
  it('渲染V2G调度页面', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/v2g/status')) return Promise.resolve({ data: mockV2GStatus });
      return Promise.resolve({ data: { items: [] } });
    });

    renderWithRouter(<FleetV2GPage />);

    await waitFor(() => {
      expect(screen.getByText('状态概览')).toBeInTheDocument();
    });
  });

  it('显示V2G统计', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/v2g/status')) return Promise.resolve({ data: mockV2GStatus });
      return Promise.resolve({ data: { items: [] } });
    });

    renderWithRouter(<FleetV2GPage />);

    await waitFor(() => {
      expect(screen.getByText('总收益(¥)')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 5. 费用结算页面测试
// ═══════════════════════════════════════════
import FleetSettlementPage from '../Settlement';

describe('FleetSettlementPage', () => {
  it('渲染费用结算页面', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/settlement/bills')) return Promise.resolve({ data: mockBills });
      return Promise.resolve({ data: { items: [] } });
    });

    renderWithRouter(<FleetSettlementPage />);

    await waitFor(() => {
      expect(screen.getByText('对账账单')).toBeInTheDocument();
    });
  });

  it('显示账单统计', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/settlement/bills')) return Promise.resolve({ data: mockBills });
      if (url.includes('/fleet/settlement/invoices')) return Promise.resolve({ data: { items: [], total: 0 } });
      return Promise.resolve({ data: { items: [] } });
    });

    renderWithRouter(<FleetSettlementPage />);

    // 等待数据加载完成
    await waitFor(() => {
      expect(screen.getByText('账单总数')).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('点击生成账单按钮打开Modal', async () => {
    mockApi.get.mockResolvedValue({ data: { items: [], total: 0 } });

    renderWithRouter(<FleetSettlementPage />);

    await waitFor(() => {
      expect(screen.getByText('生成账单')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('生成账单'));

    await waitFor(() => {
      expect(screen.getByText('账期(月份)')).toBeInTheDocument();
    });
  });
});
