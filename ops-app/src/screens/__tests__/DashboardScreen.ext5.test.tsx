/**
 * DashboardScreen coverage test — targets data?.topFaultDevices falsy branch
 * F1451: DashboardScreen.tsx branches 98.18%→100%
 */
import { render } from '@testing-library/react-native';
import DashboardScreen from '../DashboardScreen';
import { useDashboardStore } from '../../store/dashboardStore';

jest.mock('../../store/dashboardStore', () => ({
  useDashboardStore: jest.fn(),
}));

const mockStore = useDashboardStore as jest.MockedFunction<typeof useDashboardStore>;

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
  alarmTrends: [],
  workOrderTrends: [],
  topFaultDevices: undefined,
};

describe('DashboardScreen — topFaultDevices undefined branch', () => {
  it('shows "暂无故障设备数据" when topFaultDevices is undefined', () => {
    mockStore.mockReturnValue({
      data: MOCK_DATA,
      loading: false,
      error: null,
      selectedPeriod: 'week',
      fetchDashboard: jest.fn(),
      setPeriod: jest.fn(),
      refresh: jest.fn(),
    } as unknown as ReturnType<typeof useDashboardStore>);

    const { getByText } = render(<DashboardScreen />);
    expect(getByText('暂无故障设备数据')).toBeTruthy();
  });
});
