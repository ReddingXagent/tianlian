import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { RefreshControl } from 'react-native';
import DashboardScreen from '../DashboardScreen';
import { Station } from '../../types';

const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
}));

jest.mock('../../store/authStore', () => ({ useAuthStore: jest.fn() }));

// Mock the hook
const mockUseDashboard = {
  stats: null as null | {
    totalStations: number;
    onlineStations: number;
    offlineStations: number;
    totalAlarms: number;
    unhandledAlarms: number;
    revenueSummary: { today: number; week: number; month: number };
  },
  refreshing: false,
  loading: true,
  refresh: jest.fn(),
  stations: [] as Station[],
};

jest.mock('../../hooks/useDashboard', () => ({
  useDashboard: () => mockUseDashboard,
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

const MOCK_STATS = {
  totalStations: 9,
  onlineStations: 7,
  offlineStations: 2,
  totalAlarms: 5,
  unhandledAlarms: 3,
  revenueSummary: { today: 12.5, week: 88.8, month: 1200 },
};

const { useAuthStore } = require('../../store/authStore');

beforeEach(() => {
  jest.clearAllMocks();
  mockUseDashboard.stats = null;
  mockUseDashboard.refreshing = false;
  mockUseDashboard.loading = true;
  mockUseDashboard.refresh = jest.fn();
  mockUseDashboard.stations = [];
});

describe('DashboardScreen', () => {
  it('挂载即渲染(数据加载中)', () => {
    useAuthStore.mockReturnValue({ user: { nickname: '站长甲', username: 'zz1' } });
    mockUseDashboard.loading = true;
    const { UNSAFE_getByType } = render(<DashboardScreen />);
    // Loading state shows ActivityIndicator
    expect(UNSAFE_getByType(require('react-native').ActivityIndicator)).toBeTruthy();
  });

  it('渲染欢迎语与统计卡片(API值优先)', async () => {
    useAuthStore.mockReturnValue({ user: { nickname: '站长甲', username: 'zz1' } });
    mockUseDashboard.loading = false;
    mockUseDashboard.stats = MOCK_STATS;
    mockUseDashboard.stations = [makeStation(), makeStation({ id: 2, name: '充电站B', status: 'offline' })];
    const { getByText } = render(<DashboardScreen />);
    expect(getByText('你好，站长甲')).toBeTruthy();
    expect(getByText('9')).toBeTruthy(); // totalStations from stats
    expect(getByText('7')).toBeTruthy(); // onlineStations from stats
    expect(getByText('3')).toBeTruthy(); // unhandledAlarms from stats
  });

  it('渲染营收概览(两位小数)', async () => {
    useAuthStore.mockReturnValue({ user: { nickname: '站长甲', username: 'zz1' } });
    mockUseDashboard.loading = false;
    mockUseDashboard.stats = MOCK_STATS;
    mockUseDashboard.stations = [makeStation()];
    const { getByText } = render(<DashboardScreen />);
    expect(getByText('营收概览')).toBeTruthy();
    expect(getByText('¥12.50')).toBeTruthy();
    expect(getByText('¥88.80')).toBeTruthy();
    expect(getByText('¥1200.00')).toBeTruthy();
  });

  it('统计API失败时回退本地站点口径且不崩溃', async () => {
    useAuthStore.mockReturnValue({ user: { nickname: '站长甲', username: 'zz1' } });
    mockUseDashboard.loading = false;
    mockUseDashboard.stats = null; // stats API failed
    mockUseDashboard.stations = [makeStation(), makeStation({ id: 2, status: 'offline' })];
    const { getByText, queryByText } = render(<DashboardScreen />);
    expect(getByText('2')).toBeTruthy(); // 本地stations.length
    expect(getByText('1')).toBeTruthy(); // 本地online计数
    expect(getByText('-')).toBeTruthy(); // unhandledAlarms兜底
    expect(queryByText('营收概览')).toBeNull();
  });

  it('user缺失时问候兜底为站长', async () => {
    useAuthStore.mockReturnValue({ user: null });
    mockUseDashboard.loading = false;
    mockUseDashboard.stations = [makeStation()];
    const { getByText } = render(<DashboardScreen />);
    expect(getByText('你好，站长')).toBeTruthy();
  });

  it('快捷操作导航到对应页面', async () => {
    useAuthStore.mockReturnValue({ user: { nickname: '站长甲', username: 'zz1' } });
    mockUseDashboard.loading = false;
    mockUseDashboard.stations = [makeStation()];
    const { getByText } = render(<DashboardScreen />);
    expect(getByText('快捷操作')).toBeTruthy();
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
    useAuthStore.mockReturnValue({ user: { nickname: '站长甲', username: 'zz1' } });
    mockUseDashboard.loading = false;
    mockUseDashboard.stations = [makeStation(), makeStation({ id: 2, name: '充电站B', address: '上海市徐汇区', status: 'offline' })];
    const { getByText } = render(<DashboardScreen />);
    expect(getByText('充电站A')).toBeTruthy();
    fireEvent.press(getByText('充电站B'));
    expect(mockNavigate).toHaveBeenCalledWith('StationDetail', { stationId: 2 });
    fireEvent.press(getByText('查看全部 →'));
    expect(mockNavigate).toHaveBeenCalledWith('Stations');
  });

  it('无站点时显示空态文案', async () => {
    useAuthStore.mockReturnValue({ user: { nickname: '站长甲', username: 'zz1' } });
    mockUseDashboard.loading = false;
    mockUseDashboard.stations = [];
    const { getByText } = render(<DashboardScreen />);
    expect(getByText('暂无站点数据')).toBeTruthy();
  });

  it('下拉刷新调用hook refresh', async () => {
    useAuthStore.mockReturnValue({ user: { nickname: '站长甲', username: 'zz1' } });
    mockUseDashboard.loading = false;
    mockUseDashboard.stations = [makeStation()];
    mockUseDashboard.refreshing = false;
    const { UNSAFE_getByType } = render(<DashboardScreen />);
    const rc = UNSAFE_getByType(RefreshControl);
    fireEvent(rc, 'refresh');
    expect(mockUseDashboard.refresh).toHaveBeenCalledTimes(1);
  });
});
