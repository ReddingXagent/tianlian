import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Alert, Linking } from 'react-native';
import StationDetailScreen from '../StationDetailScreen';

// --- mocks ---
const mockFetchStationDetail = jest.fn().mockResolvedValue(undefined);
const mockFetchChargers = jest.fn().mockResolvedValue(undefined);

jest.mock('../../store/stationStore', () => ({
  useStationStore: jest.fn(),
}));

const { useStationStore } = require('../../store/stationStore');

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { stationId: 1 } }),
  useNavigation: () => ({ navigate: jest.fn() }),
  useIsFocused: () => true,
}));

jest.mock('../../components/StationCard', () => 'StationCard');
jest.mock('../../components/MapView', () => 'MapView');

describe('StationDetailScreen.ext3 — handleNavigate branches', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    jest.spyOn(Linking, 'openURL').mockResolvedValue(undefined);
  });

  // L58 branch true: handleNavigate when selectedStation is null → early return (no Linking call)
  it('handleNavigate returns early without calling Linking when selectedStation is null', () => {
    useStationStore.mockReturnValue({
      selectedStation: null,
      chargers: [],
      loading: false,
      error: null,
      fetchStationDetail: mockFetchStationDetail,
      fetchChargers: mockFetchChargers,
    });

    const { getByText } = render(
      <SafeAreaProvider>
        <StationDetailScreen />
      </SafeAreaProvider>,
    );

    // Press navigate button — should not call Linking.openURL since selectedStation is null
    fireEvent.press(getByText('导航到这里'));

    expect(Linking.openURL).not.toHaveBeenCalled();
  });

  // L58 branch false + catch: Linking.openURL rejects → Alert
  it('shows alert when Linking.openURL fails', async () => {
    useStationStore.mockReturnValue({
      selectedStation: {
        id: 1, name: '测试充电站', address: '地址', status: 'online',
        latitude: 39.9, longitude: 116.4, pricePerKwh: 1.2, serviceFee: 0.8,
        totalConnectors: 10, availableConnectors: 5, chargingConnectors: 3,
        isOpen24h: true, rating: 4.5, createdAt: '2025-01-01T00:00:00Z',
        updatedAt: '2025-01-01T00:00:00Z',
      },
      chargers: [{
        id: 1, stationId: 1, name: '1号桩', code: 'CH-001',
        type: 'dc', status: 'idle', power: 120, pricePerKwh: 1.2, serviceFee: 0.8,
      }],
      loading: false,
      error: null,
      fetchStationDetail: mockFetchStationDetail,
      fetchChargers: mockFetchChargers,
    });

    jest.spyOn(Linking, 'openURL').mockRejectedValue(new Error('cannot open'));

    const { getByText } = render(
      <SafeAreaProvider>
        <StationDetailScreen />
      </SafeAreaProvider>,
    );

    fireEvent.press(getByText('导航到这里'));

    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith('提示', '无法打开地图应用');
    });
  });
});
