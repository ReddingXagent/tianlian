import React from 'react';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Alert } from 'react-native';
import ScanScreen from '../ScanScreen';
import { chargingApi } from '../../services/api';

// ─── Mocks ────────────────────────────────────────────────

const mockReplace = jest.fn();
const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({
    navigate: mockNavigate,
    replace: mockReplace,
  }),
}));

// Shared mock startCharging so we can control resolved/rejected per test
const mockStartCharging = jest.fn();
jest.mock('../../store/orderStore', () => ({
  useOrderStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ startCharging: mockStartCharging }),
}));

jest.mock('../../services/api', () => ({
  chargingApi: { scan: jest.fn() },
}));

jest.mock('../../components/StatusBadge', () => 'StatusBadge');

// CameraScanner mock — capture onScan/onClose
const mockCameraProps: { current: Record<string, any> | null } = { current: null };
jest.mock('expo-camera', () => ({
  CameraView: (props: Record<string, any>) => {
    mockCameraProps.current = props;
    return null;
  },
  useCameraPermissions: () => [
    { status: 'granted', granted: true, canAskAgain: true },
    () => Promise.resolve({ status: 'granted', granted: true, canAskAgain: true }),
  ],
}));

// ─── Helpers ───────────────────────────────────────────────

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

// ─── Tests ─────────────────────────────────────────────────

describe('ScanScreen.ext — start charging flow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCameraProps.current = null;
  });

  it('starts charging on idle charger and navigates to Charging', async () => {
    const spy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    mockStartCharging.mockResolvedValue({ orderId: 42 });

    const { getByPlaceholderText, getByText } = renderScreen();
    (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockResolvedValue({
      code: 200, message: 'ok', data: mockCharger(),
    });

    fireEvent.changeText(getByPlaceholderText('输入充电桩编码'), 'CH-001');
    fireEvent.press(getByText('查询'));
    await waitFor(() => expect(getByText('测试充电桩A')).toBeTruthy());

    fireEvent.press(getByText('开始充电'));

    await waitFor(() => {
      expect(mockStartCharging).toHaveBeenCalledWith(1);
      expect(mockReplace).toHaveBeenCalledWith('Charging', { orderId: 42 });
    });
    spy.mockRestore();
  });

  it('shows Alert on axios error from startCharging', async () => {
    const spy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    mockStartCharging.mockRejectedValue({
      response: { data: { message: '设备故障' } },
    });

    const { getByPlaceholderText, getByText } = renderScreen();
    (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockResolvedValue({
      code: 200, message: 'ok', data: mockCharger(),
    });

    fireEvent.changeText(getByPlaceholderText('输入充电桩编码'), 'CH-001');
    fireEvent.press(getByText('查询'));
    await waitFor(() => expect(getByText('测试充电桩A')).toBeTruthy());

    fireEvent.press(getByText('开始充电'));

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith('启动失败', '设备故障');
    });
    spy.mockRestore();
  });

  it('shows Alert on network error from startCharging', async () => {
    const spy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    mockStartCharging.mockRejectedValue(new Error('Network Error'));

    const { getByPlaceholderText, getByText } = renderScreen();
    (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockResolvedValue({
      code: 200, message: 'ok', data: mockCharger(),
    });

    fireEvent.changeText(getByPlaceholderText('输入充电桩编码'), 'CH-001');
    fireEvent.press(getByText('查询'));
    await waitFor(() => expect(getByText('测试充电桩A')).toBeTruthy());

    fireEvent.press(getByText('开始充电'));

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith('启动失败', '网络错误，请检查网络连接');
    });
    spy.mockRestore();
  });

  it('shows "当前不可用" button text when charger status is not idle', async () => {
    const spy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    const { getByPlaceholderText, getByText } = renderScreen();
    (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockResolvedValue({
      code: 200, message: 'ok', data: mockCharger({ status: 'charging' as const }),
    });

    fireEvent.changeText(getByPlaceholderText('输入充电桩编码'), 'CH-001');
    fireEvent.press(getByText('查询'));

    await waitFor(() => expect(getByText('当前不可用')).toBeTruthy());
    expect(mockStartCharging).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});

describe('ScanScreen.ext — error branches', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows network error message on non-axios error', async () => {
    const { getByPlaceholderText, getByText } = renderScreen();
    (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockRejectedValue(
      new Error('Network Error'),
    );

    fireEvent.changeText(getByPlaceholderText('输入充电桩编码'), 'CH-500');
    fireEvent.press(getByText('查询'));

    await waitFor(() => {
      expect(getByText('网络错误，请检查网络连接')).toBeTruthy();
    });
  });

  it('shows default error when axios error has no message', async () => {
    const { getByPlaceholderText, getByText } = renderScreen();
    (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockRejectedValue({
      response: {},
    });

    fireEvent.changeText(getByPlaceholderText('输入充电桩编码'), 'CH-404');
    fireEvent.press(getByText('查询'));

    await waitFor(() => {
      expect(getByText('未找到匹配的充电桩')).toBeTruthy();
    });
  });
});

