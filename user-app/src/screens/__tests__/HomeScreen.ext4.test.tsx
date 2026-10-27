import React from 'react';
import { render } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import HomeScreen from '../HomeScreen';

const mockNavigate = jest.fn();

let mockActiveOrderId: number | null = null;

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useIsFocused: () => true,
}));

jest.mock('../../hooks/useChargingPolling', () => ({
  useActiveCharging: () => ({
    activeOrderId: mockActiveOrderId,
    loading: false,
    error: null,
    checkActive: jest.fn(),
  }),
}));

const mockState: Record<string, unknown> = {
  stations: [],
  loading: false,
  refreshing: false,
  error: null,
  fetchStations: jest.fn().mockResolvedValue(undefined),
  refreshStations: jest.fn().mockResolvedValue(undefined),
  searchStations: jest.fn().mockResolvedValue(undefined),
};

jest.mock('../../store/stationStore', () => ({
  useStationStore: () => mockState,
}));

jest.mock('../../components/StationCard', () => 'StationCard');
jest.mock('../../components/MapView', () => 'MapView');

describe('HomeScreen.ext4 — activeOrderId navigate branch', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockActiveOrderId = null;
  });

  it('navigates to Charging when activeOrderId is non-null', () => {
    mockActiveOrderId = 42;

    render(
      <SafeAreaProvider>
        <HomeScreen />
      </SafeAreaProvider>,
    );

    expect(mockNavigate).toHaveBeenCalledWith('Charging', { orderId: 42 });
  });

  it('does not navigate when activeOrderId is null', () => {
    mockActiveOrderId = null;

    render(
      <SafeAreaProvider>
        <HomeScreen />
      </SafeAreaProvider>,
    );

    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
