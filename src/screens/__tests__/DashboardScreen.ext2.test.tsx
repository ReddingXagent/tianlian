/**
 * DashboardScreen ext2 — lines 37-42: refresh + error&data coexist
 * Line 123: deviceHealth null fallbacks (dashes)
 */
import { render } from '@testing-library/react-native';
import DashboardScreen from '../DashboardScreen';
import { useDashboardStore } from '../../store/dashboardStore';

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
  useFocusEffect: jest.fn(cb => cb()),
}));

jest.mock('../../store/dashboardStore', () => ({
  useDashboardStore: jest.fn(),
}));

const mockFetchDashboard = jest.fn().mockResolvedValue(undefined);
const mockSetPeriod = jest.fn();

describe('DashboardScreen.ext2', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchDashboard.mockResolvedValue(undefined);
  });

  // Line 37-42: error+data coexist → shows ScrollView not error state
  it('renders ScrollView when error exists but data is present', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: {
        stats: { totalStations: 10, totalDevices: 50, activeAlarms: 5, pendingOrders: 3 },
        deviceHealth: { online: 40, offline: 5, fault: 5, onlineRate: 80 },
        trends: [],
        recentOrders: [],
      },
      loading: false,
      error: 'Partial error',
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getByText, queryByText } = render(<DashboardScreen />);
    expect(getByText('在线')).toBeTruthy();
    expect(queryByText('加载失败')).toBeNull();
  });

  // Line 123: null deviceHealth renders dashes
  it('renders dashes when deviceHealth fields are null/undefined', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: {
        stats: { totalStations: 0, totalDevices: 0, activeAlarms: 0, pendingOrders: 0 },
        deviceHealth: { online: null, offline: null, fault: null, onlineRate: null },
        trends: [],
        recentOrders: [],
      },
      loading: false,
      error: null,
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getAllByText } = render(<DashboardScreen />);
    const dashes = getAllByText('-');
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });

  // data is null + loading false → renders with all fallback dashes
  it('renders with null data showing all fallback dashes', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: null,
      loading: false,
      error: null,
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getAllByText } = render(<DashboardScreen />);
    const dashes = getAllByText('-');
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });

  // loading=true + no data → LoadingSpinner
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

  // zero values render 0%
  it('renders zeros for stats when data has zero values', () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: {
        stats: { totalStations: 0, totalDevices: 0, activeAlarms: 0, pendingOrders: 0 },
        deviceHealth: { online: 0, offline: 0, fault: 0, onlineRate: 0 },
        trends: [],
        recentOrders: [],
      },
      loading: false,
      error: null,
      selectedPeriod: 'week',
      fetchDashboard: mockFetchDashboard,
      setPeriod: mockSetPeriod,
    });

    const { getByText } = render(<DashboardScreen />);
    expect(getByText('在线率')).toBeTruthy();
    expect(getByText('0%')).toBeTruthy();
  });
});
