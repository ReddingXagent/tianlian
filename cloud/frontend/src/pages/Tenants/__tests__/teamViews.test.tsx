/**
 * 卡9a81fffd：TeamDataView / TeamAccountsView 去硬编码假数据 — 接真实 API 测试
 * 卡2285f54a：场站/设备/工单 Tab 接列表 API + team_id 查询参数
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import React from 'react';

const { mockTeamAPI, mockTenantAPI, mockStationAPI, mockDeviceAPI, mockWorkorderAPI } = vi.hoisted(() => ({
  mockTeamAPI: { members: vi.fn() },
  mockTenantAPI: { list: vi.fn(), stats: vi.fn() },
  mockStationAPI: { list: vi.fn() },
  mockDeviceAPI: { list: vi.fn() },
  mockWorkorderAPI: { list: vi.fn() },
}));

vi.mock('../../../api', () => ({
  teamAPI: mockTeamAPI,
  tenantAPI: mockTenantAPI,
  stationAPI: mockStationAPI,
  deviceAPI: mockDeviceAPI,
  workorderAPI: mockWorkorderAPI,
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
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), loading: vi.fn() },
  };
});

import TeamDataView from '../components/TeamDataView';
import TeamAccountsView from '../components/TeamAccountsView';

const mockTenant = {
  id: 1, name: 'TeamAlpha', code: 'TA001', contact: '张三', phone: '13800001111',
  email: 'a@test.com', status: 'active', station_count: 5, device_count: 50,
  member_count: 10, workorder_count: 3, alarm_count: 1, expired_at: '2027-01-01',
  created_at: '2025-01-01',
};

const mockMembers = {
  data: {
    items: [
      { id: 11, username: 'real_admin', real_name: '张三', role: 'admin', status: 'active', phone: '13811112222', join_date: '2025-01-01T00:00:00' },
      { id: 12, username: 'real_eng', real_name: '李四', role: 'engineer', status: 'active', phone: '13833334444', join_date: '2025-02-01T00:00:00' },
    ],
    total: 2,
  },
};

const mockStations = { data: { items: [{ id: 101, name: '真实站A', address: '真实路1号', status: 'normal', total_devices: 3, total_power: 120.5, gun_count: 8 }], total: 1 } };
const mockDevices = { data: { items: [{ id: 201, name: '真实设备1', sn: 'SN-REAL-1', type: 'charger_dc', status: 'online', power: 60.2, health_score: 95 }], total: 1 } };
const mockWorkOrders = { data: { items: [{ id: 'WO-REAL-1', fault_desc: '真实故障', type: 'repair', level: 'critical', status: 'pending', station_id: 101, create_time: '2026-08-25T10:00:00' }], total: 1 } };

describe('卡9a81fffd — TeamDataView 去 mock 接真实 API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockTeamAPI.members.mockResolvedValue(mockMembers);
    mockStationAPI.list.mockResolvedValue(mockStations);
    mockDeviceAPI.list.mockResolvedValue(mockDevices);
    mockWorkorderAPI.list.mockResolvedValue(mockWorkOrders);
  });

  it('选中团队后调用 teamAPI.members 拉取真实成员', async () => {
    render(<TeamDataView tenants={[mockTenant]} loading={false} onRefresh={() => {}} />);
    await waitFor(() => {
      expect(mockTeamAPI.members).toHaveBeenCalledWith(1);
    });
  });

  it('账户 Tab 渲染 API 真实用户，不再出现 admin_/eng_ 假账号', async () => {
    render(<TeamDataView tenants={[mockTenant]} loading={false} onRefresh={() => {}} />);
    expect(await screen.findByText('real_admin')).toBeInTheDocument();
    expect(screen.getByText('real_eng')).toBeInTheDocument();
    // 旧硬编码假账号格式不应出现
    expect(screen.queryByText('admin_ta001')).not.toBeInTheDocument();
    expect(screen.queryByText('eng_ta001')).not.toBeInTheDocument();
    expect(screen.queryByText('tech_ta001')).not.toBeInTheDocument();
  });

  it('场站/设备/工单无对应 team 维度 API，不再渲染 MOCK 假数据', async () => {
    render(<TeamDataView tenants={[mockTenant]} loading={false} onRefresh={() => {}} />);
    await screen.findByText('real_admin');
    // 旧 mock 数据（mockData.ts 切片）不应出现
    expect(screen.queryByText('郑州东区光储充站')).not.toBeInTheDocument();
    expect(screen.queryByText('WO-20260601')).not.toBeInTheDocument();
    expect(screen.queryByText('光伏逆变器-01')).not.toBeInTheDocument();
  });

  it('卡2285f54a：选中团队后三个列表 API 均携带 team_id 查询参数', async () => {
    render(<TeamDataView tenants={[mockTenant]} loading={false} onRefresh={() => {}} />);
    await waitFor(() => {
      expect(mockStationAPI.list).toHaveBeenCalledWith({ team_id: 1, page: 1, page_size: 100 });
      expect(mockDeviceAPI.list).toHaveBeenCalledWith({ team_id: 1, page: 1, page_size: 100 });
      expect(mockWorkorderAPI.list).toHaveBeenCalledWith({ team_id: 1, page: 1, page_size: 100 });
    });
  });

  it('卡2285f54a：场站 Tab 渲染真实 API 数据（真实站A）', async () => {
    render(<TeamDataView tenants={[mockTenant]} loading={false} onRefresh={() => {}} />);
    // antd Tabs 懒挂载：先激活场站子 Tab（i18n mock 下 label 为 i18n key）
    fireEvent.click(screen.getByRole('tab', { name: /pages\.tenants\.stations/ }));
    expect(await screen.findByText('真实站A')).toBeInTheDocument();
    expect(screen.getByText('真实路1号')).toBeInTheDocument();
  });

  it('卡2285f54a：设备/工单 Tab 渲染真实 API 数据', async () => {
    render(<TeamDataView tenants={[mockTenant]} loading={false} onRefresh={() => {}} />);
    fireEvent.click(screen.getByRole('tab', { name: /pages\.tenants\.devices/ }));
    expect(await screen.findByText('真实设备1')).toBeInTheDocument();
    expect(screen.getByText('SN-REAL-1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /pages\.tenants\.workorders/ }));
    expect(await screen.findByText('WO-REAL-1')).toBeInTheDocument();
    expect(screen.getByText('真实故障')).toBeInTheDocument();
  });

  it('卡2285f54a：单路 API 失败不影响其他 Tab（设备置空，场站仍渲染）', async () => {
    mockDeviceAPI.list.mockRejectedValue(new Error('403'));
    render(<TeamDataView tenants={[mockTenant]} loading={false} onRefresh={() => {}} />);
    fireEvent.click(screen.getByRole('tab', { name: /pages\.tenants\.stations/ }));
    expect(await screen.findByText('真实站A')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /pages\.tenants\.devices/ }));
    await waitFor(() => {
      expect(screen.getByText('pages.tenants.members_empty')).toBeInTheDocument();
    });
    expect(screen.queryByText('真实设备1')).not.toBeInTheDocument();
  });
});

describe('卡9a81fffd — TeamAccountsView 去 mock 接真实 API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockTeamAPI.members.mockResolvedValue(mockMembers);
  });

  it('按租户逐个拉取成员并渲染真实账户，不再出现 admin_ 假账号', async () => {
    render(<TeamAccountsView tenants={[mockTenant]} loading={false} onRefresh={() => {}} />);
    await waitFor(() => {
      expect(mockTeamAPI.members).toHaveBeenCalledWith(1);
    });
    expect(await screen.findByText('real_admin')).toBeInTheDocument();
    expect(screen.getByText('real_eng')).toBeInTheDocument();
    expect(screen.queryByText('admin_ta001')).not.toBeInTheDocument();
    expect(screen.queryByText('eng_ta001')).not.toBeInTheDocument();
  });
});
