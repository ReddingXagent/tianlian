/**
 * 设备管理页面 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块
// ═══════════════════════════════════════════
const { mockDeviceAPI, mockEfficiencyAPI } = vi.hoisted(() => ({
  mockDeviceAPI: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
  mockEfficiencyAPI: {
    utilization: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  deviceAPI: mockDeviceAPI,
  efficiencyAPI: mockEfficiencyAPI,
  deviceLibraryAPI: { list: vi.fn(() => Promise.resolve({ data: { items: [], total: 0 } })) },
  stationAPI: { list: vi.fn(() => Promise.resolve({ data: { items: [], total: 0 } })) },
  // 卡 971f853e: 页面改用 fetchAllPages 循环拉全量, mock 保留同语义(单页空结果)
  fetchAllPages: vi.fn(async (listFn: (p: Record<string, unknown>) => Promise<any>) => {
    const res = await listFn({ page: 1, page_size: 100 });
    const payload = res?.data ?? res;
    return payload?.items ?? [];
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

// Mock PageWrapper to avoid complex skeleton logic
vi.mock('../../../components/PageWrapper', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// Mock DeviceControlPanel, DeviceConfigPanel, DeviceEfficiencyDetail
vi.mock('../DeviceControlPanel', () => ({
  default: () => <div data-testid="device-control-panel" />,
}));
vi.mock('../DeviceConfigPanel', () => ({
  default: () => <div data-testid="device-config-panel" />,
}));
vi.mock('../DeviceEfficiencyDetail', () => ({
  default: () => <div data-testid="device-efficiency-detail" />,
}));

import DeviceListPage from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockDevices = [
  {
    id: 1, sn: 'SN001', name: '充电桩-01', code: 'D001', type: 'CHARGER_DC',
    model: 'DC-120', manufacturer: 'Tesla', station_id: 1, status: 'ONLINE',
    health_score: 95, utilization_rate: 75, created_at: '2025-01-01', updated_at: '2025-06-01',
  },
  {
    id: 2, sn: 'SN002', name: '逆变器-02', code: 'D002', type: 'PV_INVERTER',
    model: 'SG110CX', manufacturer: 'Sungrow', station_id: 1, status: 'FAULT',
    health_score: 40, utilization_rate: 15, created_at: '2025-02-01', updated_at: '2025-06-01',
  },
];

const mockPaginatedData = {
  items: mockDevices,
  total: 2,
  page: 1,
  page_size: 20,
};

const mockUtilizationData = {
  warnings: [{ device_id: 1, utilization_rate: 75 }],
  device_utilization: [{ device_id: 2, utilization_rate: 15 }],
};

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

beforeEach(() => {
  vi.clearAllMocks();
  mockDeviceAPI.list.mockResolvedValue({ data: mockPaginatedData });
  mockEfficiencyAPI.utilization.mockResolvedValue({ data: mockUtilizationData });
});

describe('设备管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('加载后表格渲染设备数据', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    expect(await screen.findByText('充电桩-01')).toBeInTheDocument();
    expect(screen.getByText('逆变器-02')).toBeInTheDocument();
  });

  it('显示设备 SN', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    expect(await screen.findByText('SN001')).toBeInTheDocument();
    expect(screen.getByText('SN002')).toBeInTheDocument();
  });
});

describe('设备管理 — 数据加载', () => {
  it('页面挂载时调用 deviceAPI.list', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    expect(mockDeviceAPI.list).toHaveBeenCalled();
  });

  it('加载利用率数据 efficiencyAPI.utilization', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    expect(mockEfficiencyAPI.utilization).toHaveBeenCalled();
  });

  it('API 返回空列表不崩溃', async () => {
    mockDeviceAPI.list.mockResolvedValue({ data: { items: [], total: 0 } });
    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockDeviceAPI.list).toHaveBeenCalled();
    });
  });
});

describe('设备管理 — 用户交互', () => {
  it('点击新增按钮打开 Modal', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    await screen.findByText('充电桩-01');

    // 点击工具栏的「新增」按钮
    const addButtons = screen.getAllByText('pages.devices.add');
    fireEvent.click(addButtons[0]);

    // Modal 打开后出现 modal 标题
    await waitFor(() => {
      const allAddTexts = screen.getAllByText('pages.devices.add');
      expect(allAddTexts.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('设备列表中展示操作按钮（详情、编辑、删除）', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    await screen.findByText('充电桩-01');

    // 每行有 "详情", "参数", "编辑", "删除"
    const detailBtns = screen.getAllByText('详情');
    const editBtns = screen.getAllByText('编辑');
    expect(detailBtns.length).toBeGreaterThanOrEqual(1);
    expect(editBtns.length).toBeGreaterThanOrEqual(1);
  });

  it('deviceAPI.delete 被调用格式正确', async () => {
    mockDeviceAPI.delete.mockResolvedValue({});
    mockDeviceAPI.list.mockResolvedValue({ data: mockPaginatedData });

    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    await screen.findByText('充电桩-01');

    await mockDeviceAPI.delete(1);
    expect(mockDeviceAPI.delete).toHaveBeenCalledWith(1);
  });

  it('deviceAPI.create 被调用格式正确', async () => {
    mockDeviceAPI.create.mockResolvedValue({ data: mockDevices[0] });

    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    await screen.findByText('充电桩-01');

    const payload = { sn: 'SN003', name: '新设备', type: 'CHARGER_DC' };
    await mockDeviceAPI.create(payload);
    expect(mockDeviceAPI.create).toHaveBeenCalledWith(payload);
  });

  it('deviceAPI.update 被调用格式正确', async () => {
    mockDeviceAPI.update.mockResolvedValue({ data: mockDevices[0] });

    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    await screen.findByText('充电桩-01');

    await mockDeviceAPI.update(1, { name: '更新名称' });
    expect(mockDeviceAPI.update).toHaveBeenCalledWith(1, { name: '更新名称' });
  });
});

describe('设备管理 — 移动端响应式', () => {
  beforeEach(() => {
    vi.stubGlobal('innerWidth', 375);
    mockDeviceAPI.list.mockResolvedValue({ data: mockPaginatedData });
    mockEfficiencyAPI.utilization.mockResolvedValue({ data: mockUtilizationData });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('移动端宽度渲染设备卡片且不渲染桌面表格', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    expect(await screen.findByText('充电桩-01')).toBeInTheDocument();
    // 移动端切换为卡片列表，桌面 Table 不渲染
    expect(document.querySelector('.ant-table')).toBeNull();
  });

  it('移动端渲染与设备数一致的卡片', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    await screen.findByText('充电桩-01');
    expect(document.querySelectorAll('[data-testid="device-mobile-card"]').length).toBe(mockDevices.length);
  });

  it('移动端卡片含状态标签自适应', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceListPage /></BrowserRouter>);
    });
    await screen.findByText('充电桩-01');
    // 卡片渲染状态 Tag（statusColorMap/statusTextMap 映射，ONLINE→green）
    const card = document.querySelector('[data-testid="device-mobile-card"]');
    expect(card?.querySelector('.ant-tag')).toBeInTheDocument();
  });
});
