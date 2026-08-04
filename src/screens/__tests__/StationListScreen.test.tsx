import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { TextInput, RefreshControl, ActivityIndicator } from 'react-native';
import StationListScreen from '../StationListScreen';
import { useStationStore } from '../../store/stationStore';
import { Station } from '../../types';

const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
}));

jest.mock('../../store/stationStore', () => ({
  useStationStore: jest.fn(),
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

const setup = (over: Record<string, unknown> = {}) => {
  const fetchStations = jest.fn().mockResolvedValue(undefined);
  (useStationStore as unknown as jest.Mock).mockReturnValue({
    stations: [
      makeStation(),
      makeStation({ id: 2, name: '充电站B', address: '上海市徐汇区', status: 'maintenance', alarmCount: 3, deviceCount: 4, onlineDeviceCount: 1 }),
      makeStation({ id: 3, name: '充电站C', address: '广州市天河区', status: 'offline', deviceCount: 2, onlineDeviceCount: 0 }),
    ],
    loading: false,
    fetchStations,
    ...over,
  });
  return { fetchStations };
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('StationListScreen', () => {
  it('挂载即拉取站点列表(默认无搜索词)', async () => {
    const { fetchStations } = setup();
    render(<StationListScreen />);
    await waitFor(() => expect(fetchStations).toHaveBeenCalled());
    expect(fetchStations).toHaveBeenCalledWith({ page: 1, pageSize: 100, search: undefined });
  });

  it('渲染站点卡片: 名称/地址/设备数 + 三态状态徽章', async () => {
    setup();
    const { getByText } = render(<StationListScreen />);
    await waitFor(() => getByText('充电站A'));
    getByText('充电站B');
    getByText('充电站C');
    getByText('北京市朝阳区');
    getByText('设备 8 | 在线 6');
    getByText('在线');
    getByText('维护中');
    getByText('离线');
  });

  it('告警徽章仅在 alarmCount>0 时出现', async () => {
    setup();
    const { getByText, queryByText } = render(<StationListScreen />);
    await waitFor(() => getByText('充电站A'));
    getByText('告警 3');
    expect(queryByText('告警 0')).toBeNull();
  });

  it('点击卡片跳转站点详情(携带 stationId)', async () => {
    setup();
    const { getByText } = render(<StationListScreen />);
    await waitFor(() => getByText('充电站B'));
    fireEvent.press(getByText('充电站B'));
    expect(mockNavigate).toHaveBeenCalledWith('StationDetail', { stationId: 2 });
  });

  it('搜索提交后按搜索词重新拉取', async () => {
    const { fetchStations } = setup();
    const { UNSAFE_getByType } = render(<StationListScreen />);
    await waitFor(() => expect(fetchStations).toHaveBeenCalledTimes(1));
    const input = UNSAFE_getByType(TextInput);
    fireEvent.changeText(input, '充电站B');
    fireEvent(input, 'onSubmitEditing');
    await waitFor(() => expect(fetchStations).toHaveBeenCalledTimes(2));
    expect(fetchStations).toHaveBeenLastCalledWith({ page: 1, pageSize: 100, search: '充电站B' });
  });

  it('下拉刷新重新拉取且 refreshing 复位', async () => {
    const { fetchStations } = setup();
    const { UNSAFE_getByType } = render(<StationListScreen />);
    await waitFor(() => expect(fetchStations).toHaveBeenCalledTimes(1));
    const rc = UNSAFE_getByType(RefreshControl);
    await rc.props.onRefresh();
    expect(fetchStations).toHaveBeenCalledTimes(2);
    expect(UNSAFE_getByType(RefreshControl).props.refreshing).toBe(false);
  });

  it('loading 且非刷新中时显示加载指示器', async () => {
    setup({ loading: true });
    const { UNSAFE_getByType, queryByText } = render(<StationListScreen />);
    await waitFor(() => UNSAFE_getByType(ActivityIndicator));
    expect(queryByText('暂无站点数据')).toBeNull();
  });

  it('空列表显示空态文案', async () => {
    setup({ stations: [] });
    const { getByText } = render(<StationListScreen />);
    await waitFor(() => getByText('暂无站点数据'));
  });
});
