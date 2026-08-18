import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Alert } from 'react-native';
import ScanScreen from '../ScanScreen';
import { chargingApi } from '../../services/api';

// ─── Mocks (对齐 ScanScreen.ext4 模式) ───────────────────

const mockReplace = jest.fn();
const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate, replace: mockReplace }),
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

describe('ScanScreen.ext6 — L45 status undefined branch', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });

  // L45: handleStartCharging 正常 resolve 但返回 undefined(useScan hook 内
  // lastResult 竞态变空等防御路径) → if(status) false 分支, 不导航
  it('does not navigate when startCharging resolves undefined', async () => {
    mockStartCharging.mockResolvedValue(undefined);

    const { getByText } = await doLookup(mockCharger({ status: 'idle' }));

    fireEvent.press(getByText('开始充电'));

    await waitFor(() => {
      expect(mockStartCharging).toHaveBeenCalledWith(1);
    });
    // 等待 promise 微任务冲刷
    await waitFor(() => {
      expect(mockReplace).not.toHaveBeenCalled();
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
