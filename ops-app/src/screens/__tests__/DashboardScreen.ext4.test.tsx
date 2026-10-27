/**
 * DashboardScreen ext4 — onRefresh real reload (line 69)
 * Target: RefreshControl onRefresh={() => loadData(true)}
 * F1203 layering aftermath: effect only calls loadCore, wrapper triggered
 * only by pull-to-refresh. All 22 existing tests bypass this branch.
 * Method: findAllByType(RefreshControl) direct lookup, fail-fast if absent,
 * fetch count anchored 1 -> 2 after refresh fire.
 */
import { render, act } from '@testing-library/react-native';
import { RefreshControl } from 'react-native';
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

describe('DashboardScreen.ext4 onRefresh reload', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('triggers loadData(true) via pull-to-refresh, fetch anchored 1 -> 2', async () => {
    const fetchDashboard = jest.fn().mockResolvedValue(undefined);
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: BASE_DATA, loading: false, error: null,
      selectedPeriod: 'week', fetchDashboard, setPeriod: jest.fn(),
    });

    const { UNSAFE_root } = render(<DashboardScreen />);

    // fail-fast: RefreshControl must be in the tree with onRefresh wired
    const rcs = UNSAFE_root.findAllByType(RefreshControl);
    expect(rcs.length).toBeGreaterThan(0);
    const onRefresh = rcs[0].props.onRefresh;
    expect(typeof onRefresh).toBe('function');

    // mount effect already called fetchDashboard once
    expect(fetchDashboard).toHaveBeenCalledTimes(1);

    await act(async () => {
      onRefresh();
      // flush loadData(true) body: await fetchDashboard + setRefreshing(false)
      await Promise.resolve();
    });

    // real reload anchored: 1 -> 2
    expect(fetchDashboard).toHaveBeenCalledTimes(2);
  });
});
