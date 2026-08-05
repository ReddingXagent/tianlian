import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { RefreshControl, ActivityIndicator, View } from 'react-native';
import StationDetailScreen from '../StationDetailScreen';
import { useStationStore } from '../../store/stationStore';

const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { stationId: 7 } }),
  useNavigation: () => ({ navigate: mockNavigate }),
}));

jest.mock('../../store/stationStore', () => ({
  useStationStore: jest.fn(),
}));

const makeDevice = (over: Record<string, unknown> = {}) => ({
  id: 1, stationId: 7, name: '充电桩-01', code: 'CP-01', type: 'dc',
  status: 'online', model: 'Model-X', manufacturer: '厂商',
  lastHeartbeat: '2026-08-04T00:00:00Z', createdAt: '', updatedAt: '',
  ...over,
});

const makeAlarm = (over: Record<string, unknown> = {}) => ({
  id: 1, stationId: 7, stationName: '充电站A', type: 'overvoltage',
  level: 'critical', title: '电压过高', description: 'desc', status: 'active',
  createdAt: '2026-08-04T08:00:00Z',
  ...over,
});

const setup = (over: Record<string, unknown> = {}) => {
  const fetchStationDetail = jest.fn().mockResolvedValue(undefined);
  const fetchStationDevices = jest.fn().mockResolvedValue(undefined);
  const fetchStationAlarms = jest.fn().mockResolvedValue(undefined);
  (useStationStore as unknown as jest.Mock).mockReturnValue({
    selectedStation: {
      id: 7, name: '充电站A', code: 'ST-007', address: '上海市浦东新区', status: 'online',
    },
    devices: [makeDevice(), makeDevice({ id: 2, name: '充电桩-02', status: 'fault', model: 'Model-Y' })],
    alarms: [makeAlarm(), makeAlarm({ id: 2, title: '温度过高', level: 'warning' })],
    loading: false,
    fetchStationDetail,
    fetchStationDevices,
    fetchStationAlarms,
    ...over,
  });
  return { fetchStationDetail, fetchStationDevices, fetchStationAlarms };
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('StationDetailScreen', () => {
  it('挂载即并行拉取详情/设备/告警(使用路由 stationId)', async () => {
    const fns = setup();
    render(<StationDetailScreen />);
    await waitFor(() => {
      expect(fns.fetchStationDetail).toHaveBeenCalledWith(7);
      expect(fns.fetchStationDevices).toHaveBeenCalledWith(7);
      expect(fns.fetchStationAlarms).toHaveBeenCalledWith(7);
    });
  });

  it('渲染站点头部: 名称/编码/地址/在线徽章', async () => {
    setup();
    const { getByText } = render(<StationDetailScreen />);
    await waitFor(() => getByText('充电站A'));
    getByText('编码: ST-007');
    getByText('上海市浦东新区');
    getByText('在线');
  });

  it('快捷操作跳转: 设备(携带stationId+stationName)/告警/工单', async () => {
    setup();
    const { getByText } = render(<StationDetailScreen />);
    await waitFor(() => getByText('充电站A'));
    fireEvent.press(getByText('告警'));
    expect(mockNavigate).toHaveBeenCalledWith('AlarmList', { stationId: 7 });
    fireEvent.press(getByText('工单'));
    expect(mockNavigate).toHaveBeenCalledWith('WorkOrder', { stationId: 7 });
  });

  it('设备列表渲染名称/型号与计数', async () => {
    setup();
    const { getByText } = render(<StationDetailScreen />);
    await waitFor(() => getByText('充电桩-01'));
    getByText('充电桩-02');
    getByText('Model-X');
    getByText('设备列表 (2)');
  });

  it('设备超过5台显示"查看全部设备"并可跳转设备列表', async () => {
    setup({
      devices: Array.from({ length: 6 }, (_, i) => makeDevice({ id: i + 1, name: `桩-${i + 1}` })),
    });
    const { getByText } = render(<StationDetailScreen />);
    await waitFor(() => getByText('查看全部设备 →'));
    fireEvent.press(getByText('查看全部设备 →'));
    expect(mockNavigate).toHaveBeenCalledWith('DeviceList', { stationId: 7, stationName: '充电站A' });
  });

  it('最近告警渲染标题', async () => {
    setup();
    const { getByText } = render(<StationDetailScreen />);
    await waitFor(() => getByText('电压过高'));
    getByText('温度过高');
  });

  it('无告警显示庆祝空态; 无设备显示设备空态', async () => {
    setup({ alarms: [], devices: [] });
    const { getByText } = render(<StationDetailScreen />);
    await waitFor(() => getByText('无告警 🎉'));
    getByText('暂无设备');
  });

  it('loading 且无站点数据时显示加载指示器', () => {
    setup({ loading: true, selectedStation: null });
    const { UNSAFE_getByType } = render(<StationDetailScreen />);
    UNSAFE_getByType(ActivityIndicator);
  });

  it('下拉刷新并行重拉且 refreshing 复位', async () => {
    const fns = setup();
    const { UNSAFE_getByType } = render(<StationDetailScreen />);
    await waitFor(() => expect(fns.fetchStationDetail).toHaveBeenCalledTimes(1));
    const rc = UNSAFE_getByType(RefreshControl);
    await rc.props.onRefresh();
    expect(fns.fetchStationDetail).toHaveBeenCalledTimes(2);
    expect(fns.fetchStationDevices).toHaveBeenCalledTimes(2);
    expect(fns.fetchStationAlarms).toHaveBeenCalledTimes(2);
    expect(UNSAFE_getByType(RefreshControl).props.refreshing).toBe(false);
  });

  it('离线站点渲染"离线"徽章(离线样式分支)', async () => {
    setup({
      selectedStation: { id: 7, name: '充电站B', code: 'ST-008', address: 'addr', status: 'offline' },
    });
    const { getByText } = render(<StationDetailScreen />);
    await waitFor(() => getByText('离线'));
    expect(() => getByText('在线')).toThrow();
  });

  it('站点名称缺失时跳转回退默认名"站点"(快捷操作与查看全部两处)', async () => {
    setup({
      selectedStation: { id: 7, name: '', code: 'ST-007', address: 'addr', status: 'online' },
      devices: Array.from({ length: 6 }, (_, i) => makeDevice({ id: i + 1, name: `桩-${i + 1}` })),
    });
    const { getByText } = render(<StationDetailScreen />);
    await waitFor(() => getByText('查看全部设备 →'));
    fireEvent.press(getByText('设备'));
    expect(mockNavigate).toHaveBeenLastCalledWith('DeviceList', { stationId: 7, stationName: '站点' });
    fireEvent.press(getByText('查看全部设备 →'));
    expect(mockNavigate).toHaveBeenLastCalledWith('DeviceList', { stationId: 7, stationName: '站点' });
  });

  it('离线设备状态点走 dotOffline 样式分支', async () => {
    setup({ devices: [makeDevice({ status: 'offline', name: '离线桩' })] });
    const { getByText, UNSAFE_getAllByType } = render(<StationDetailScreen />);
    await waitFor(() => getByText('离线桩'));
    const dot = UNSAFE_getAllByType(View).find((v) => {
      const arr = (Array.isArray(v.props.style) ? v.props.style : [v.props.style]) as (Record<string, unknown> | null | undefined)[];
      return arr.some((s) => s && s.backgroundColor === '#666') && arr.some((s) => s && s.width === 10);
    });
    expect(dot).toBeTruthy();
  });
});
