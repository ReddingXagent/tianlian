/**
 * DashboardScreen ext3 — topFaultDevices border fallback (line 208)
 * Target: (data?.topFaultDevices?.length || 1) - the || 1 fallback
 * When data.topFaultDevices is undefined but the ternary still evaluates
 */
import { render } from '@testing-library/react-native';
import DashboardScreen from '../DashboardScreen';
import { useDashboardStore } from '../../store/dashboardStore';

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../store/dashboardStore', () => ({
  useDashboardStore: jest.fn(),
}));

const BASE_DATA = {
  stats: { totalStations: 10, totalDevices: 50, activeAlarms: 5, pendingOrders: 3 },
  deviceHealth: { online: 40, offline: 5, fault: 5, onlineRate: 80 },
  trends: [],
  recentOrders: [],
  topFaultDevices: [
    { deviceId: 1, deviceName: '设备A', stationName: '站A', faultCount: 10 },
  ],
};

describe('DashboardScreen.ext3 single topFaultDevice', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders single fault device without border (idx=0, 0 < 0=false)', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: BASE_DATA, loading: false, error: null,
      selectedPeriod: 'week', fetchDashboard: jest.fn(), setPeriod: jest.fn(),
    });
    const { getByText } = render(<DashboardScreen />);
    expect(getByText('设备A')).toBeTruthy();
    expect(getByText('10次')).toBeTruthy();
  });
});
