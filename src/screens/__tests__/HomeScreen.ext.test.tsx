import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import HomeScreen from '../HomeScreen';
import type { Station } from '../../types';

let mockFocused = true;
let mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useIsFocused: () => mockFocused,
}));

const mockState: {
  stations: Partial<Station>[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  fetchStations: jest.Mock;
  refreshStations: jest.Mock;
  searchStations: jest.Mock;
  total: number;
  page: number;
  selectedStation: unknown;
  chargers: unknown[];
  setSelectedStation: jest.Mock;
} = {
  stations: [],
  loading: false,
  refreshing: false,
  error: null,
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

// Use real components for EmptyState/LoadingSpinner/StationCard to verify text rendering
jest.unmock('../../components/LoadingSpinner');
jest.unmock('../../components/EmptyState');
jest.unmock('../../components/StationCard');
jest.mock('../../components/MapView', () => 'MapView');

describe('HomeScreen.ext — coverage lift 54.5% -> 95%', () => {
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

  // loading state
  it('renders LoadingSpinner when loading with no cached stations', () => {
    mockState.loading = true;
    mockState.stations = [];
    const { getByText } = renderHome();
    expect(getByText('加载附近站点...')).toBeTruthy();
  });

  // error state
  it('renders error EmptyState when error and no cached stations', () => {
    mockState.error = '网络异常';
    mockState.stations = [];
    const { getByText } = renderHome();
    expect(getByText('重试')).toBeTruthy();
  });

  // search-specific empty message
  it('shows search-specific empty message when search yields no results', () => {
    mockState.stations = [];
    const { getByPlaceholderText, getByText } = renderHome();
    fireEvent.changeText(getByPlaceholderText('搜索充电站...'), '不存在的站');
    fireEvent.press(getByText('搜索'));
    expect(getByText('未找到匹配的站点，试试其他关键词')).toBeTruthy();
  });

  // default empty message
  it('shows default empty message without search term', () => {
    mockState.stations = [];
    const { getByText } = renderHome();
    expect(getByText('当前附近没有充电站')).toBeTruthy();
  });

  // clear search button show/hide
  it('shows clear search button when search text is not empty', () => {
    const { getByPlaceholderText, getByText } = renderHome();
    fireEvent.changeText(getByPlaceholderText('搜索充电站...'), 'abc');
    expect(getByText('清除搜索')).toBeTruthy();
  });

  it('hides clear search button when search text is empty', () => {
    const { queryByText } = renderHome();
    expect(queryByText('清除搜索')).toBeNull();
  });

  // clear search -> refetch
  it('clears search and refetches on clear search press', () => {
    const { getByPlaceholderText, getByText } = renderHome();
    fireEvent.changeText(getByPlaceholderText('搜索充电站...'), 'abc');
    fireEvent.press(getByText('清除搜索'));
    expect(mockState.fetchStations).toHaveBeenCalled();
    const input = getByPlaceholderText('搜索充电站...');
    expect(input.props.value).toBe('');
  });

  // empty search -> fetchStations
  it('calls fetchStations when search text is empty', () => {
    const { getByText } = renderHome();
    fireEvent.press(getByText('搜索'));
    expect(mockState.fetchStations).toHaveBeenCalled();
  });

  // keyword search -> searchStations
  it('calls searchStations when search text is not empty', () => {
    const { getByPlaceholderText, getByText } = renderHome();
    fireEvent.changeText(getByPlaceholderText('搜索充电站...'), '快充');
    fireEvent.press(getByText('搜索'));
    expect(mockState.searchStations).toHaveBeenCalledWith('快充');
  });

  // submit editing triggers search
  it('triggers search on submit editing', () => {
    const { getByPlaceholderText } = renderHome();
    const input = getByPlaceholderText('搜索充电站...');
    fireEvent.changeText(input, '特来电');
    fireEvent(input, 'submitEditing');
    expect(mockState.searchStations).toHaveBeenCalledWith('特来电');
  });

  // station press -> navigate
  it('navigates to StationDetail on station card press', () => {
    mockState.stations = [
      { id: 1, name: '站点A', pricePerKwh: 1.2, serviceFee: 0.5, availableConnectors: 2, distance: 500, address: 'addr', status: 'online', totalConnectors: 4 },
    ];
    const { getByText } = renderHome();
    fireEvent.press(getByText('站点A'));
    expect(mockNavigate).toHaveBeenCalledWith('StationDetail', { stationId: 1 });
  });

  // station cards rendered
  it('renders station cards when stations exist', () => {
    mockState.stations = [
      { id: 1, name: '站1', pricePerKwh: 1.0, serviceFee: 0.5, availableConnectors: 2, distance: 500, address: 'addr', status: 'online', totalConnectors: 4 },
      { id: 2, name: '站2', pricePerKwh: 1.5, serviceFee: 0.6, availableConnectors: 3, distance: 1000, address: 'addr2', status: 'online', totalConnectors: 4 },
    ];
    const { getByText } = renderHome();
    expect(getByText('站1')).toBeTruthy();
    expect(getByText('站2')).toBeTruthy();
  });
});