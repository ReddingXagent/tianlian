import React from 'react';
import { render } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import StationDetailScreen from '../StationDetailScreen';

// --- mocks ---
const mockStation = {
  id: 1,
  name: '测试充电站',
  address: '北京市朝阳区xx路',
  status: 'online' as const,
  latitude: 39.9,
  longitude: 116.4,
  pricePerKwh: 1.2,
  serviceFee: 0.8,
  totalConnectors: 10,
  availableConnectors: 5,
  chargingConnectors: 3,
  isOpen24h: true,
  rating: 4.5,
  createdAt: '2025-01-01T00:00:00Z',
  updatedAt: '2025-01-01T00:00:00Z',
};

const mockChargers = [
  {
    id: 1,
    stationId: 1,
    name: '1号桩',
    code: 'CH-001',
    type: 'dc' as const,
    status: 'idle' as const,
    power: 120,
    pricePerKwh: 1.2,
    serviceFee: 0.8,
  },
  {
    id: 2,
    stationId: 1,
    name: '2号桩',
    code: 'CH-002',
    type: 'ac' as const,
    status: 'charging' as const,
    power: 7,
    pricePerKwh: 1.2,
    serviceFee: 0.8,
  },
];

const mockFetchStationDetail = jest.fn().mockResolvedValue(undefined);
const mockFetchChargers = jest.fn().mockResolvedValue(undefined);

jest.mock('../../store/stationStore', () => ({
  useStationStore: () => ({
    selectedStation: mockStation,
    chargers: mockChargers,
    loading: false,
    error: null,
    fetchStationDetail: mockFetchStationDetail,
    fetchChargers: mockFetchChargers,
  }),
}));

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { stationId: 1 } }),
  useNavigation: () => ({
    navigate: jest.fn(),
  }),
}));

jest.mock('../../components/StationCard', () => 'StationCard');
jest.mock('../../components/MapView', () => 'MapView');

describe('StationDetailScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const renderScreen = () =>
    render(
      <SafeAreaProvider>
        <StationDetailScreen />
      </SafeAreaProvider>
    );

  it('renders station name', () => {
    const { getByText } = renderScreen();
    expect(getByText('测试充电站')).toBeTruthy();
  });

  it('renders station address', () => {
    const { getByText } = renderScreen();
    expect(getByText('北京市朝阳区xx路')).toBeTruthy();
  });

  it('renders navigation button text', () => {
    const { getByText } = renderScreen();
    expect(getByText('导航到这里')).toBeTruthy();
  });

  it('renders 充电桩列表 section', () => {
    const { getByText } = renderScreen();
    expect(getByText('充电桩列表')).toBeTruthy();
  });

  it('renders charger names', () => {
    const { getByText } = renderScreen();
    expect(getByText('1号桩')).toBeTruthy();
    expect(getByText('2号桩')).toBeTruthy();
  });

  it('calls fetchStationDetail on mount', () => {
    renderScreen();
    expect(mockFetchStationDetail).toHaveBeenCalledWith(1);
  });

  it('calls fetchChargers on mount', () => {
    renderScreen();
    expect(mockFetchChargers).toHaveBeenCalledWith(1);
  });

  it('renders charger count from chargers array', () => {
    const { getByText } = renderScreen();
    expect(getByText('总枪数')).toBeTruthy();
  });
});
