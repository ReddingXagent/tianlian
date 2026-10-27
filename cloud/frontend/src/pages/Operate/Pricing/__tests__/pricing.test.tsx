/**
 * 定价管理 — Vitest 单元测试
 * 覆盖: 5类定价组件渲染 + 时段定义CRUD + 主页Tab切换
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

// 卡 971f853e: Pricing 页改用 fetchAllPages 拉站点/设备全量, mock 需补相应导出
vi.mock('../../../api', () => ({
  default: mockApi,
  stationAPI: { list: vi.fn(() => Promise.resolve({ data: { items: [], total: 0 } })) },
  deviceAPI: { list: vi.fn(() => Promise.resolve({ data: { items: [], total: 0 } })) },
  fetchAllPages: vi.fn(async () => []),
}));
vi.mock('../../../api/pricing', () => ({
  timeSlotAPI: {
    list: vi.fn(() => Promise.resolve({ data: { items: [] } })),
    get: vi.fn(() => Promise.resolve({ data: {} })),
    create: vi.fn(() => Promise.resolve({ data: {} })),
    update: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
  },
  energyPriceAPI: {
    list: vi.fn(() => Promise.resolve({ data: { items: [] } })),
    get: vi.fn(() => Promise.resolve({ data: {} })),
    create: vi.fn(() => Promise.resolve({ data: {} })),
    update: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
  },
  serviceFeeAPI: {
    list: vi.fn(() => Promise.resolve({ data: { items: [] } })),
    get: vi.fn(() => Promise.resolve({ data: {} })),
    create: vi.fn(() => Promise.resolve({ data: {} })),
    update: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
  },
  parkingPriceAPI: {
    list: vi.fn(() => Promise.resolve({ data: { items: [] } })),
    get: vi.fn(() => Promise.resolve({ data: {} })),
    create: vi.fn(() => Promise.resolve({ data: {} })),
    update: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
  },
  occupancyFeeAPI: {
    list: vi.fn(() => Promise.resolve({ data: { items: [] } })),
    get: vi.fn(() => Promise.resolve({ data: {} })),
    create: vi.fn(() => Promise.resolve({ data: {} })),
    update: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
  },
  reservationFeeAPI: {
    list: vi.fn(() => Promise.resolve({ data: { items: [] } })),
    get: vi.fn(() => Promise.resolve({ data: {} })),
    create: vi.fn(() => Promise.resolve({ data: {} })),
    update: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
  },
  orderEstimateAPI: {
    estimate: vi.fn(() => Promise.resolve({ data: {} })),
  },
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

// 导入组件
import PricingPage from '../index';
import TimeSlotDefinitions from '../TimeSlotDefinitions';
import EnergyPricing from '../EnergyPricing';
import ServicePricing from '../ServicePricing';
import ParkingPricing from '../ParkingPricing';
import OccupancyPricing from '../OccupancyPricing';
import ReservationPricing from '../ReservationPricing';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
});

// ═══════════════════════════════════════════
// 辅助函数
// ═══════════════════════════════════════════
function clickTab(label: string) {
  const tabs = document.querySelectorAll('.ant-tabs-tab');
  for (let i = 0; i < tabs.length; i++) {
    if (tabs[i].textContent?.includes(label)) {
      fireEvent.click(tabs[i]);
      return;
    }
  }
}

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

describe('定价管理主页', () => {
  it('渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><PricingPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('显示3个Tab标签', () => {
    render(<BrowserRouter><PricingPage /></BrowserRouter>);
    expect(screen.getByText(/充电费/)).toBeInTheDocument();
    expect(screen.getByText(/V2G放电价/)).toBeInTheDocument();
    expect(screen.getByText(/平台费率/)).toBeInTheDocument();
  });

  it('默认激活充电费Tab', () => {
    render(<BrowserRouter><PricingPage /></BrowserRouter>);
    const activeTab = document.querySelector('.ant-tabs-tab-active');
    expect(activeTab?.textContent).toContain('充电费');
  });

  it('点击Tab切换到充电费', () => {
    render(<BrowserRouter><PricingPage /></BrowserRouter>);
    clickTab('充电费');
    const activeTab = document.querySelector('.ant-tabs-tab-active');
    expect(activeTab?.textContent).toContain('充电费');
  });

  it('渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><TimeSlotDefinitions /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('显示新增时段按钮', () => {
    render(<BrowserRouter><TimeSlotDefinitions /></BrowserRouter>);
    expect(screen.getByText('新增时段')).toBeInTheDocument();
  });

  it('显示刷新按钮', () => {
    render(<BrowserRouter><TimeSlotDefinitions /></BrowserRouter>);
    expect(screen.getByText('刷新')).toBeInTheDocument();
  });

  it('点击新增打开Modal', async () => {
    await act(async () => {
      render(<BrowserRouter><TimeSlotDefinitions /></BrowserRouter>);
    });
    fireEvent.click(screen.getByText('新增时段'));
    await waitFor(() => {
      expect(screen.getByText('新增时段定义')).toBeInTheDocument();
    });
  });

  it('Modal包含必要表单字段', async () => {
    await act(async () => {
      render(<BrowserRouter><TimeSlotDefinitions /></BrowserRouter>);
    });
    fireEvent.click(screen.getByText('新增时段'));
    await waitFor(() => {
      expect(screen.getByText('新增时段定义')).toBeInTheDocument();
    });
    // 表单字段label可能在表格header和表单中都出现，用getAllByText
    expect(screen.getAllByText('名称').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('时段类型').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('开始时间').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('结束时间').length).toBeGreaterThanOrEqual(1);
  });
});

describe('充电费定价', () => {
  it('渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><EnergyPricing /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('显示新增电价按钮', () => {
    render(<BrowserRouter><EnergyPricing /></BrowserRouter>);
    expect(screen.getByText('新增电价')).toBeInTheDocument();
  });

  it('点击新增打开Modal', async () => {
    await act(async () => {
      render(<BrowserRouter><EnergyPricing /></BrowserRouter>);
    });
    fireEvent.click(screen.getByText('新增电价'));
    await waitFor(() => {
      expect(screen.getByText('新增充电费定价')).toBeInTheDocument();
    });
  });
});

describe('服务费定价', () => {
  it('渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><ServicePricing /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('显示新增服务费按钮', () => {
    render(<BrowserRouter><ServicePricing /></BrowserRouter>);
    expect(screen.getByText('新增服务费')).toBeInTheDocument();
  });

  it('点击新增打开Modal', async () => {
    await act(async () => {
      render(<BrowserRouter><ServicePricing /></BrowserRouter>);
    });
    fireEvent.click(screen.getByText('新增服务费'));
    await waitFor(() => {
      expect(screen.getByText('新增服务费定价')).toBeInTheDocument();
    });
  });
});

describe('停车费定价', () => {
  it('渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><ParkingPricing /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('显示新增停车费按钮', () => {
    render(<BrowserRouter><ParkingPricing /></BrowserRouter>);
    expect(screen.getByText('新增停车费')).toBeInTheDocument();
  });

  it('点击新增打开Modal', async () => {
    await act(async () => {
      render(<BrowserRouter><ParkingPricing /></BrowserRouter>);
    });
    fireEvent.click(screen.getByText('新增停车费'));
    await waitFor(() => {
      expect(screen.getByText('新增停车费定价')).toBeInTheDocument();
    });
  });
});

describe('占桩费定价', () => {
  it('渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><OccupancyPricing /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('显示新增占桩费按钮', () => {
    render(<BrowserRouter><OccupancyPricing /></BrowserRouter>);
    expect(screen.getByText('新增占桩费')).toBeInTheDocument();
  });

  it('点击新增打开Modal', async () => {
    await act(async () => {
      render(<BrowserRouter><OccupancyPricing /></BrowserRouter>);
    });
    fireEvent.click(screen.getByText('新增占桩费'));
    await waitFor(() => {
      expect(screen.getByText('新增占桩费定价')).toBeInTheDocument();
    });
  });
});

describe('预约费定价', () => {
  it('渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><ReservationPricing /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('显示新增预约费按钮', () => {
    render(<BrowserRouter><ReservationPricing /></BrowserRouter>);
    expect(screen.getByText('新增预约费')).toBeInTheDocument();
  });

  it('点击新增打开Modal', async () => {
    await act(async () => {
      render(<BrowserRouter><ReservationPricing /></BrowserRouter>);
    });
    fireEvent.click(screen.getByText('新增预约费'));
    await waitFor(() => {
      expect(screen.getByText('新增预约费定价')).toBeInTheDocument();
    });
  });
});