describe('ScanScreen.ext — quick input buttons', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('quick input sets code and clears error', async () => {
    const { getByText, getByPlaceholderText, queryByText } = renderScreen();
    (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockRejectedValue({
      response: { data: { message: '充电桩不存在' } },
    });

    // Trigger error first
    fireEvent.changeText(getByPlaceholderText('输入充电桩编码'), 'BAD');
    fireEvent.press(getByText('查询'));
    await waitFor(() => expect(getByText('充电桩不存在')).toBeTruthy());

    // Quick input should clear the error
    fireEvent.press(getByText('CH-002'));
    expect(getByPlaceholderText('输入充电桩编码').props.value).toBe('CH-002');
    expect(queryByText('充电桩不存在')).toBeNull();
  });
});

describe('ScanScreen.ext — result rendering', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders charger details: name, station, power, code, price', async () => {
    const { getByText, getByPlaceholderText } = renderScreen();
    (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockResolvedValue({
      code: 200, message: 'ok', data: mockCharger({
        name: '超级快充桩',
        stationName: '东方明珠站',
        power: 120,
        code: 'CH-999',
        pricePerKwh: 1.5,
        serviceFee: 0.5,
      }),
    });

    fireEvent.changeText(getByPlaceholderText('输入充电桩编码'), 'CH-999');
    fireEvent.press(getByText('查询'));

    await waitFor(() => {
      expect(getByText('超级快充桩')).toBeTruthy();
      expect(getByText('东方明珠站')).toBeTruthy();
      expect(getByText('功率: 120kW')).toBeTruthy();
      expect(getByText('编码: CH-999')).toBeTruthy();
    });
  });

  it('shows loading indicator on query button when loading', async () => {
    const { getByText, queryByText, getByPlaceholderText } = renderScreen();
    // Never resolve to keep loading state
    (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockReturnValue(
      new Promise(() => {}),
    );

    fireEvent.changeText(getByPlaceholderText('输入充电桩编码'), 'CH-001');
    fireEvent.press(getByText('查询'));

    await waitFor(() => {
      expect(queryByText('查询')).toBeNull();
    });
  });
});

describe('ScanScreen.ext — camera scan flow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCameraProps.current = null;
  });

  it('camera scan triggers lookup and closes camera', async () => {
    const { getByTestId, queryByTestId, getByText } = renderScreen();
    (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockResolvedValue({
      code: 200, message: 'ok', data: mockCharger({ code: 'CH-007', name: '相机扫到的桩' }),
    });

    fireEvent.press(getByTestId('open-camera-btn'));
    expect(getByTestId('camera-view')).toBeTruthy();

    act(() => {
      mockCameraProps.current?.onBarcodeScanned({ data: 'CH-007' });
    });

    await waitFor(() => {
      expect(chargingApi.scan).toHaveBeenCalledWith('CH-007');
    });
    await waitFor(() => {
      expect(queryByTestId('camera-view')).toBeNull();
      expect(getByText('相机扫到的桩')).toBeTruthy();
    });
  });

  it('camera scan network error shows error message', async () => {
    const { getByTestId, getByText } = renderScreen();
    (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockRejectedValue(
      new Error('Network Error'),
    );

    fireEvent.press(getByTestId('open-camera-btn'));
    act(() => {
      mockCameraProps.current?.onBarcodeScanned({ data: 'CH-NET' });
    });

    await waitFor(() => {
      expect(getByText('网络错误，请检查网络连接')).toBeTruthy();
    });
  });
});

describe('ScanScreen.ext — text input clears error', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('typing in input clears previous error', async () => {
    const { getByText, getByPlaceholderText, queryByText } = renderScreen();
    (chargingApi.scan as jest.MockedFunction<typeof chargingApi.scan>).mockRejectedValue({
      response: { data: { message: '充电桩不存在' } },
    });

    // Trigger error
    fireEvent.changeText(getByPlaceholderText('输入充电桩编码'), 'BAD');
    fireEvent.press(getByText('查询'));
    await waitFor(() => expect(getByText('充电桩不存在')).toBeTruthy());

    // Typing should clear error
    fireEvent.changeText(getByPlaceholderText('输入充电桩编码'), 'CH-');
    expect(queryByText('充电桩不存在')).toBeNull();
  });
});
