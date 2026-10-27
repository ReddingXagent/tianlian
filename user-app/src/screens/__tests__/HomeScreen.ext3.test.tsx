import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { RefreshControl } from 'react-native';
import HomeScreen from '../HomeScreen';

// Track store state for manipulation
const mockState: Record<string, unknown> = {};

jest.mock('../../store/stationStore', () => ({
  useStationStore: jest.fn(() => mockState),
}));

const { useStationStore } = require('../../store/stationStore');

let mockFocused = true;

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
  useIsFocused: () => mockFocused,
}));

jest.mock('../../components/StationCard', () => 'StationCard');
jest.mock('../../components/MapView', () => 'MapView');

const stations = [
  { id: 1, name: '站A', address: 'addr', status: 'online', latitude: 30, longitude: 120, pricePerKwh: 1.0, serviceFee: 0.5, totalConnectors: 5, availableConnectors: 2, chargingConnectors: 1, isOpen24h: true, rating: 4.5, createdAt: '', updatedAt: '' },
];

describe('HomeScreen.ext3 — handleRefresh branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
    // Reset to defaults
    Object.assign(mockState, {
      stations: [],
      loading: false,
      refreshing: false,
      error: null,
      fetchStations: jest.fn().mockResolvedValue(undefined),
      refreshStations: jest.fn().mockResolvedValue(undefined),
      searchStations: jest.fn().mockResolvedValue(undefined),
    });
    // Re-mock to pick up new function references
    (useStationStore as jest.Mock).mockReturnValue(mockState);
  });

  /**
   * RefreshControl onRefresh → handleRefresh
   * Line 67: if (searchText.trim()) → searchStations(path)
   * Line 70: else → refreshStations(path)
   *
   * Both branches need firing. We spy on the mock functions passed to the store.
   */
  it('handleRefresh with search text calls searchStations', async () => {
    mockState.stations = stations;
    const searchSpy = jest.fn().mockResolvedValue(undefined);
    mockState.searchStations = searchSpy;

    const { getByPlaceholderText, UNSAFE_root } = render(
      <SafeAreaProvider><HomeScreen /></SafeAreaProvider>,
    );

    // Type search text
    fireEvent.changeText(getByPlaceholderText('搜索充电站...'), '快充');
    fireEvent.press(getByPlaceholderText('搜索充电站...').props.onSubmitEditing?.() ?? (() => {}));

    // Find and fire RefreshControl onRefresh
    const refreshControl = UNSAFE_root.findByType(RefreshControl);
    await waitFor(() => {
      refreshControl.props.onRefresh();
    });

    expect(searchSpy).toHaveBeenCalledWith('快充');
  });

  it('handleRefresh without search text calls refreshStations', async () => {
    mockState.stations = stations;
    const refreshSpy = jest.fn().mockResolvedValue(undefined);
    mockState.refreshStations = refreshSpy;

    const { UNSAFE_root } = render(
      <SafeAreaProvider><HomeScreen /></SafeAreaProvider>,
    );

    const refreshControl = UNSAFE_root.findByType(RefreshControl);
    await waitFor(() => {
      refreshControl.props.onRefresh();
    });

    expect(refreshSpy).toHaveBeenCalled();
  });
});
