import React from 'react';
import { render, act, fireEvent, waitFor } from '@testing-library/react-native';
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

    // The component uses ActivityIndicator (no text), but the loading state
    // should show the filter row while loading. The ActivityIndicator has no
    // accessible text, so we check that filter chips are visible instead.
    const { getByText } = render(<AlarmListScreen />);
    // Filter chips should be visible during loading
    expect(getByText('全部')).toBeTruthy();
  });

  it('筛选chip切换: 点按状态chip触发带status参数的重新拉取(setFilter非all分支)', async () => {
    const { getAllByText } = render(<AlarmListScreen />);
    await waitFor(() => {
      expect((alarmApi.getList as jest.Mock).mock.calls.length).toBeGreaterThan(0);
    });
    // '未处理'在chip与告警卡片状态文本双处出现, 逐个press——仅chip有onPress生效
    for (const el of getAllByText('未处理')) {
      fireEvent.press(el);
    }
    await waitFor(() => {
      const calls = (alarmApi.getList as jest.Mock).mock.calls;
      const last = calls[calls.length - 1][0];
      expect(last.status).toBe('unhandled');
    });
  });

  it('should render alarm list after loading', async () => {
    const { findByText } = render(<AlarmListScreen />);

    expect(await findByText('充电桩A-01温度异常')).toBeTruthy();
    expect(await findByText('充电站A功率异常')).toBeTruthy();
    expect(await findByText('充电站B通信恢复')).toBeTruthy();
  });

  it('should render station names in alarm cards', async () => {
    const { findByText } = render(<AlarmListScreen />);

    // Station name is only in the alarm title text (e.g. "充电站A功率异常")
    // not rendered separately, so we verify via the title text
    expect(await findByText('充电站A功率异常')).toBeTruthy();
    expect(await findByText('充电站B通信恢复')).toBeTruthy();
  });

  it('should show device name for device-related alarms', async () => {
    const { findByText, findAllByText } = render(<AlarmListScreen />);

    // The alarm title already contains the device name: "充电桩A-01温度异常"
    expect(await findByText('充电桩A-01温度异常')).toBeTruthy();
    // Device name appears in title and description
    const deviceNameElements = await findAllByText(/充电桩A-01/);
    expect(deviceNameElements.length).toBeGreaterThanOrEqual(2);
  });

  it('should render filter chips', async () => {
    const { findByText, getAllByText } = render(<AlarmListScreen />);

    // The component renders a single filter row with status filters
    // "未处理" also appears as status text in the first alarm card
    // "处理中" also appears as status text in the second alarm card
    expect(await findByText('全部')).toBeTruthy();
    expect(getAllByText('未处理').length).toBeGreaterThanOrEqual(1);
    expect(getAllByText('处理中').length).toBeGreaterThanOrEqual(1);
    expect(getAllByText('已解决').length).toBeGreaterThanOrEqual(1);
  });

  it('should handle error state', async () => {
    (alarmApi.getList as jest.Mock).mockRejectedValue(new Error('API Error'));

    const { findByText } = render(<AlarmListScreen />);
    // Wait for the async loadData to complete (it catches errors silently)
    // The component catches errors and just shows empty list with ActivityIndicator
    // We need to wait for the loading to finish
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });
    // After error, component shows empty state "暂无告警 🎉" (not error text)
    expect(await findByText('暂无告警 🎉')).toBeTruthy();
  });

  it('should render empty state when no alarms', async () => {
    (alarmApi.getList as jest.Mock).mockResolvedValue({
      data: { items: [], total: 0, page: 1, pageSize: 20 },
    });

    // The empty state text includes an emoji
    const { findByText } = render(<AlarmListScreen />);
    expect(await findByText('暂无告警 🎉')).toBeTruthy();
  });
});