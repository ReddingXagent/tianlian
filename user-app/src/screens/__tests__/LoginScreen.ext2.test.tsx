import React from 'react';
import { render, fireEvent, act } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

// ── Mock auth store ──────────────────────────────────────────
const mockAuth = {
  loginByCode: jest.fn().mockResolvedValue(undefined),
  loginByPassword: jest.fn().mockResolvedValue(undefined),
};

jest.mock('../../store/authStore', () => ({
  useAuthStore: (selector: (s: typeof mockAuth) => unknown) => selector(mockAuth),
}));

jest.mock('../../services/api', () => ({
  __esModule: true,
  authApi: {
    sendCode: jest.fn(),
  },
}));

import LoginScreen from '../LoginScreen';
import * as ApiModule from '../../services/api';

const mockSendCode = (ApiModule as unknown as { authApi: { sendCode: jest.Mock } }).authApi.sendCode;

const renderLogin = () =>
  render(
    <SafeAreaProvider>
      <LoginScreen />
    </SafeAreaProvider>,
  );

describe('LoginScreen.ext2 — countdown zero branch (L35-36)', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    mockSendCode.mockResolvedValue({ code: 0, data: null, message: 'OK' });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('countdown reaches 0 and clears interval (prev<=1 branch, timerRef.current check)', async () => {
    const { getByText, getByPlaceholderText, queryByText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');

    await act(async () => {
      fireEvent.press(getByText('获取验证码'));
      await Promise.resolve();
    });

    // Countdown started at 60
    expect(getByText('60s')).toBeTruthy();

    // Fast-forward 60 seconds — each tick tests prev<=1 and clears interval
    await act(async () => {
      jest.advanceTimersByTime(60000);
    });

    // Countdown finished — button should show original text
    expect(queryByText(/s$/)).toBeNull();
    expect(getByText('获取验证码')).toBeTruthy();
  });
});
