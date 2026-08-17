import React from 'react';
import { render, waitFor, fireEvent, act } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Alert } from 'react-native';
import ChargingScreen from '../ChargingScreen';

// Mock navigation
const mockReplace = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ replace: mockReplace }),
  useRoute: () => ({ params: { orderId: 42 } }),
}));

// Mock API
jest.mock('../../services/api', () => {
  const getStatus = jest.fn();
  return { chargingApi: { getStatus } };
});

// Mock order store with controllable stopCharging
const mockStopCharging = jest.fn();
jest.mock('../../store/orderStore', () => ({
  useOrderStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ stopCharging: mockStopCharging }),
}));

// Mock useAppLifecycle to control paused/foreground state
let mockIsForeground = true;
let mockIsConnected: boolean | null = true;
jest.mock('../../hooks/useAppLifecycle', () => ({
  useAppLifecycle: () => ({
    appState: mockIsForeground ? 'active' : 'background',
    isForeground: mockIsForeground,
    isConnected: mockIsConnected,
  }),
}));

// Spy on Alert.alert to intercept callbacks
const alertSpy = jest.spyOn(Alert, 'alert');

const mockChargingData = {
  orderId: 42, orderNo: 'ORD-001', chargerName: '充电桩A', stationName: '测试站',
  status: 'charging', power: 30.5, voltage: 400.2, current: 76.1,
  energy: 5.32, duration: 10.5, amount: 6.38, startTime: '2026-08-03T10:00:00Z',
};

