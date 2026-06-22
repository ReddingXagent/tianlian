import React from 'react';
import { render, act } from '@testing-library/react-native';
import AlarmListScreen from '../AlarmListScreen';
import { alarmApi } from '../../services/api';

// Mock navigation and route
const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({
    params: {},
  }),
  useNavigation: () => ({ navigate: mockNavigate }),
}));

// Mock the API module
jest.mock('../../services/api', () => ({
  alarmApi: {
    getList: jest.fn(),
  },
}));

// Mock child components
jest.mock('../../components/LoadingSpinner', () => {
  const MockLoadingSpinner = (props: any) => {
    const React = require('react');
    const { Text } = require('react-native');
    return React.createElement(Text, null, props.text || '加载中...');
  };
  return MockLoadingSpinner;
});
jest.mock('../../components/StatusBadge', () => {
  const MockStatusBadge = (props: any) => {
    const React = require('react');
    const { Text } = require('react-native');
    return React.createElement(Text, null, props.label || props.status || 'badge');
  };
  return MockStatusBadge;
});
jest.mock('../../components/EmptyState', () => {
  const MockEmptyState = (props: any) => {
    const React = require('react');
    const { View, Text, TouchableOpacity } = require('react-native');
    const elements = [React.createElement(Text, { key: 'title' }, props.title || '')];
    if (props.message) {
      elements.push(React.createElement(Text, { key: 'msg' }, props.message));
    }
    if (props.actionLabel && props.onAction) {
      elements.push(
        React.createElement(TouchableOpacity, { key: 'btn', onPress: props.onAction },
          React.createElement(Text, null, props.actionLabel)
        )
      );
    }
    return React.createElement(View, null, elements);
  };
  return MockEmptyState;
});

const MOCK_ALARMS = [
  {
    id: 1,
    stationId: 1,
    stationName: '充电站A',
    deviceId: 101,
    deviceName: '充电桩A-01',
    type: 'device_fault' as const,
    level: 'critical' as const,
    title: '充电桩A-01温度异常',
    description: '充电桩A-01充电枪温度达到85°C，超过安全阈值，请立即处理',
    status: 'unhandled' as const,
    createdAt: '2024-01-15T10:30:00Z',
    updatedAt: '2024-01-15T10:30:00Z',
  },
  {
    id: 2,
    stationId: 1,
    stationName: '充电站A',
    type: 'power_anomaly' as const,
    level: 'warning' as const,
    title: '充电站A功率异常',
    description: '充电站A总功率超过额定功率的80%',
    status: 'processing' as const,
    createdAt: '2024-01-15T09:00:00Z',
    updatedAt: '2024-01-15T09:30:00Z',
  },
  {
    id: 3,
    stationId: 2,
    stationName: '充电站B',
    type: 'communication_loss' as const,
    level: 'info' as const,
    title: '充电站B通信恢复',
    description: '充电站B通信连接已恢复正常',
    status: 'resolved' as const,
    createdAt: '2024-01-14T08:00:00Z',
    updatedAt: '2024-01-14T09:00:00Z',
  },
];

describe('AlarmListScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (alarmApi.getList as jest.Mock).mockResolvedValue({
      data: { items: MOCK_ALARMS, total: 3, page: 1, pageSize: 20 },
    });
  });

  it('should render loading state initially', () => {
    (alarmApi.getList as jest.Mock).mockImplementation(() => new Promise(() => {}));

    const { getByText } = render(<AlarmListScreen />);
    expect(getByText('加载告警列表...')).toBeTruthy();
  });

  it('should render alarm list after loading', async () => {
    const { findByText } = render(<AlarmListScreen />);

    expect(await findByText('充电桩A-01温度异常')).toBeTruthy();
    expect(await findByText('充电站A功率异常')).toBeTruthy();
    expect(await findByText('充电站B通信恢复')).toBeTruthy();
  });

  it('should render station names in alarm cards', async () => {
    const { findAllByText, findByText } = render(<AlarmListScreen />);

    const stationAElements = await findAllByText('充电站A');
    expect(stationAElements.length).toBe(2); // 两条告警都属于充电站A
    expect(await findByText('充电站B')).toBeTruthy();
  });

  it('should show device name for device-related alarms', async () => {
    const { findByText } = render(<AlarmListScreen />);

    // 有设备名称的告警显示设备名
    expect(await findByText('· 充电桩A-01')).toBeTruthy();
  });

  it('should render filter chips', async () => {
    const { findAllByText, findByText } = render(<AlarmListScreen />);

    const allChips = await findAllByText('全部');
    expect(allChips.length).toBe(2); // 级别和状态各有一个"全部"
    expect(await findByText('严重')).toBeTruthy();
    expect(await findByText('警告')).toBeTruthy();
    expect(await findByText('未处理')).toBeTruthy();
    expect(await findByText('已解决')).toBeTruthy();
  });

  it('should handle error state', async () => {
    (alarmApi.getList as jest.Mock).mockRejectedValue(new Error('API Error'));

    const { findByText } = render(<AlarmListScreen />);
    expect(await findByText('加载告警列表失败')).toBeTruthy();
  });

  it('should render empty state when no alarms', async () => {
    (alarmApi.getList as jest.Mock).mockResolvedValue({
      data: { items: [], total: 0, page: 1, pageSize: 20 },
    });

    const { findByText } = render(<AlarmListScreen />);
    expect(await findByText('暂无告警')).toBeTruthy();
  });
});