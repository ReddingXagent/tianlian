/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import ChargerMonitorScreen from '../ChargerMonitorScreen';
import { chargerApi } from '../../services/api';

// Mock navigation and route
const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({
    params: { stationId: 1, stationName: '充电站A' },
  }),
  useNavigation: () => ({ navigate: mockNavigate }),
}));

// Mock the API module
jest.mock('../../services/api', () => ({
  chargerApi: {
    getMonitorList: jest.fn(),
    getMonitorSummary: jest.fn(),
    getTrend: jest.fn(),
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
jest.mock('../../components/ChargerTrendChart', () => {
  const MockTrend = (props: any) => {
    const React = require('react');
    const { Text } = require('react-native');
    return React.createElement(Text, { testID: 'trend-mock' }, `趋势:${props.deviceId}`);
  };
  return MockTrend;
});

const MOCK_CHARGERS = [
  {
    id: 1,
    deviceId: 101,
    deviceName: '充电桩A-01',
    connectorStatus: 'charging' as const,
    power: 45.6,
    voltage: 380,
    current: 120,
    temperature: 42,
    soc: 65,
    energyTotal: 12345.6,
    sessionEnergy: 12.3,
    sessionDuration: 45,
    state: 'charging' as const,
    faultCode: null,
    faultMessage: null,
    lastHeartbeat: '2024-01-15T10:30:00Z',
    updatedAt: '2024-01-15T10:30:00Z',
  },
  {
    id: 2,
    deviceId: 102,
    deviceName: '充电桩A-02',
    connectorStatus: 'idle' as const,
    power: 0,
    voltage: 220,
    current: 0,
    temperature: 28,
    energyTotal: 5678.9,
    sessionEnergy: 0,
    sessionDuration: 0,
    state: 'idle' as const,
    faultCode: null,
    faultMessage: null,
    lastHeartbeat: '2024-01-15T10:29:00Z',
    updatedAt: '2024-01-15T10:29:00Z',
  },
  {
    id: 3,
    deviceId: 103,
    deviceName: '充电桩A-03',
    connectorStatus: 'fault' as const,
    power: 0,
    voltage: 0,
    current: 0,
    temperature: 68,
    energyTotal: 9000,
    sessionEnergy: 0,
    sessionDuration: 0,
    state: 'fault' as const,
    faultCode: 'E001',
    faultMessage: '充电枪温度过高，已自动停止充电',
    lastHeartbeat: '2024-01-15T10:25:00Z',
    updatedAt: '2024-01-15T10:25:00Z',
  },
];

const MOCK_SUMMARY = {
  totalChargers: 3,
  chargingCount: 1,
  idleCount: 1,
  faultCount: 1,
  totalPower: 45.6,
  todayEnergy: 256.8,
  todaySessions: 15,
  avgPowerPerCharger: 15.2,
};

describe('ChargerMonitorScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (chargerApi.getMonitorList as jest.Mock).mockResolvedValue({ data: MOCK_CHARGERS });
    (chargerApi.getMonitorSummary as jest.Mock).mockResolvedValue({ data: MOCK_SUMMARY });
  });

  it('should render loading state initially', () => {
    (chargerApi.getMonitorList as jest.Mock).mockImplementation(() => new Promise(() => {}));
    (chargerApi.getMonitorSummary as jest.Mock).mockImplementation(() => new Promise(() => {}));

    const { getByText } = render(<ChargerMonitorScreen />);
    expect(getByText('加载监控面板...')).toBeTruthy();
  });

  it('should render chargers after loading', async () => {
    const { findByText } = render(<ChargerMonitorScreen />);

    expect(await findByText('充电桩A-01')).toBeTruthy();
    expect(await findByText('充电桩A-02')).toBeTruthy();
    expect(await findByText('充电桩A-03')).toBeTruthy();
  });

  it('should render summary statistics', async () => {
    const { findByText } = render(<ChargerMonitorScreen />);

    // 等待充电桩名称加载后，检查汇总标签
    await findByText('充电桩A-01');
    expect(await findByText('今日充电 kWh')).toBeTruthy();
    expect(await findByText('今日充电次数')).toBeTruthy();
    expect(await findByText('平均功率 kW')).toBeTruthy();
  });

  it('should display fault information for faulty chargers', async () => {
    const { findByText } = render(<ChargerMonitorScreen />);

    expect(await findByText('故障码: E001')).toBeTruthy();
    expect(await findByText('充电枪温度过高，已自动停止充电')).toBeTruthy();
  });

  it('should show charging session info for active chargers', async () => {
    const { findByText } = render(<ChargerMonitorScreen />);

    // 充电中显示会话信息
    expect(await findByText(/本会话/)).toBeTruthy();
  });

  it('should display SOC in session info when available', async () => {
    const { findByText } = render(<ChargerMonitorScreen />);

    expect(await findByText(/电量 65%/)).toBeTruthy();
  });

  it('should show a trend toggle hint on each charger card', async () => {
    const { findAllByText } = render(<ChargerMonitorScreen />);

    await findAllByText('充电桩A-01');
    const toggles = await findAllByText(/趋势 ▾/);
    expect(toggles.length).toBeGreaterThan(0);
  });

  it('should expand the trend chart when tapping a charger card', async () => {
    const { findByText, getAllByText, getByText } = render(<ChargerMonitorScreen />);

    await findByText('充电桩A-01');

    // 初始每个充电桩都显示「趋势 ▾」
    expect(getAllByText('趋势 ▾').length).toBe(3);

    // 点击第一个充电桩卡片头部，展开趋势
    fireEvent.press(getAllByText('趋势 ▾')[0]);

    // 展开后渲染趋势组件，且该卡片切换为「收起 ▴」
    expect(getByText('趋势:101')).toBeTruthy();
    expect(getByText('收起 ▴')).toBeTruthy();
    expect(getAllByText('趋势 ▾').length).toBe(2);
  });

  it('should collapse the trend chart when tapping an expanded card again', async () => {
    const { findByText, getAllByText, queryByText } = render(<ChargerMonitorScreen />);

    await findByText('充电桩A-01');

    fireEvent.press(getAllByText('趋势 ▾')[0]);
    expect(getAllByText('收起 ▴').length).toBe(1);

    // 再次点击「收起 ▴」收起
    fireEvent.press(getAllByText('收起 ▴')[0]);
    expect(queryByText('趋势:101')).toBeNull();
  });

  it('should handle error state', async () => {
    (chargerApi.getMonitorList as jest.Mock).mockRejectedValue(new Error('API Error'));

    const { findByText } = render(<ChargerMonitorScreen />);
    // The component renders EmptyState with title="加载失败" and message=error.message
    expect(await findByText('加载失败')).toBeTruthy();
    expect(await findByText('API Error')).toBeTruthy();
    expect(await findByText('重新加载')).toBeTruthy();
  });

  it('should render empty state when no chargers', async () => {
    (chargerApi.getMonitorList as jest.Mock).mockResolvedValue({ data: [] });

    const { findByText } = render(<ChargerMonitorScreen />);
    expect(await findByText('暂无充电桩')).toBeTruthy();
  });
});