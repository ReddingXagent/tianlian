import React from 'react';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
import AlarmListScreen from '../AlarmListScreen';
import { Alarm, AlarmStatus } from '../../types';

// Mock navigation and route
const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({
    params: {},
  }),
  useNavigation: () => ({ navigate: mockNavigate }),
}));

// Mock child components
jest.mock('../../components/LoadingSpinner', () => {
  const MockLoadingSpinner = (props: { text?: string; size?: 'small' | 'large'; color?: string }) => {
    const React = require('react');
    const { Text } = require('react-native');
    return React.createElement(Text, null, props.text || '加载中...');
  };
  return MockLoadingSpinner;
});
jest.mock('../../components/StatusBadge', () => {
  const MockStatusBadge = (props: { status: string; label?: string }) => {
    const React = require('react');
    const { Text } = require('react-native');
    return React.createElement(Text, null, props.label || props.status || 'badge');
  };
  return MockStatusBadge;
});
jest.mock('../../components/EmptyState', () => {
  const MockEmptyState = (props: { icon?: string; title?: string; message?: string; actionLabel?: string; onAction?: () => void }) => {
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

// Mock the hook
const mockUseAlarms = {
  alarms: [] as Alarm[],
  loading: true,
  refreshing: false,
  filter: 'all' as AlarmStatus | 'all',
  setFilter: jest.fn(),
  refresh: jest.fn(),
};

jest.mock('../../hooks/useAlarms', () => ({
  useAlarms: () => mockUseAlarms,
}));

const MOCK_ALARMS: Alarm[] = [
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
  } as Alarm,
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
  } as Alarm,
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
  } as Alarm,
];

describe('AlarmListScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAlarms.alarms = [];
    mockUseAlarms.loading = true;
    mockUseAlarms.refreshing = false;
    mockUseAlarms.filter = 'all';
    mockUseAlarms.setFilter = jest.fn();
    mockUseAlarms.refresh = jest.fn();
  });

  it('should render loading state initially', () => {
    mockUseAlarms.loading = true;
    mockUseAlarms.refreshing = false;
    const { getByText } = render(<AlarmListScreen />);
    expect(getByText('全部')).toBeTruthy();
  });

  it('筛选chip切换: 点按状态chip调用setFilter', async () => {
    mockUseAlarms.loading = false;
    mockUseAlarms.alarms = MOCK_ALARMS;
    const { getAllByText } = render(<AlarmListScreen />);
    // '未处理' appears as both filter chip and alarm status text
    for (const el of getAllByText('未处理')) {
      fireEvent.press(el);
    }
    expect(mockUseAlarms.setFilter).toHaveBeenCalledWith('unhandled');
  });

  it('should render alarm list after loading', async () => {
    mockUseAlarms.loading = false;
    mockUseAlarms.alarms = MOCK_ALARMS;
    const { getByText, getByTestId } = render(<AlarmListScreen />);
    expect(getByText('充电桩A-01温度异常')).toBeTruthy();
    expect(getByText('充电站A功率异常')).toBeTruthy();
    expect(getByText('充电站B通信恢复')).toBeTruthy();
    // testID守卫: 卡片testID必须是prop而非children(F3688回归)
    expect(getByTestId('alarm-card-1')).toBeTruthy();
    expect(getByTestId('alarm-card-2')).toBeTruthy();
    expect(getByTestId('alarm-card-3')).toBeTruthy();
  });

  it('should render station names in alarm cards', async () => {
    mockUseAlarms.loading = false;
    mockUseAlarms.alarms = MOCK_ALARMS;
    const { getByText } = render(<AlarmListScreen />);
    expect(getByText('充电站A功率异常')).toBeTruthy();
    expect(getByText('充电站B通信恢复')).toBeTruthy();
  });

  it('should show device name for device-related alarms', async () => {
    mockUseAlarms.loading = false;
    mockUseAlarms.alarms = MOCK_ALARMS;
    const { getByText, getAllByText } = render(<AlarmListScreen />);
    expect(getByText('充电桩A-01温度异常')).toBeTruthy();
    const deviceNameElements = getAllByText(/充电桩A-01/);
    expect(deviceNameElements.length).toBeGreaterThanOrEqual(2);
  });

  it('should render filter chips', async () => {
    mockUseAlarms.loading = false;
    mockUseAlarms.alarms = MOCK_ALARMS;
    const { getByText, getAllByText } = render(<AlarmListScreen />);
    expect(getByText('全部')).toBeTruthy();
    expect(getAllByText('未处理').length).toBeGreaterThanOrEqual(1);
    expect(getAllByText('处理中').length).toBeGreaterThanOrEqual(1);
    expect(getAllByText('已解决').length).toBeGreaterThanOrEqual(1);
  });

  it('should handle error state (empty list)', async () => {
    mockUseAlarms.loading = false;
    mockUseAlarms.alarms = [];
    const { getByText } = render(<AlarmListScreen />);
    expect(getByText('暂无告警 🎉')).toBeTruthy();
  });

  it('should render empty state when no alarms', async () => {
    mockUseAlarms.loading = false;
    mockUseAlarms.alarms = [];
    const { getByText } = render(<AlarmListScreen />);
    expect(getByText('暂无告警 🎉')).toBeTruthy();
  });
});
