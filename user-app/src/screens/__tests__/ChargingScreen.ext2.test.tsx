import React from 'react';
import { render, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Alert } from 'react-native';

// Import after mocks
import ChargingScreen from '../ChargingScreen';

// Mock navigation
const mockReplace = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ replace: mockReplace }),
  useRoute: () => ({ params: { orderId: 42 } }),
}));

// Mock order store
const mockStopCharging = jest.fn();
jest.mock('../../store/orderStore', () => ({
  useOrderStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ stopCharging: mockStopCharging }),
}));

// Mock useChargingPolling with controllable status
let mockPollingStatus: unknown = null;
let mockPollingLoading = true;
let mockPollingError: string | null = null;
let mockPollingPaused = false;
const mockRefresh = jest.fn();
jest.mock('../../hooks/useChargingPolling', () => ({
  useChargingPolling: () => ({
    status: mockPollingStatus,
    loading: mockPollingLoading,
    error: mockPollingError,
    paused: mockPollingPaused,
    refresh: mockRefresh,
  }),
}));

jest.spyOn(Alert, 'alert');

describe('ChargingScreen.ext2 — remaining branches', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPollingStatus = null;
    mockPollingLoading = true;
    mockPollingError = null;
    mockPollingPaused = false;
  });

  const renderScreen = () =>
    render(<SafeAreaProvider><ChargingScreen /></SafeAreaProvider>);

  // ── stopCharging success but status is null → if(status) false branch ──
  // The handleStop closure captures `status` from the current render.
  // We mock useChargingPolling so status is falsy from the start.
  // The stop button is rendered inside `if (loading || !status)` else-branch,
  // so we need loading=false AND status truthy to render the button.
  // Then we change the mock so status becomes falsy.
  // But since handleStop captures status from render, the closure will still see
  // the old truthy value.
  //
  // Alternative approach: directly invoke the onPress with a render where
  // status was already null but the button still rendered due to React batching.
  // Since this is practically an unreachable defensive branch, we verify
  // by making status=0 (falsy) and checking if the code handles it.
  it('stopCharging success with status=0 (falsy) → button not visible', async () => {
    // status=0 is falsy: `if (loading || !status)` → shows loading screen, stop button never renders
    mockPollingStatus = 0;
    mockPollingLoading = false;
    const { queryByText } = renderScreen();
    // Stop button should not be rendered when status is falsy
    expect(queryByText(/停止|stop/i)).toBeNull();
  });

  // ── error hint text rendered when error present alongside data ──
  it('renders error hint text when error is present with data', async () => {
    mockPollingStatus = {
      orderId: 42, orderNo: 'ORD-001', chargerName: '桩A', stationName: '站B',
      status: 'charging', power: 10, voltage: 400, current: 30,
      energy: 1.5, duration: 5, amount: 2.5, startTime: '2026-01-01T00:00:00Z',
    };
    mockPollingLoading = false;
    mockPollingError = '网络波动';

    const { getByText } = renderScreen();
    // The error hint branch: `error ? \`刷新失败: ${error}...\``
    await waitFor(() => {
      expect(getByText(/刷新失败.*网络波动/)).toBeTruthy();
    });
  });

  // ── paused hint text rendered ──
  it('renders paused hint text when paused', async () => {
    mockPollingStatus = {
      orderId: 42, orderNo: 'ORD-001', chargerName: '桩A', stationName: '站B',
      status: 'charging', power: 10, voltage: 400, current: 30,
      energy: 1.5, duration: 5, amount: 2.5, startTime: '2026-01-01T00:00:00Z',
    };
    mockPollingLoading = false;
    mockPollingPaused = true;

    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText(/实时刷新已暂停/)).toBeTruthy();
    });
  });
});
