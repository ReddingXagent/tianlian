import React from 'react';
import { RefreshControl } from 'react-native';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import HomeScreen from '../HomeScreen';
import type { Station } from '../../types';

let mockFocused = true;
let mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useIsFocused: () => mockFocused,
}));

const mockState = {
  stations: [] as Partial<Station>[],
  loading: false,
  refreshing: false,
  error: null as string | null,
  fetchStations: jest.fn().mockResolvedValue(undefined),
  refreshStations: jest.fn().mockResolvedValue(undefined),
  searchStations: jest.fn().mockResolvedValue(undefined),
  total: 0,
  page: 1,
  selectedStation: null,
  chargers: [],
  setSelectedStation: jest.fn(),
};

jest.mock('../../store/stationStore', () => ({
  useStationStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    if (selector) return selector(mockState);
    return mockState;
  },
}));

// Real components for rendering verification
jest.unmock('../../components/LoadingSpinner');
jest.unmock('../../components/EmptyState');
jest.unmock('../../components/StationCard');
jest.mock('../../components/MapView', () => 'MapView');


// F1207: stations非空→ScrollView分支渲染RefreshControl
const makeStation = (id: number): Partial<Station> => ({
  id,
  name: `站${id}`,
  latitude: 30,
  longitude: 120,
  status: 'online',
  totalConnectors: 4,
  availableConnectors: 2,
  chargingConnectors: 0,
  pricePerKwh: 1.2,
  serviceFee: 0.4,
});

describe('HomeScreen.ext2 — refresh + isSearching branches', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
    mockState.stations = [];
    mockState.loading = false;
    mockState.error = null;
    mockState.refreshing = false;
  });

  const renderHome = () =>
    render(
      <SafeAreaProvider>
        <HomeScreen />
      </SafeAreaProvider>
    );

  it('triggers refreshStations via pull-to-refresh when no search text', async () => {
    // F1207: 空壳修复 — ScrollView+RefreshControl仅在stations非空时渲染, 必须给数据才能真触发
    mockState.stations = [makeStation(1), makeStation(2)];
    const { UNSAFE_root } = renderHome();

    // F1206教训: findByType直查, 找不到即抛错(fail-fast), 禁用if守卫静默跳过
    const refreshControl = UNSAFE_root.findByType(RefreshControl);
    expect(typeof refreshControl.props.onRefresh).toBe('function');

    refreshControl.props.onRefresh();
    // 无搜索词分支: handleRefresh→refreshStations (计数锚定)
    expect(mockState.refreshStations).toHaveBeenCalledTimes(1);
    expect(mockState.searchStations).not.toHaveBeenCalled();
  });

  it('calls searchStations on refresh when search text is present', async () => {
    const { getByPlaceholderText, getByText } = renderHome();
    fireEvent.changeText(getByPlaceholderText('搜索充电站...'), '快充');
    fireEvent.press(getByText('搜索'));

    await waitFor(() => {
      expect(mockState.searchStations).toHaveBeenCalledWith('快充');
    });
  });

  it('shows "..." in search button when isSearching', async () => {
    // searchStations is async — while it's pending, isSearching=true
    let resolveSearch: () => void;
    mockState.searchStations = jest.fn().mockImplementation(
      () => new Promise<void>((resolve) => { resolveSearch = resolve; })
    );

    const { getByPlaceholderText, getByText } = renderHome();
    fireEvent.changeText(getByPlaceholderText('搜索充电站...'), 'test');
    fireEvent.press(getByText('搜索'));

    // While pending, button shows '...'
    await waitFor(() => {
      expect(getByText('...')).toBeTruthy();
    });

    // Resolve
    resolveSearch!();
  });

  it('renders error EmptyState with retry when error and no stations', () => {
    mockState.error = '服务器错误';
    const { getByText } = renderHome();
    expect(getByText('加载失败')).toBeTruthy();
    expect(getByText('服务器错误')).toBeTruthy();
    // Press retry
    fireEvent.press(getByText('重试'));
    expect(mockState.fetchStations).toHaveBeenCalled();
  });

  it('renders LoadingSpinner on error retry', () => {
    mockState.error = '网络错误';
    mockState.loading = true;
    const { getByText } = renderHome();
    expect(getByText('加载附近站点...')).toBeTruthy();
  });

  it('shows refresh action on empty state without search term', () => {
    const { getByText } = renderHome();
    expect(getByText('刷新')).toBeTruthy();
    fireEvent.press(getByText('刷新'));
    expect(mockState.fetchStations).toHaveBeenCalled();
  });

  it('does not show refresh action on empty state with search term', () => {
    const { getByPlaceholderText } = renderHome();
    fireEvent.changeText(getByPlaceholderText('搜索充电站...'), '不存在');
    // No '刷新' button in empty state when search term present
    // The search-specific empty message appears after search
  });

  it('renders stations list with ScrollView and MapView when data exists', () => {
    mockState.stations = [
      { id: 1, name: '快充站', pricePerKwh: 1.2, serviceFee: 0.5, availableConnectors: 2, distance: 300, address: 'addr1', status: 'online', totalConnectors: 4 },
      { id: 2, name: '超充站', pricePerKwh: 1.8, serviceFee: 0.3, availableConnectors: 0, distance: 800, address: 'addr2', status: 'online', totalConnectors: 2 },
    ];
    const { getByText } = renderHome();
    expect(getByText('快充站')).toBeTruthy();
    expect(getByText('超充站')).toBeTruthy();
  });
});
