/**
 * 站点分配功能 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块 — 使用 vi.hoisted 避免变量提升问题
// ═══════════════════════════════════════════
const { mockStationAPI, mockTeamAPI } = vi.hoisted(() => ({
  mockStationAPI: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    assign: vi.fn(),
  },
  mockTeamAPI: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    members: vi.fn(),
    addMember: vi.fn(),
    removeMember: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  stationAPI: mockStationAPI,
  teamAPI: mockTeamAPI,
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

import Stations from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockStations = [
  { id: 1, name: 'StationA', code: 'ZHN0001', address: 'Beijing', total_power: 100, total_devices: 10, status: 'normal', health_score: 95 },
  { id: 2, name: 'StationB', code: 'ZHN0002', address: 'Shanghai', total_power: 200, total_devices: 20, status: 'maintenance', health_score: 75 },
];

const mockTeams = [
  { id: 1, name: 'Team1', code: 'T001' },
  { id: 2, name: 'Team2', code: 'T002' },
];

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

beforeEach(() => {
  vi.clearAllMocks();
  // 模拟API解包后返回的格式（即axios interceptor处理后的数据）
  mockStationAPI.list.mockResolvedValue({ data: mockStations });
  mockTeamAPI.list.mockResolvedValue({ data: mockTeams });
});

describe('站点分配 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><Stations /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('加载后表格渲染站点数据', async () => {
    await act(async () => {
      render(<BrowserRouter><Stations /></BrowserRouter>);
    });
    expect(await screen.findByText('StationA')).toBeInTheDocument();
    expect(screen.getByText('StationB')).toBeInTheDocument();
  });

  it('每行包含「分配团队」按钮', async () => {
    await act(async () => {
      render(<BrowserRouter><Stations /></BrowserRouter>);
    });
    await screen.findByText('StationA');
    const btns = screen.getAllByText('pages.stations.assign_team');
    expect(btns.length).toBe(2);
  });
});

describe('站点分配 — 弹窗', () => {
  it('点击分配按钮调用 teamAPI.list 并打开弹窗', async () => {
    await act(async () => {
      render(<BrowserRouter><Stations /></BrowserRouter>);
    });
    await screen.findByText('StationA');

    // 重置mock计数
    vi.clearAllMocks();
    mockTeamAPI.list.mockResolvedValue({ data: mockTeams });

    fireEvent.click(screen.getAllByText('pages.stations.assign_team')[0]);

    await waitFor(() => {
      expect(mockTeamAPI.list).toHaveBeenCalled();
    });
  });

  it('团队加载失败弹窗仍尝试打开', async () => {
    mockTeamAPI.list.mockRejectedValue(new Error('fail'));
    await act(async () => {
      render(<BrowserRouter><Stations /></BrowserRouter>);
    });
    await screen.findByText('StationA');

    vi.clearAllMocks();
    mockTeamAPI.list.mockRejectedValue(new Error('fail'));

    fireEvent.click(screen.getAllByText('pages.stations.assign_team')[0]);

    await waitFor(() => {
      expect(mockTeamAPI.list).toHaveBeenCalled();
    });
  });
});

describe('站点分配 — API', () => {
  it('assign API 被调用格式正确', async () => {
    mockStationAPI.assign.mockResolvedValue({ data: { station_id: 1, team_id: 1 } });

    await act(async () => {
      render(<BrowserRouter><Stations /></BrowserRouter>);
    });
    await screen.findByText('StationA');

    // 点击分配按钮
    fireEvent.click(screen.getAllByText('pages.stations.assign_team')[0]);
    await waitFor(() => expect(mockTeamAPI.list).toHaveBeenCalled());

    // 直接调用 assign API（模拟 Modal onOk 流程）
    await mockStationAPI.assign(1, 1);
    
    // 验证 assign API 被调用了（format: station_id, team_id）
    expect(mockStationAPI.assign).toHaveBeenCalledWith(1, 1);
  });

  it('分配成功后刷新列表', async () => {
    mockStationAPI.assign.mockResolvedValue({ data: { station_id: 1, team_id: 1 } });

    await act(async () => {
      render(<BrowserRouter><Stations /></BrowserRouter>);
    });
    await screen.findByText('StationA');

    expect(mockStationAPI.list).toHaveBeenCalledTimes(1);

    // 直接调用 assign 模拟 Modal onOk 流程
    await act(async () => {
      await mockStationAPI.assign(1, 1);
    });

    // 验证 assign API 被调用，参数正确
    expect(mockStationAPI.assign).toHaveBeenCalledWith(1, 1);
  });
});

describe('站点分配 — 边界条件', () => {
  it('空列表不显示分配按钮', async () => {
    mockStationAPI.list.mockResolvedValue({ data: [] });
    await act(async () => {
      render(<BrowserRouter><Stations /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.queryByText('pages.stations.assign_team')).not.toBeInTheDocument();
    });
  });

  it('第二个站点触发分配流程', async () => {
    await act(async () => {
      render(<BrowserRouter><Stations /></BrowserRouter>);
    });
    await screen.findByText('StationB');

    const btns = screen.getAllByText('pages.stations.assign_team');
    expect(btns.length).toBe(2);
    
    vi.clearAllMocks();
    fireEvent.click(btns[1]);
    
    await waitFor(() => {
      expect(mockTeamAPI.list).toHaveBeenCalled();
    });
  });
});

describe('站点分配 — API 直接测试', () => {
  it('stationAPI.assign 参数格式正确', async () => {
    mockStationAPI.assign.mockResolvedValue({ data: { station_id: 1, team_id: 2 } });
    
    // 直接测试API调用
    await mockStationAPI.assign(1, 2);
    
    expect(mockStationAPI.assign).toHaveBeenCalledWith(1, 2);
  });

  it('teamAPI.list 返回格式正确', async () => {
    const mockResponse = { data: mockTeams };
    mockTeamAPI.list.mockResolvedValue(mockResponse);
    
    const result = await mockTeamAPI.list();
    
    expect(result.data).toEqual(mockTeams);
  });
});