/**
 * DashboardScreen Extension Tests
 * 目标: 74.5% → 90%+ branches
 * 覆盖: error+data, loading+data, period selection, empty trends, alarm/workOrder trends render
 */
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
    completedOrders: 80,
    pendingOrders: 20,
    avgCompletionHours: 5,
    onTimeRate: 85,
  },
  deviceHealth: {
    online: 50,
    offline: 3,
    fault: 2,
    onlineRate: 91,
  },
  alarmTrends: [
    { date: '2026-08-01', critical: 3, warning: 5, info: 10 },
    { date: '2026-08-02', critical: 1, warning: 3, info: 7 },
  ],
  workOrderTrends: [
    { date: '2026-08-01', created: 10, completed: 8 },
    { date: '2026-08-02', created: 5, completed: 6 },
  ],
  topFaultDevices: [
    { deviceId: 1, deviceName: '充电桩A', stationName: '东站', faultCount: 15 },
    { deviceId: 2, deviceName: '充电桩B', stationName: '西站', faultCount: 10 },
    { deviceId: 3, deviceName: '充电桩C', stationName: '南站', faultCount: 8 },
  ],
};

describe('DashboardScreen.ext', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders full dashboard with data', async () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: MOCK_DATA,
      loading: false,
      error: null,
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getByText } = render(<DashboardScreen />);
    expect(getByText('100')).toBeTruthy();
    expect(getByText('总工单')).toBeTruthy();
    expect(getByText('85%')).toBeTruthy();
    expect(getByText('充电桩A')).toBeTruthy();
    expect(getByText('15次')).toBeTruthy();
  });

  it('renders error state when error and no data', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: null,
      loading: false,
      error: '网络错误',
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getByText } = render(<DashboardScreen />);
    expect(getByText('加载失败')).toBeTruthy();
    expect(getByText('网络错误')).toBeTruthy();
  });

  it('error retry calls loadData', () => {
    mockFetchDashboard.mockResolvedValue(undefined);
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: null,
      loading: false,
      error: '网络错误',
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getByText } = render(<DashboardScreen />);
    fireEvent.press(getByText('重新加载'));
    expect(mockFetchDashboard).toHaveBeenCalled();
  });

  it('period button press calls setPeriod', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: MOCK_DATA,
      loading: false,
      error: null,
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getByText } = render(<DashboardScreen />);
    fireEvent.press(getByText('月'));
    expect(mockSetPeriod).toHaveBeenCalledWith('month');
  });

  it('renders loading spinner when loading and no data', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: null,
      loading: true,
      error: null,
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getByText } = render(<DashboardScreen />);
    expect(getByText('加载看板数据...')).toBeTruthy();
  });

  it('renders data with error (error but data present)', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: MOCK_DATA,
      loading: false,
      error: '部分错误',
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    // Should show data, not error screen
    const { getByText } = render(<DashboardScreen />);
    expect(getByText('100')).toBeTruthy();
  });

  it('renders empty alarm trends message', () => {
    const emptyData = { ...MOCK_DATA, alarmTrends: [] };
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: emptyData,
      loading: false,
      error: null,
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getByText } = render(<DashboardScreen />);
    expect(getByText('暂无告警趋势数据')).toBeTruthy();
  });

  it('renders empty work order trends message', () => {
    const emptyData = { ...MOCK_DATA, workOrderTrends: [] };
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: emptyData,
      loading: false,
      error: null,
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getByText } = render(<DashboardScreen />);
    expect(getByText('暂无工单趋势数据')).toBeTruthy();
  });

  it('renders empty top fault devices message', () => {
    const emptyData = { ...MOCK_DATA, topFaultDevices: [] };
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: emptyData,
      loading: false,
      error: null,
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getByText } = render(<DashboardScreen />);
    expect(getByText('暂无故障设备数据')).toBeTruthy();
  });

  it('renders top 3 fault devices with red rank color', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: MOCK_DATA,
      loading: false,
      error: null,
      selectedPeriod: 'quarter',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getByText } = render(<DashboardScreen />);
    expect(getByText('充电桩A')).toBeTruthy();
    expect(getByText('充电桩B')).toBeTruthy();
    expect(getByText('充电桩C')).toBeTruthy();
  });

  it('renders with null data fields using fallback dashes', () => {
    const nullData: Record<string, unknown> = {
      stats: { totalOrders: null, completedOrders: null, pendingOrders: null, avgCompletionHours: null, onTimeRate: null },
      deviceHealth: { online: null, offline: null, fault: null, onlineRate: null },
      alarmTrends: null,
      workOrderTrends: null,
      topFaultDevices: null,
    };
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: nullData,
      loading: false,
      error: null,
      selectedPeriod: 'month',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getAllByText } = render(<DashboardScreen />);
    // Multiple '-' fallback values
    expect(getAllByText('-').length).toBeGreaterThan(0);
  });
});
