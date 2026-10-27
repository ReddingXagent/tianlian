import React from 'react';
import { Alert } from 'react-native';
import { render, waitFor, act, fireEvent } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import WalletScreen from '../WalletScreen';

const mockGetRecords = jest.fn();
const mockRecharge = jest.fn();
const mockGetProfile = jest.fn();
const mockAlertAlert = jest.spyOn(Alert, 'alert').mockImplementation(() => {});

jest.mock('../../services/api', () => ({
  walletApi: {
    getRecords: (...args: unknown[]) => mockGetRecords(...args),
    recharge: (...args: unknown[]) => mockRecharge(...args),
  },
  authApi: {
    getProfile: (...args: unknown[]) => mockGetProfile(...args),
  },
}));

const mockSetUser = jest.fn();

jest.mock('../../store/authStore', () => ({
  useAuthStore: () => ({
    user: { id: 1, phone: '138', nickname: 'u', balance: 150 },
    setUser: mockSetUser,
  }),
}));

let mockFocused = true;
jest.mock('@react-navigation/native', () => ({
  useIsFocused: () => mockFocused,
}));

type AlertButton = { text: string; onPress: () => void };

describe('WalletScreen ext3 — recharging=true render branch (L163)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
    mockAlertAlert.mockClear();
    mockGetProfile.mockResolvedValue({ data: { id: 1, balance: 200 } });
    mockGetRecords.mockResolvedValue({
      data: { items: [], page: 1, total: 0 },
    });
  });

  it('shows "充值中..." and disables button during recharge', async () => {
    // Make recharge slow so recharging=true is rendered.
    // 用受控 pending promise 挂起而非裸 setTimeout(5000):
    // 裸真实定时器会在测试环境拆除后仍触发 → teardown 后 Alert.alert
    // → "worker process failed to exit gracefully"(F1198 实证根因)。
    let resolveRecharge!: () => void;
    mockRecharge.mockImplementation(
      () => new Promise<void>(r => { resolveRecharge = r; })
    );
    mockGetProfile.mockResolvedValue({ data: { id: 1, balance: 210 } });

    const { getByText, queryByText } = render(
      <SafeAreaProvider><WalletScreen /></SafeAreaProvider>
    );

    await waitFor(() => expect(getByText('充值')).toBeTruthy());

    // Press recharge button
    fireEvent.press(getByText('充值'));

    // Alert shown with amount options
    const callArgs = mockAlertAlert.mock.calls[0];
    const buttons = callArgs[2] as AlertButton[];
    const tenBtn = buttons.find((b) => b.text === '¥10')!;

    mockAlertAlert.mockClear();

    // Start recharge (won't complete until we resolve it)
    act(() => {
      tenBtn.onPress();
    });

    // During recharge: button shows "充值中..." and is disabled
    await waitFor(() => {
      expect(getByText('充值中...')).toBeTruthy();
    });
    expect(queryByText('充值')).toBeNull();

    // 清理: 显式 resolve 挂起的 recharge 并 flush 后续异步链
    // (getProfile → setUser/loadRecords → Alert), 避免句柄逃逸到 teardown 后
    await act(async () => {
      resolveRecharge();
      await Promise.resolve();
    });
    await act(async () => {
      await Promise.resolve();
    });
  });
});
