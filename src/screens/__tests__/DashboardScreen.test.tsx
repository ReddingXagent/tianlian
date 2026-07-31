import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import DashboardScreen from '../DashboardScreen';
import { useDashboardStore } from '../../store/dashboardStore';

const mockFetchDashboard = jest.fn();
const mockSetPeriod = jest.fn();

jest.mock('../../store/dashboardStore', () => ({
  useDashboardStore: jest.fn(),
}));

const MOCK_DATA = {
  stats: {
    totalOrders: 100,
    completedOrders: 60,
    pendingOrders: 30,
    avgCompletionHours: 4.5,
    onTimeRate: 92,
  },
  deviceHealth: {
    total: 50,
    online: 40,
    offline: 5,
    fault: 3,
    maintenance: 2,
    onlineRate: 80,
  },
  alarmTrends: [
    { date: '2024-01-15', total: 5, critical: 1, warning: 2, info: 2 },
  ],
  workOrderTrends: [{ date: '2024-01-15', created: 3, completed: 2 }],
  topFaultDevices: [
    { deviceId: 1, deviceName: '故障设备A', stationName: '充电站A', faultCount: 9 },
  ],
};

const baseStore = (overrides: Record<string, unknown> = {}) => ({
  data: MOCK_DATA,
  loading: false,
  error: null,
  selectedPeriod: 'week',
  fetchDashboard: mockFetchDashboard,
  setPeriod: mockSetPeriod,
  ...overrides,
});

describe('DashboardScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchDashboard.mockResolvedValue(undefined);
    (useDashboardStore as unknown as jest.Mock).mockReturnValue(baseStore());
  });

  it('shows loading spinner initially', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue(
      baseStore({ data: null, loading: true })
    );
    const { getByText } = render(<DashboardScreen />);
    expect(getByText('加载看板数据...')).toBeTruthy();
  });

  it('shows error state when load fails', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue(
      baseStore({ data: null, error: '出错了' })
    );
    const { getByText } = render(<DashboardScreen />);
    expect(getByText('加载失败')).toBeTruthy();
    expect(getByText('出错了')).toBeTruthy();
  });

  it('renders stats, device health and top fault devices', () => {
    const { getByText } = render(<DashboardScreen />);
    expect(getByText('工单统计')).toBeTruthy();
    expect(getByText('设备健康度')).toBeTruthy();
    expect(getByText('92%')).toBeTruthy();
    expect(getByText('故障设备A')).toBeTruthy();
  });

  it('changes period when pressing a period chip', () => {
    const { getByText } = render(<DashboardScreen />);
    fireEvent.press(getByText('月'));
    expect(mockSetPeriod).toHaveBeenCalledWith('month');
  });

  it('shows no-data placeholders when trends are empty', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue(
      baseStore({
        data: {
          ...MOCK_DATA,
          alarmTrends: [],
          workOrderTrends: [],
          topFaultDevices: [],
        },
      })
    );
    const { getByText } = render(<DashboardScreen />);
    expect(getByText('暂无告警趋势数据')).toBeTruthy();
    expect(getByText('暂无工单趋势数据')).toBeTruthy();
    expect(getByText('暂无故障设备数据')).toBeTruthy();
  });
});
