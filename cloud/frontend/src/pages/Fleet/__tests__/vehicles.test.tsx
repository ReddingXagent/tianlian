/**
 * 车队 - 车辆管理页面 Vitest 组件测试
 *
 * 覆盖：列表渲染、搜索筛选、绑定新车Modal、详情Drawer、状态变更、空数据、解绑
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
// 测试数据（字段对齐后端 _vehicle_to_dict）
// ═══════════════════════════════════════════
const mockEnterprises = [{ id: 1, name: '测试物流有限公司' }];
const mockDrivers = {
  items: [{ id: 1, name: '赵刚', phone: '13600136001' }],
};
const mockVehicles = {
  items: [
    { id: 1, enterprise_id: 1, plate_number: '京A·12345', vin: 'LSGAB52L7DF000001', brand: '比亚迪', model: 'T5', driver_name: '赵刚', driver_phone: '13600136001', status: 'active', created_at: '2026-07-01T10:00:00' },
    { id: 2, enterprise_id: 1, plate_number: '京A·23456', vin: 'LSGAB52L7DF000002', brand: '东风', model: '天龙KL', driver_name: '钱明', driver_phone: '13500135002', status: 'maintenance', created_at: '2026-06-15T10:00:00' },
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
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/fleet/enterprises')) return Promise.resolve({ data: mockEnterprises });
    if (url.includes('/fleet/drivers')) return Promise.resolve({ data: mockDrivers });
    if (url.includes('/enterprises/') && url.includes('/vehicles')) return Promise.resolve({ data: mockVehicles });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
});

import FleetVehiclesPage from '../Vehicles';

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
describe('FleetVehiclesPage', () => {
  it('1. 渲染车辆列表与统计卡片', async () => {
    renderWithRouter(<FleetVehiclesPage />);

    await waitFor(() => {
      expect(screen.getByText('京A·12345')).toBeInTheDocument();
    });
    expect(screen.getByText('京A·23456')).toBeInTheDocument();
    // 品牌车型列合并显示为「比亚迪 T5」
    expect(screen.getByText(/比亚迪/)).toBeInTheDocument();
    expect(screen.getByText('车辆总数')).toBeInTheDocument();
    // 「在役」同时出现在统计卡片与 active 状态标签中
    expect(screen.getAllByText('在役').length).toBeGreaterThanOrEqual(1);
  });

  it('2. 搜索车牌号进行筛选', async () => {
    renderWithRouter(<FleetVehiclesPage />);

    await waitFor(() => expect(screen.getByText('京A·12345')).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText('搜索车牌/VIN/司机'), { target: { value: '12345' } });

    await waitFor(() => {
      expect(screen.queryByText('京A·23456')).not.toBeInTheDocument();
    });
    expect(screen.getByText('京A·12345')).toBeInTheDocument();
  });

  it('3. 绑定新车 Modal 打开并提交调用 POST', async () => {
    renderWithRouter(<FleetVehiclesPage />);

    await waitFor(() => expect(screen.getByText('京A·12345')).toBeInTheDocument());

    fireEvent.click(screen.getByText('绑定新车'));

    // Modal 打开
    await waitFor(() => {
      expect(screen.getByPlaceholderText('如 京A·12345')).toBeInTheDocument();
    });

    // 填表
    fireEvent.change(screen.getByPlaceholderText('如 京A·12345'), { target: { value: '京A·99999' } });
    fireEvent.change(screen.getByPlaceholderText('17位车架号'), { target: { value: 'LSGAB52L7DF999999' } });

    // 点 Modal 确认按钮
    const okBtn = document.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLElement;
    fireEvent.click(okBtn);

    await waitFor(() => expect(mockApi.post).toHaveBeenCalled());
    const [url, payload] = mockApi.post.mock.calls[0];
    expect(url).toContain('/vehicles');
    expect(payload.plate_number).toBe('京A·99999');
    expect(payload.vin).toBe('LSGAB52L7DF999999');
  });

  it('4. 点击行打开详情 Drawer', async () => {
    renderWithRouter(<FleetVehiclesPage />);

    await waitFor(() => expect(screen.getByText('京A·12345')).toBeInTheDocument());

    fireEvent.click(screen.getByText('京A·12345'));

    await waitFor(() => {
      expect(screen.getByText(/车辆详情 - 京A·12345/)).toBeInTheDocument();
    });
    // 详情中应包含多标签
    expect(screen.getByText('充电历史')).toBeInTheDocument();
    expect(screen.getByText('V2G收益')).toBeInTheDocument();
  });

  it('5. 状态变更通过 Popconfirm 确认并调用 PATCH', async () => {
    renderWithRouter(<FleetVehiclesPage />);

    await waitFor(() => expect(screen.getByText('京A·12345')).toBeInTheDocument());

    // 点击第一行的「状态」下拉按钮
    const statusBtn = screen.getAllByRole('button', { name: /状态/ })[0];
    fireEvent.click(statusBtn);

    // 选择「转为维修」
    await waitFor(() => expect(screen.getByText('转为维修')).toBeInTheDocument());
    fireEvent.click(screen.getByText('转为维修'));

    // 受控 Popconfirm 弹出，点确认
    await waitFor(() => {
      expect(document.querySelector('.ant-popconfirm-buttons')).toBeInTheDocument();
    });
    const confirmBtn = document.querySelector('.ant-popconfirm-buttons .ant-btn-primary') as HTMLElement;
    fireEvent.click(confirmBtn);

    await waitFor(() => expect(mockApi.patch).toHaveBeenCalled());
    const [url, payload] = mockApi.patch.mock.calls[0];
    expect(url).toContain('/vehicles/1');
    expect(payload).toEqual(expect.objectContaining({ status: 'maintenance' }));
  });

  it('6. 空数据展示空状态', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/enterprises')) return Promise.resolve({ data: mockEnterprises });
      if (url.includes('/fleet/drivers')) return Promise.resolve({ data: mockDrivers });
      if (url.includes('/enterprises/') && url.includes('/vehicles')) return Promise.resolve({ data: { items: [], total: 0 } });
      return Promise.resolve({ data: { items: [] } });
    });

    renderWithRouter(<FleetVehiclesPage />);

    await waitFor(() => {
      expect(screen.getByText('暂无车辆')).toBeInTheDocument();
    });
  });

  it('7. 解绑车辆调用 DELETE', async () => {
    renderWithRouter(<FleetVehiclesPage />);

    await waitFor(() => expect(screen.getByText('京A·12345')).toBeInTheDocument());

    fireEvent.click(screen.getAllByText('解绑')[0]);

    await waitFor(() => {
      expect(document.querySelector('.ant-popconfirm-buttons')).toBeInTheDocument();
    });
    const okBtn = document.querySelector('.ant-popconfirm-buttons .ant-btn-primary') as HTMLElement;
    fireEvent.click(okBtn);

    await waitFor(() => expect(mockApi.delete).toHaveBeenCalled());
    expect(mockApi.delete.mock.calls[0][0]).toContain('/vehicles/1');
  });
});
