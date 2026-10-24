/**
 * 车队 - 车辆保险页面 Vitest 组件测试
 *
 * 覆盖：渲染+统计 / 保险列表 / 类型筛选(带query) / 新增Modal / 编辑回填+PUT / 删除DELETE / 错误降级
 *
 * mock 模式对齐 extension-modules.test.tsx；字段契约对齐 backend _insurance_to_dict
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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
// 测试数据（字段对齐 _insurance_to_dict）
// ═══════════════════════════════════════════
const mockEnterprises = {
  items: [{ id: 1, name: '顺达物流有限公司' }],
};

const mockVehicles = {
  items: [
    { id: 101, plate_number: '京A12345' },
    { id: 102, plate_number: '京B67890' },
  ],
};

const mockInsurances = {
  items: [
    { id: 1, vehicle_id: 101, insurance_type: 'compulsory', company: '人保财险', policy_no: 'P2026001', start_date: '2026-01-01', end_date: '2027-01-01', premium: 950, attachment_url: null },
    { id: 2, vehicle_id: 101, insurance_type: 'commercial', company: '平安产险', policy_no: 'P2026002', start_date: '2026-03-01', end_date: '2027-03-01', premium: 4500, attachment_url: null },
  ],
};

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

const defaultGet = (url: string): Promise<any> => {
  if (url.includes('/fleet/enterprises')) return Promise.resolve({ data: mockEnterprises });
  if (url.includes('/enterprises/') && url.includes('/vehicles')) return Promise.resolve({ data: mockVehicles });
  if (url.includes('/fleet/vehicles') && url.includes('/insurance')) return Promise.resolve({ data: mockInsurances });
  return Promise.resolve({ data: { items: [] } });
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mockApi.get.mockImplementation(defaultGet);
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
});

import FleetVehicleInsurancePage from '../VehicleInsurance';

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
describe('FleetVehicleInsurancePage 车辆保险', () => {
  it('1. 渲染页面与统计卡片（企业→车辆联动，拉取保险列表）', async () => {
    renderWithRouter(<FleetVehicleInsurancePage />);

    await waitFor(() => {
      expect(screen.getByText('保单总数')).toBeInTheDocument();
    });
    expect(screen.getByText('生效保单')).toBeInTheDocument();
    expect(mockApi.get).toHaveBeenCalledWith('/fleet/enterprises');
  });

  it('2. 加载并显示保险列表（保险公司/保单号/生效状态）', async () => {
    renderWithRouter(<FleetVehicleInsurancePage />);

    await waitFor(() => {
      expect(screen.getByText('人保财险')).toBeInTheDocument();
    }, { timeout: 3000 });
    expect(screen.getByText('平安产险')).toBeInTheDocument();
    expect(screen.getByText('P2026001')).toBeInTheDocument();
    // 两条均为未来到期 → 生效中
    expect(screen.getAllByText('生效中').length).toBeGreaterThanOrEqual(1);
  });

  it('3. 类型筛选切换会以 insurance_type query 重新请求', async () => {
    const { container } = renderWithRouter(<FleetVehicleInsurancePage />);

    await waitFor(() => expect(screen.getByText('人保财险')).toBeInTheDocument(), { timeout: 3000 });

    // 第3个 Select 为险种筛选（企业 / 车辆 / 筛选）
    const filterSelector = container.querySelectorAll('.ant-select-selector')[2] as HTMLElement;
    fireEvent.mouseDown(filterSelector);

    // 下拉出现后点「商业险」
    const dropdown = await waitFor(() => {
      const el = document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)') as HTMLElement;
      expect(el).toBeInTheDocument();
      return el;
    });
    fireEvent.click(within(dropdown).getByText('商业险'));

    await waitFor(() => {
      const insCalls = mockApi.get.mock.calls.filter(c => c[0].includes('/insurance'));
      const last = insCalls[insCalls.length - 1];
      expect(last[1]?.params?.insurance_type).toBe('commercial');
    });
  });

  it('4. 点击「新增保险」打开创建Modal', async () => {
    renderWithRouter(<FleetVehicleInsurancePage />);

    // 等列表数据出现 → vehicleId 已就绪 → 「新增保险」按钮可点
    await waitFor(() => expect(screen.getByText('人保财险')).toBeInTheDocument(), { timeout: 3000 });
    const addBtn = screen.getByRole('button', { name: /新增保险/ });
    expect(addBtn).not.toBeDisabled();
    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(screen.getByText('新增保险记录')).toBeInTheDocument();
    });
    // 用 placeholder 断言表单字段（避免 antd required label 文本多节点歧义）
    expect(screen.getByPlaceholderText('保险公司')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('保单号')).toBeInTheDocument();
  });

  it('5. 点击「编辑」回填表单并调用 PUT 更新', async () => {
    renderWithRouter(<FleetVehicleInsurancePage />);

    await waitFor(() => expect(screen.getByText('人保财险')).toBeInTheDocument(), { timeout: 3000 });

    fireEvent.click(screen.getAllByText('编辑')[0]);

    // Modal 打开且表单回填（保单号、保险公司）
    await waitFor(() => {
      expect(screen.getByText('编辑保险记录')).toBeInTheDocument();
      expect(screen.getByDisplayValue('P2026001')).toBeInTheDocument();
      expect(screen.getByDisplayValue('人保财险')).toBeInTheDocument();
    });

    // 点确定 → PUT（日期已回填，校验通过）
    const okBtn = document.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLElement;
    fireEvent.click(okBtn);

    await waitFor(() => expect(mockApi.put).toHaveBeenCalled());
    const [url, payload] = mockApi.put.mock.calls[0];
    expect(url).toContain('/insurance/1');
    expect(payload.insurance_type).toBe('compulsory');
    expect(payload.company).toBe('人保财险');
    expect(payload.policy_no).toBe('P2026001');
  });

  it('6. 点击「删除」Popconfirm 确认后调用 DELETE', async () => {
    renderWithRouter(<FleetVehicleInsurancePage />);

    await waitFor(() => expect(screen.getAllByText('删除').length).toBeGreaterThan(0), { timeout: 3000 });
    fireEvent.click(screen.getAllByText('删除')[0]);

    await waitFor(() => {
      expect(document.querySelector('.ant-popconfirm-buttons')).toBeInTheDocument();
    });
    const okBtn = document.querySelector('.ant-popconfirm-buttons .ant-btn-primary') as HTMLElement;
    fireEvent.click(okBtn);

    await waitFor(() => expect(mockApi.delete).toHaveBeenCalled());
    expect(mockApi.delete.mock.calls[0][0]).toContain('/insurance/1');
  });

  it('7. 保险接口报错时降级为空态（不崩溃，统计保留）', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/vehicles') && url.includes('/insurance')) return Promise.reject(new Error('boom'));
      return defaultGet(url);
    });

    renderWithRouter(<FleetVehicleInsurancePage />);

    await waitFor(() => {
      expect(screen.getByText('保单总数')).toBeInTheDocument();
    }, { timeout: 3000 });
    expect(screen.queryByText('人保财险')).not.toBeInTheDocument();
    expect(screen.queryByText('平安产险')).not.toBeInTheDocument();
  });
});
