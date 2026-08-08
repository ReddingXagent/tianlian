import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Alert } from 'react-native';
import ScanScreen from '../ScanScreen';
import { chargingApi } from '../../services/api';

// ─── Mocks (matching ScanScreen.ext.test.tsx pattern) ─────

const mockReplace = jest.fn();
const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({
    navigate: mockNavigate,
    replace: mockReplace,
  }),
}));

const mockStartCharging = jest.fn();
jest.mock('../../store/orderStore', () => ({
  useOrderStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ startCharging: mockStartCharging }),
}));

jest.mock('../../services/api', () => ({
  chargingApi: { scan: jest.fn() },
}));

jest.mock('../../components/StatusBadge', () => 'StatusBadge');

jest.mock('expo-camera', () => ({
  CameraView: () => null,
  useCameraPermissions: () => [
    { status: 'granted', granted: true, canAskAgain: true },
    () => Promise.resolve({ status: 'granted', granted: true, canAskAgain: true }),
  ],
}));

const mockCharger = (overrides: Partial<Record<string, any>> = {}) => ({
  id: 1,
  type: 'charger' as const,
  code: 'CH-001',
  name: '测试充电桩A',
  stationId: 1,
  stationName: '测试站点',
  power: 60,
  pricePerKwh: 1.2,
  serviceFee: 0.8,
  status: 'idle' as const,
  ...overrides,
});

const renderScreen = () =>
  render(
    <SafeAreaProvider>
      <ScanScreen />
    </SafeAreaProvider>,
  );

const doLookup = async (charger: ReturnType<typeof mockCharger>) => {
  (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockResolvedValue({
    code: 200, message: 'ok', data: charger,
  });
  const utils = renderScreen();
  fireEvent.changeText(utils.getByPlaceholderText('输入充电桩编码'), 'CH-001');
  fireEvent.press(utils.getByText('查询'));
  await waitFor(() => expect(utils.getByText('测试充电桩A')).toBeTruthy());
  return utils;
};

// ─── Tests ─────────────────────────────────────────────────

describe('ScanScreen.ext3 — final branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });

  // Line 75-76: handleStartCharging axios error with response.data.message
  it('shows axios error message on startCharging failure with response', async () => {
    mockStartCharging.mockRejectedValue({
      response: { data: { message: '设备故障' } },
    });

    const { getByText } = await doLookup(mockCharger({ status: 'idle' }));

    fireEvent.press(getByText('开始充电'));

    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith('启动失败', '设备故障');
    });
  });

  // Line 76-77: handleStartCharging axios error with response but no message → fallback
  it('shows fallback message when axios error response has no message', async () => {
    mockStartCharging.mockRejectedValue({ response: { data: {} } });

    const { getByText } = await doLookup(mockCharger({ status: 'idle' }));

    fireEvent.press(getByText('开始充电'));

    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith('启动失败', '启动充电失败');
    });
  });

  // Line 73: status !== idle renders "当前不可用" button text (UI branch coverage)
  it('renders unavailable button text when charger status is not idle', async () => {
    const { getByText } = await doLookup(mockCharger({ status: 'fault' }));

    expect(getByText('当前不可用')).toBeTruthy();
  });
});
