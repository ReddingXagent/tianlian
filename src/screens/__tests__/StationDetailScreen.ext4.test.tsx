import React from 'react';
import { render, act } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import StationDetailScreen from '../StationDetailScreen';

const mockFetchStationDetail = jest.fn().mockReturnValue(new Promise(() => {}));
const mockFetchChargers = jest.fn().mockReturnValue(new Promise(() => {}));

jest.mock('../../store/stationStore', () => ({
  useStationStore: jest.fn(),
}));

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { useStationStore } = require('../../store/stationStore');

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { stationId: 1 } }),
  useNavigation: () => ({ navigate: jest.fn() }),
  useIsFocused: () => true,
}));

jest.mock('../../components/StationCard', () => 'StationCard');
jest.mock('../../components/MapView', () => 'MapView');

describe('StationDetailScreen.ext4 — 卸载竞态分支', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useStationStore.mockReturnValue({
      selectedStation: null,
      chargers: [],
      loading: true,
      error: null,
      fetchStationDetail: mockFetchStationDetail,
      fetchChargers: mockFetchChargers,
    });
  });

  it('cancels pending loadData when unmounted before microtask flush', async () => {
    const view = render(
      <SafeAreaProvider>
        <StationDetailScreen />
      </SafeAreaProvider>
    );
    view.unmount();
    await act(async () => {});
    // 卸载先于微任务冲刷 → cancelled=true, 不应发起详情/充电桩请求
    expect(mockFetchStationDetail).not.toHaveBeenCalled();
    expect(mockFetchChargers).not.toHaveBeenCalled();
  });
});
