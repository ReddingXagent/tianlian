import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { TextInput, RefreshControl, ActivityIndicator } from 'react-native';
import StationListScreen from '../StationListScreen';
import { Station } from '../../types';

const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
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

const mockUseStationList = {
  stations: [] as Station[],
  loading: false,
  refreshing: false,
  search: '',
  setSearch: jest.fn(),
  filteredStations: [] as Station[],
  refresh: jest.fn(),
};

jest.mock('../../hooks/useStationList', () => ({
  useStationList: () => mockUseStationList,
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockUseStationList.stations = [];
  mockUseStationList.filteredStations = [];
  mockUseStationList.loading = false;
  mockUseStationList.refreshing = false;
  mockUseStationList.search = '';
  mockUseStationList.setSearch = jest.fn();
  mockUseStationList.refresh = jest.fn();
});

describe('StationListScreen', () => {
  it('渲染站点卡片: 名称/地址/设备数 + 三态状态徽章', async () => {
    const stations = [
      makeStation(),
      makeStation({ id: 2, name: '充电站B', address: '上海市徐汇区', status: 'maintenance', alarmCount: 3, deviceCount: 4, onlineDeviceCount: 1 }),
      makeStation({ id: 3, name: '充电站C', address: '广州市天河区', status: 'offline', deviceCount: 2, onlineDeviceCount: 0 }),
    ];
    mockUseStationList.stations = stations;
    mockUseStationList.filteredStations = stations;
    const { getByText, getByTestId } = render(<StationListScreen />);
    getByText('充电站A');
    getByText('充电站B');
    getByText('充电站C');
    getByText('北京市朝阳区');
    getByText('设备 8 | 在线 6');
    getByText('在线');
    getByText('维护中');
    getByText('离线');
    // testID守卫: 卡片testID必须是prop而非children(F3688回归)
    expect(getByTestId('station-card-1')).toBeTruthy();
    expect(getByTestId('station-card-2')).toBeTruthy();
  });

  it('告警徽章仅在 alarmCount>0 时出现', async () => {
    const stations = [
      makeStation(),
      makeStation({ id: 2, name: '充电站B', alarmCount: 3 }),
    ];
    mockUseStationList.stations = stations;
    mockUseStationList.filteredStations = stations;
    const { getByText, queryByText } = render(<StationListScreen />);
    getByText('告警 3');
    expect(queryByText('告警 0')).toBeNull();
  });

  it('点击卡片跳转站点详情(携带 stationId)', async () => {
    const stations = [makeStation(), makeStation({ id: 2, name: '充电站B' })];
    mockUseStationList.stations = stations;
    mockUseStationList.filteredStations = stations;
    const { getByText } = render(<StationListScreen />);
    fireEvent.press(getByText('充电站B'));
    expect(mockNavigate).toHaveBeenCalledWith('StationDetail', { stationId: 2 });
  });

  it('搜索输入调用setSearch', async () => {
    mockUseStationList.filteredStations = [makeStation()];
    const { UNSAFE_getByType } = render(<StationListScreen />);
    const input = UNSAFE_getByType(TextInput);
    fireEvent.changeText(input, '充电站B');
    expect(mockUseStationList.setSearch).toHaveBeenCalledWith('充电站B');
  });

  it('搜索提交调用refresh', async () => {
    mockUseStationList.filteredStations = [makeStation()];
    const { UNSAFE_getByType } = render(<StationListScreen />);
    const input = UNSAFE_getByType(TextInput);
    fireEvent(input, 'onSubmitEditing');
    expect(mockUseStationList.refresh).toHaveBeenCalledTimes(1);
  });

  it('下拉刷新调用hook refresh', async () => {
    mockUseStationList.filteredStations = [makeStation()];
    const { UNSAFE_getByType } = render(<StationListScreen />);
    const rc = UNSAFE_getByType(RefreshControl);
    fireEvent(rc, 'refresh');
    expect(mockUseStationList.refresh).toHaveBeenCalledTimes(1);
  });

  it('loading 且非刷新中时显示加载指示器', async () => {
    mockUseStationList.loading = true;
    mockUseStationList.refreshing = false;
    mockUseStationList.filteredStations = [];
    const { UNSAFE_getByType, queryByText } = render(<StationListScreen />);
    expect(UNSAFE_getByType(ActivityIndicator)).toBeTruthy();
    expect(queryByText('暂无站点数据')).toBeNull();
  });

  it('空列表显示空态文案', async () => {
    mockUseStationList.filteredStations = [];
    const { getByText } = render(<StationListScreen />);
    getByText('暂无站点数据');
  });
});
