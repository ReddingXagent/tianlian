/**
 * 车队 - 设置页面 Vitest 组件测试
 *
 * 覆盖：页面渲染、企业信息Tab回填、车辆默认配置Tab、保存企业信息(PUT /enterprises/{id})、保存车辆配置(localStorage)
 *
 * 字段契约对齐后端 app/api/v1/enterprises.py：
 *   - 联系人/电话字段为 contact / phone（非 contact_person / contact_phone）
 *   - address / description 及车辆默认配置后端模型不支持，走 localStorage 本地持久化
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
// 测试数据（字段对齐后端 _enterprise_to_dict + 统一响应包装）
// ═══════════════════════════════════════════
const mockEnterpriseList = {
  code: 200,
  message: 'success',
  data: {
    items: [
      { id: 1, name: '顺达物流有限公司', code: 'TL-FLEET-001', contact: '张伟', phone: '13800138001', status: 'active' },
      { id: 2, name: '鹏程货运公司', code: 'TL-FLEET-002', contact: '李强', phone: '13900139002', status: 'active' },
    ],
    total: 2,
    page: 1,
    page_size: 20,
  },
};

const mockEnterpriseDetail = {
  code: 200,
  message: 'success',
  data: {
    id: 1,
    name: '顺达物流有限公司',
    code: 'TL-FLEET-001',
    contact: '张伟',
    phone: '13800138001',
    balance: 0.0,
    credit_limit: 0.0,
    status: 'active',
    owner_team_id: null,
  },
};

const mockTeams = {
  code: 200,
  data: { items: [{ id: 1, name: '运维一部' }, { id: 2, name: '运维二部' }] },
};

const mockStations = {
  code: 200,
  data: [
    { id: 10, name: '北京朝阳站', code: 'STA010', address: '北京市朝阳区', status: 'normal', team_id: 1 },
    { id: 20, name: '上海浦东站', code: 'STA020', address: '上海市浦东新区', status: 'normal', team_id: 1 },
  ],
};

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mockApi.get.mockImplementation((url: string) => {
    if (url === '/enterprises') return Promise.resolve({ data: mockEnterpriseList });
    if (url.startsWith('/enterprises/') && url.endsWith('/stations'))
      return Promise.resolve({ data: { code: 200, data: mockStations.data } });
    if (url.startsWith('/enterprises/') && url.endsWith('/available-stations'))
      return Promise.resolve({ data: { code: 200, data: mockStations.data } });
    if (url.startsWith('/enterprises/')) return Promise.resolve({ data: mockEnterpriseDetail });
    if (url === '/teams') return Promise.resolve({ data: mockTeams });
    return Promise.resolve({ data: { code: 200, data: { items: [] } } });
  });
  mockApi.put.mockResolvedValue({ data: { code: 200, message: 'success' } });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
});

import FleetSettingsPage from '../Settings';

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
describe('FleetSettingsPage', () => {
  it('1. 渲染设置页面与企业选择器，默认加载首个企业', async () => {
    renderWithRouter(<FleetSettingsPage />);

    await waitFor(() => {
      expect(screen.getByText('车队设置')).toBeInTheDocument();
    });

    // 拉取企业列表
    expect(mockApi.get).toHaveBeenCalledWith('/enterprises');

    // 默认选中第一个企业并加载详情
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/enterprises/1');
    });
  });

  it('2. 企业信息Tab回填企业字段（contact/phone 对齐后端）', async () => {
    renderWithRouter(<FleetSettingsPage />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('顺达物流有限公司')).toBeInTheDocument();
    });
    // 联系人 contact
    expect(screen.getByDisplayValue('张伟')).toBeInTheDocument();
    // 联系电话 phone
    expect(screen.getByDisplayValue('13800138001')).toBeInTheDocument();
  });

  it('3. 车辆默认配置Tab展示配置项', async () => {
    renderWithRouter(<FleetSettingsPage />);

    await waitFor(() => expect(screen.getByDisplayValue('顺达物流有限公司')).toBeInTheDocument());

    fireEvent.click(screen.getByText('车辆默认配置'));

    await waitFor(() => {
      expect(screen.getByText('默认年检周期(月)')).toBeInTheDocument();
      expect(screen.getByText('保险提醒天数')).toBeInTheDocument();
      expect(screen.getByText('里程保养间隔(km)')).toBeInTheDocument();
    });
  });

  it('4. 保存企业信息调用 PUT /enterprises/{id}，载荷使用后端字段', async () => {
    renderWithRouter(<FleetSettingsPage />);

    await waitFor(() => expect(screen.getByDisplayValue('顺达物流有限公司')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /保存企业信息/ }));

    await waitFor(() => expect(mockApi.put).toHaveBeenCalled());
    const [url, payload] = mockApi.put.mock.calls[0];
    expect(url).toBe('/enterprises/1');
    expect(payload).toEqual(expect.objectContaining({
      name: '顺达物流有限公司',
      code: 'TL-FLEET-001',
      contact: '张伟',
      phone: '13800138001',
      status: 'active',
    }));
  });

  it('5. 保存车辆配置写入 localStorage（本地持久化，不调后端）', async () => {
    renderWithRouter(<FleetSettingsPage />);

    await waitFor(() => expect(screen.getByDisplayValue('顺达物流有限公司')).toBeInTheDocument());

    fireEvent.click(screen.getByText('车辆默认配置'));

    await waitFor(() => expect(screen.getByText('默认年检周期(月)')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /保存车辆配置/ }));

    await waitFor(() => {
      const raw = localStorage.getItem('fleet:settings:vehicle:1');
      expect(raw).toBeTruthy();
      const parsed = JSON.parse(raw!);
      expect(parsed.inspection_period_months).toBe(12);
      expect(parsed.insurance_reminder_days).toBe(30);
      expect(parsed.maintenance_interval_km).toBe(10000);
    });

    // 车辆配置为本地存储，不应触发后端写入
    expect(mockApi.put).not.toHaveBeenCalled();
  });

  it('6. 场站绑定Tab只读展示已绑定场站（卡691532f2：写入口迁至运维侧）', async () => {
    renderWithRouter(<FleetSettingsPage />);

    await waitFor(() => expect(screen.getByDisplayValue('顺达物流有限公司')).toBeInTheDocument());

    fireEvent.click(screen.getByText('场站绑定'));

    await waitFor(() => {
      expect(screen.getByText('绑定由运营商在运维侧（车队管理）操作，此处仅展示当前绑定结果。')).toBeInTheDocument();
      expect(screen.getByText('北京朝阳站')).toBeInTheDocument();
      expect(screen.getByText('上海浦东站')).toBeInTheDocument();
    });
  });

  it('7. 场站绑定Tab无写入口：不调 available-stations，也不发 PUT /stations', async () => {
    renderWithRouter(<FleetSettingsPage />);

    await waitFor(() => expect(screen.getByDisplayValue('顺达物流有限公司')).toBeInTheDocument());

    fireEvent.click(screen.getByText('场站绑定'));

    await waitFor(() => expect(screen.getByText('北京朝阳站')).toBeInTheDocument());

    expect(mockApi.get).not.toHaveBeenCalledWith('/enterprises/1/available-stations');
    const putCalls = mockApi.put.mock.calls.filter(
      ([url]: string[]) => String(url).includes('/stations')
    );
    expect(putCalls).toHaveLength(0);
    expect(screen.queryByText('保存场站绑定')).not.toBeInTheDocument();
  });
});