describe('ChargingScreen.ext — branch coverage to 100%', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    mockIsForeground = true;
    mockIsConnected = true;
    alertSpy.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  const renderScreen = () =>
    render(<SafeAreaProvider><ChargingScreen /></SafeAreaProvider>);

  // ── handleStop: cancel button ──
  it('handleStop cancel does nothing', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockReturnValue(new Promise((resolve) => {
      resolve({ data: mockChargingData });
    }));
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('停止充电')).toBeTruthy(), { timeout: 3000 });

    fireEvent.press(getByText('停止充电'));
    expect(alertSpy).toHaveBeenCalledWith(
      '停止充电',
      '确定要停止当前充电吗？',
      expect.arrayContaining([
        expect.objectContaining({ text: '取消', style: 'cancel' }),
        expect.objectContaining({ text: '停止', style: 'destructive' }),
      ])
    );

    // Press cancel
    const cancelAction = alertSpy.mock.calls[0][2]?.[0];
    cancelAction?.onPress?.();
    // No navigation or stopCharging called
    expect(mockStopCharging).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  // ── handleStop: success flow ──
  it('handleStop success navigates to payment', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    mockStopCharging.mockResolvedValue(undefined);
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('停止充电')).toBeTruthy());

    fireEvent.press(getByText('停止充电'));
    const stopAction = alertSpy.mock.calls[0][2]?.[1];

    await act(async () => {
      await stopAction?.onPress?.();
    });

    expect(mockStopCharging).toHaveBeenCalledWith(42);
    expect(mockReplace).toHaveBeenCalledWith('Payment', { orderId: 42, amount: 6.38 });
  });

  // ── handleStop: failure shows error alert ──
  it('handleStop failure shows error alert', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    mockStopCharging.mockRejectedValue(new Error('server error'));
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('停止充电')).toBeTruthy());

    fireEvent.press(getByText('停止充电'));
    const stopAction = alertSpy.mock.calls[0][2]?.[1];

    await act(async () => {
      await stopAction?.onPress?.();
    });

    expect(mockStopCharging).toHaveBeenCalledWith(42);
    // Error Alert.alert('操作失败', ...)
    expect(alertSpy).toHaveBeenCalledWith('操作失败', '停止充电失败，请重试');
  });

  // ── stopping state shows ActivityIndicator on button ──
  it('shows spinner on stop button while stopping', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    // Hold the stopCharging promise so stopping=true persists
    mockStopCharging.mockReturnValue(new Promise(() => {}));
    const { getByText, queryByText } = renderScreen();
    await waitFor(() => expect(getByText('停止充电')).toBeTruthy());

    fireEvent.press(getByText('停止充电'));
    const stopAction = alertSpy.mock.calls[0][2]?.[1];

    await act(async () => {
      stopAction?.onPress?.();
    });

    // Button text hidden (replaced by ActivityIndicator), stop button text gone
    await waitFor(() => {
      expect(queryByText('停止充电')).toBeNull();
    });
  });

  // ── paused hint: foreground=false ──
  it('shows paused hint when app goes to background', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    const { getByText, rerender } = renderScreen();
    await waitFor(() => expect(getByText('30.5')).toBeTruthy());

    // Simulate going to background
    mockIsForeground = false;
    rerender(<SafeAreaProvider><ChargingScreen /></SafeAreaProvider>);

    await waitFor(() => {
      expect(getByText(/实时刷新已暂停/)).toBeTruthy();
    });
  });

  // ── paused hint: disconnected ──
  it('shows paused hint when network disconnects', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    const { getByText, rerender } = renderScreen();
    await waitFor(() => expect(getByText('30.5')).toBeTruthy());

    // Simulate disconnect
    mockIsConnected = false;
    rerender(<SafeAreaProvider><ChargingScreen /></SafeAreaProvider>);

    await waitFor(() => {
      expect(getByText(/实时刷新已暂停/)).toBeTruthy();
    });
  });

  // ── renders voltage and current ──
  it('displays voltage and current values', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('400.2 V')).toBeTruthy();
      expect(getByText('76.1 A')).toBeTruthy();
    });
  });

  // ── renders amount with ¥ ──
  it('displays amount with yuan sign', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText(/¥6\.38/)).toBeTruthy();
    });
  });

  // ── duration formatting: whole minutes ──
  it('formats duration with 0 seconds correctly', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({
      data: { ...mockChargingData, duration: 5.0 },
    });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText(/5分0秒/)).toBeTruthy();
    });
  });

  // ── duration formatting: fractional seconds ──
  it('formats duration with fractional seconds', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({
      data: { ...mockChargingData, duration: 3.25 },
    });
    const { getByText } = renderScreen();
    await waitFor(() => {
      // 3.25 min → 3分15秒 (0.25*60=15)
      expect(getByText(/3分15秒/)).toBeTruthy();
    });
  });

  // ── energy formatting ──
  it('displays formatted energy', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({
      data: { ...mockChargingData, energy: 12.345 },
    });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText(/12\.35.*kWh/)).toBeTruthy();
    });
  });

  // ── error + !loading shows error screen with retry button ──
  it('shows error and retry when initial load fails', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockRejectedValue(new Error('timeout'));
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('timeout')).toBeTruthy();
      expect(getByText('重试')).toBeTruthy();
    });
  });

  // ── retry button triggers refetch ──
  it('retry button refetches and renders data', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockRejectedValueOnce(new Error('fail'));
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('重试')).toBeTruthy());

    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    fireEvent.press(getByText('重试'));
    await waitFor(() => expect(getByText('30.5')).toBeTruthy());
  });

  // ── onStatusChange callback fires ──
  it('calls onStatusChange when data arrives (internal hook)', async () => {
    // onStatusChange is internal to the hook; we verify data renders which means the callback chain works
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('测试站')).toBeTruthy());
  });

  // ── error hint shows alongside data after successful first fetch ──
  it('shows error hint but keeps data after transient polling failure', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus
      .mockResolvedValueOnce({ data: mockChargingData })
      .mockRejectedValue(new Error('flaky'));
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('30.5')).toBeTruthy());

    await act(async () => {
      jest.advanceTimersByTime(3000);
    });
    await waitFor(() => {
      expect(getByText(/刷新失败/)).toBeTruthy();
      expect(getByText('30.5')).toBeTruthy();
    });
  });

  // ── isConnected=null does not pause (treated as unknown, not offline) ──
  it('does not pause when isConnected is null (unknown)', async () => {
    const { chargingApi } = require('../../services/api');
    chargingApi.getStatus.mockResolvedValue({ data: mockChargingData });
    mockIsConnected = null;
    const { getByText, queryByText } = renderScreen();
    await waitFor(() => expect(getByText('30.5')).toBeTruthy());
    // Should NOT show paused hint since null=unknown, not offline
    expect(queryByText(/实时刷新已暂停/)).toBeNull();
  });
});
