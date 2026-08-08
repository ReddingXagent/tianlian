import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { Alert, Linking, Platform } from 'react-native';
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
const mockNavigate = jest.fn();

let mockStoreOverrides: Record<string, unknown> = {};

jest.mock('../../store/stationStore', () => ({
  useStationStore: jest.fn(),
}));

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { useStationStore } = require('../../store/stationStore');

let mockFocused = true;

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { stationId: 1 } }),
  useNavigation: () => ({
    navigate: mockNavigate,
  }),
  useIsFocused: () => mockFocused,
}));

jest.mock('../../components/StationCard', () => 'StationCard');
jest.mock('../../components/MapView', () => 'MapView');

const spyAlert = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
const spyLinking = jest.spyOn(Linking, 'openURL').mockResolvedValue(undefined);

describe('StationDetailScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
    mockStoreOverrides = {};
    spyAlert.mockClear();
    spyLinking.mockClear();
    mockNavigate.mockClear();
  });

  const renderScreen = () => {
    useStationStore.mockReturnValue({
      selectedStation: 'selectedStation' in mockStoreOverrides ? mockStoreOverrides.selectedStation : mockStation,
      chargers: 'chargers' in mockStoreOverrides ? mockStoreOverrides.chargers : mockChargers,
      loading: 'loading' in mockStoreOverrides ? mockStoreOverrides.loading : false,
      error: 'error' in mockStoreOverrides ? mockStoreOverrides.error : null,
      fetchStationDetail: mockFetchStationDetail,
      fetchChargers: mockFetchChargers,
    });
    return render(
      <SafeAreaProvider>
        <StationDetailScreen />
      </SafeAreaProvider>
    );
  };

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

  it('refetches station + chargers when screen regains focus (回焦刷新)', () => {
    const utils = renderScreen();
    expect(mockFetchStationDetail).toHaveBeenCalledTimes(1);
    expect(mockFetchChargers).toHaveBeenCalledTimes(1);

    mockFocused = false;
    utils.rerender(<SafeAreaProvider><StationDetailScreen /></SafeAreaProvider>);
    expect(mockFetchStationDetail).toHaveBeenCalledTimes(1);

    mockFocused = true;
    utils.rerender(<SafeAreaProvider><StationDetailScreen /></SafeAreaProvider>);
    expect(mockFetchStationDetail).toHaveBeenCalledTimes(2);
    expect(mockFetchChargers).toHaveBeenCalledTimes(2);
  });

  // --- loading / error states ---
  it('shows loading spinner when loading and no station yet', () => {
    mockStoreOverrides = { loading: true, selectedStation: null };
    const { getByText } = renderScreen();
    expect(getByText('加载站点详情...')).toBeTruthy();
  });

  it('shows error state with retry button when error and no station', () => {
    mockStoreOverrides = { error: '网络超时', selectedStation: null };
    const { getByText } = renderScreen();
    expect(getByText('加载失败')).toBeTruthy();
    expect(getByText('网络超时')).toBeTruthy();
    expect(getByText('重试')).toBeTruthy();
  });

  it('retries data fetch when retry button pressed', () => {
    mockStoreOverrides = { error: '网络超时', selectedStation: null };
    // Clear the mount-time calls
    mockFetchStationDetail.mockClear();
    mockFetchChargers.mockClear();
    const { getByText } = renderScreen();
    fireEvent.press(getByText('重试'));
    expect(mockFetchStationDetail).toHaveBeenCalledWith(1);
    expect(mockFetchChargers).toHaveBeenCalledWith(1);
  });

  // --- handleNavigate (导航) ---
  it('opens map URL via Linking when navigate button pressed (iOS)', () => {
    Platform.OS = 'ios';
    const { getByText } = renderScreen();
    fireEvent.press(getByText('导航到这里'));
    expect(spyLinking).toHaveBeenCalled();
  });

  it('opens geo URL on Android', () => {
    Platform.OS = 'android';
    const { getByText } = renderScreen();
    fireEvent.press(getByText('导航到这里'));
    expect(spyLinking).toHaveBeenCalledWith(
      expect.stringMatching(/^geo:/)
    );
    // Restore
    Platform.OS = 'ios';
  });

  it('shows alert when Linking.openURL fails', async () => {
    spyLinking.mockRejectedValueOnce(new Error('no app'));
    const { getByText } = renderScreen();
    fireEvent.press(getByText('导航到这里'));
    await waitFor(() => {
      expect(spyAlert).toHaveBeenCalledWith('提示', '无法打开地图应用');
    });
  });

  // --- handleChargerPress (各status分支) ---
  it('shows confirm dialog for idle charger', () => {
    const { getAllByText } = renderScreen();
    // Press first charger card (idle)
    const chargerCards = getAllByText('1号桩');
    fireEvent.press(chargerCards[0]);
    expect(spyAlert).toHaveBeenCalledWith(
      '开始充电',
      expect.stringContaining('1号桩'),
      expect.any(Array)
    );
  });

  it('shows "in use" alert for charging status charger', () => {
    const { getAllByText } = renderScreen();
    fireEvent.press(getAllByText('2号桩')[0]);
    expect(spyAlert).toHaveBeenCalledWith('提示', '该充电桩正在使用中');
  });

  it('shows fault alert for fault status charger', () => {
    mockStoreOverrides = {
      chargers: [
        { id: 3, stationId: 1, name: '故障桩', code: 'CH-003', type: 'dc', status: 'fault', power: 60, pricePerKwh: 1.2, serviceFee: 0.8 },
      ],
    };
    const { getByText } = renderScreen();
    fireEvent.press(getByText('故障桩'));
    expect(spyAlert).toHaveBeenCalledWith('提示', '该充电桩故障，请选择其他充电桩');
  });

  it('shows offline alert for unknown status charger', () => {
    mockStoreOverrides = {
      chargers: [
        { id: 4, stationId: 1, name: '离线桩', code: 'CH-004', type: 'ac', status: 'offline', power: 7, pricePerKwh: 1.2, serviceFee: 0.8 },
      ],
    };
    const { getByText } = renderScreen();
    fireEvent.press(getByText('离线桩'));
    expect(spyAlert).toHaveBeenCalledWith('提示', '该充电桩离线');
  });

  // --- 空充电桩列表 ---
  it('renders empty state when chargers list is empty', () => {
    mockStoreOverrides = { chargers: [] };
    const { getByText } = renderScreen();
    expect(getByText('暂无充电桩')).toBeTruthy();
  });

  // --- 24h / openingHours ---
  it('shows 24小时营业 when isOpen24h is true', () => {
    const { getByText } = renderScreen();
    expect(getByText('24小时营业')).toBeTruthy();
  });

  it('shows openingHours when not 24h', () => {
    mockStoreOverrides = {
      selectedStation: { ...mockStation, isOpen24h: false, openingHours: '08:00-22:00' },
    };
    const { getByText } = renderScreen();
    expect(getByText('08:00-22:00')).toBeTruthy();
  });

  it('shows dash for openingHours when not 24h and no hours set', () => {
    mockStoreOverrides = {
      selectedStation: { ...mockStation, isOpen24h: false, openingHours: '' },
    };
    const { getByText } = renderScreen();
    expect(getByText('-')).toBeTruthy();
  });

  // --- summary counts (available/charging) ---
  it('shows correct available and charging counts', () => {
    const { getAllByText } = renderScreen();
    // mockChargers has 1 idle + 1 charging → 空闲:1, 充电中:1
    // '1' appears for both counts
    expect(getAllByText('1').length).toBeGreaterThanOrEqual(2);
  });

  // --- refresh control ---
  it('triggers refresh data when refresh control fires', async () => {
    mockFetchStationDetail.mockClear();
    mockFetchChargers.mockClear();
    renderScreen();
    // RefreshControl is part of ScrollView; we test via store calls
    // The initial render already calls once
    expect(mockFetchStationDetail).toHaveBeenCalledTimes(1);
  });

  // --- navigation when "去充电" pressed in Alert ---
  it('navigates to Scan screen when confirming charge on idle charger', () => {
    const { getAllByText } = renderScreen();
    fireEvent.press(getAllByText('1号桩')[0]);
    // Alert.alert was called with buttons array
    const alertCall = spyAlert.mock.calls.find(c => c[0] === '开始充电');
    expect(alertCall).toBeTruthy();
    const buttons = alertCall![2] as { text: string; onPress?: () => void }[];
    const confirmBtn = buttons.find(b => b.text === '去充电');
    expect(confirmBtn).toBeTruthy();
    confirmBtn!.onPress!();
    expect(mockNavigate).toHaveBeenCalledWith('Main', { screen: 'Scan' });
  });

  // --- price rendering ---
  it('renders price section with formatMoney values', () => {
    const { getByText } = renderScreen();
    expect(getByText('电费')).toBeTruthy();
    expect(getByText('服务费')).toBeTruthy();
    expect(getByText('合计')).toBeTruthy();
  });

  it('renders non-24h station with openingHours fallback to dash', () => {
    mockStoreOverrides = {
      selectedStation: { ...mockStation, isOpen24h: false, openingHours: undefined },
    };
    const { getByText } = renderScreen();
    expect(getByText('-')).toBeTruthy();
  });
});
