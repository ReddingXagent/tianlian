import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { RefreshControl } from 'react-native';
import DashboardScreen from '../DashboardScreen';
import { useAuthStore } from '../../store/authStore';
import { useStationStore } from '../../store/stationStore';
import { useWorkOrderStore } from '../../store/workOrderStore';
import { dashboardApi } from '../../services/api';
import { Station } from '../../types';

const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
}));

jest.mock('../../store/authStore', () => ({ useAuthStore: jest.fn() }));
jest.mock('../../store/stationStore', () => ({ useStationStore: jest.fn() }));
jest.mock('../../store/workOrderStore', () => ({ useWorkOrderStore: jest.fn() }));
jest.mock('../../services/api', () => ({
  dashboardApi: { getStats: jest.fn() },
}));

const makeStation = (over: Partial<Station> = {}): Station => ({
  id: 1,
  name: '充电站A',
  code: 'ST-001',
  address: '北京市朝阳区',
  status: 'online',
  latitude: 39.9,
  longitude: 116.4,
  deviceCount: 8,
  onlineDeviceCount: 6,
  alarmCount: 0,
  createdAt: '',
  updatedAt: '',
  ...over,
});

const setup = (over: {
  user?: { nickname?: string; username?: string } | null;
  stations?: Station[];
  stats?: unknown;
  statsError?: boolean;
} = {}) => {
  (useAuthStore as unknown as jest.Mock).mockReturnValue({
    user: over.user === undefined ? { nickname: '站长甲', username: 'zz1' } : over.user,
  });
  const fetchStations = jest.fn().mockResolvedValue(undefined);
  (useStationStore as unknown as jest.Mock).mockReturnValue({
    stations: over.stations ?? [
      makeStation(),
      makeStation({ id: 2, name: '充电站B', address: '上海市徐汇区', status: 'offline' }),
    ],
    fetchStations,
  });
  const fetchOrders = jest.fn().mockResolvedValue(undefined);
  (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({ fetchOrders });
  const getStats = (dashboardApi.getStats as unknown as jest.Mock).mockReset();
  if (over.statsError) {
    getStats.mockRejectedValue(new Error('stats not ready'));
  } else {
    getStats.mockResolvedValue({
      data: over.stats ?? {
        totalStations: 9,
        onlineStations: 7,
        offlineStations: 2,
        totalAlarms: 5,
        unhandledAlarms: 3,
        revenueSummary: { today: 12.5, week: 88.8, month: 1200 },
      },
    });
  }
  return { fetchStations, fetchOrders };
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('DashboardScreen', () => {
  it('挂载即拉取站点/工单/统计', async () => {
    const { fetchStations, fetchOrders } = setup();
    render(<DashboardScreen />);
    await waitFor(() => {
      expect(fetchStations).toHaveBeenCalledWith({ page: 1, pageSize: 100 });
      expect(fetchOrders).toHaveBeenCalledWith({ page: 1, pageSize: 5 });
      expect(dashboardApi.getStats).toHaveBeenCalledTimes(1);
    });
  });

  it('渲染欢迎语与统计卡片(API值优先)', async () => {
    setup();
    const { getByText } = render(<DashboardScreen />);
    await waitFor(() => expect(getByText('你好，站长甲')).toBeTruthy());
    expect(getByText('9')).toBeTruthy(); // totalStations
    expect(getByText('7')).toBeTruthy(); // onlineStations
    expect(getByText('3')).toBeTruthy(); // unhandledAlarms
  });

  it('渲染营收概览(两位小数)', async () => {
    setup();
    const { getByText } = render(<DashboardScreen />);
    await waitFor(() => expect(getByText('营收概览')).toBeTruthy());
    expect(getByText('¥12.50')).toBeTruthy();
    expect(getByText('¥88.80')).toBeTruthy();
    expect(getByText('¥1200.00')).toBeTruthy();
  });

  it('统计API失败时回退本地站点口径且不崩溃', async () => {
    setup({ statsError: true, stations: [makeStation(), makeStation({ id: 2, status: 'offline' })] });
    const { getByText, queryByText } = render(<DashboardScreen />);
    await waitFor(() => expect(getByText('2')).toBeTruthy()); // 本地stations.length
    expect(getByText('1')).toBeTruthy(); // 本地online计数
    expect(getByText('-')).toBeTruthy(); // unhandledAlarms兜底
    expect(queryByText('营收概览')).toBeNull(); // 无revenueSummary
  });

  it('user缺失时问候兜底为站长', async () => {
    setup({ user: null });
    const { getByText } = render(<DashboardScreen />);
    await waitFor(() => expect(getByText('你好，站长')).toBeTruthy());
  });

  it('快捷操作导航到对应页面', async () => {
    setup();
    const { getByText } = render(<DashboardScreen />);
    await waitFor(() => expect(getByText('快捷操作')).toBeTruthy());
    fireEvent.press(getByText('站点管理'));
    expect(mockNavigate).toHaveBeenCalledWith('Stations');
    fireEvent.press(getByText('告警查看'));
    expect(mockNavigate).toHaveBeenCalledWith('AlarmList');
    fireEvent.press(getByText('工单管理'));
    expect(mockNavigate).toHaveBeenCalledWith('WorkOrder');
    fireEvent.press(getByText('营收统计'));
    expect(mockNavigate).toHaveBeenCalledWith('Revenue');
  });

  it('站点预览: 点击进入详情并查看全部导航', async () => {
    setup();
    const { getByText } = render(<DashboardScreen />);
    await waitFor(() => expect(getByText('充电站A')).toBeTruthy());
    fireEvent.press(getByText('充电站B'));
    expect(mockNavigate).toHaveBeenCalledWith('StationDetail', { stationId: 2 });
    fireEvent.press(getByText('查看全部 →'));
    expect(mockNavigate).toHaveBeenCalledWith('Stations');
  });

  it('无站点时显示空态文案', async () => {
    setup({ stations: [] });
    const { getByText } = render(<DashboardScreen />);
    await waitFor(() => expect(getByText('暂无站点数据')).toBeTruthy());
  });

  it('下拉刷新重新拉取数据', async () => {
    const { fetchStations } = setup();
    const { UNSAFE_getByType } = render(<DashboardScreen />);
    await waitFor(() => expect(fetchStations).toHaveBeenCalledTimes(1));
    const rc = UNSAFE_getByType(RefreshControl);
    fireEvent(rc, 'refresh');
    await waitFor(() => expect(fetchStations).toHaveBeenCalledTimes(2));
  });
});
