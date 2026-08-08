import React from 'react';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

// ── Mock auth store ──────────────────────────────────────────
const mockAuth = {
  loginByCode: jest.fn().mockResolvedValue(undefined),
  loginByPassword: jest.fn().mockResolvedValue(undefined),
};

jest.mock('../../store/authStore', () => ({
  useAuthStore: (selector: (s: typeof mockAuth) => unknown) => selector(mockAuth),
}));

// ── Mock api: jest.mock is hoisted by babel, factory must be self-contained ──
jest.mock('../../services/api', () => ({
  __esModule: true,
  authApi: {
    sendCode: jest.fn(),
  },
}));

// jest.mock calls are hoisted above imports by babel — safe to import below
// eslint-disable-next-line import/first
import LoginScreen from '../LoginScreen';
// eslint-disable-next-line import/first
import * as ApiModule from '../../services/api';

const mockSendCode = (ApiModule as unknown as { authApi: { sendCode: jest.Mock } }).authApi.sendCode;

const renderLogin = () =>
  render(
    <SafeAreaProvider>
      <LoginScreen />
    </SafeAreaProvider>,
  );

const flush = () => new Promise<void>((r) => setTimeout(r, 50));

describe('LoginScreen.ext — full branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAuth.loginByCode.mockResolvedValue(undefined);
    mockAuth.loginByPassword.mockResolvedValue(undefined);
    mockSendCode.mockResolvedValue({ code: 0, data: null, message: 'OK' });
  });

  // ── handleSendCode: empty phone ───────────────────────────
  it('shows error when phone is empty on send code', () => {
    const { getByText } = renderLogin();
    fireEvent.press(getByText('获取验证码'));
    expect(getByText('请输入正确的手机号')).toBeTruthy();
    expect(mockSendCode).not.toHaveBeenCalled();
  });

  // ── handleSendCode: whitespace phone ──────────────────────
  it('shows error when phone is whitespace only', () => {
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '   ');
    fireEvent.press(getByText('获取验证码'));
    expect(getByText('请输入正确的手机号')).toBeTruthy();
  });

  // ── handleSendCode: short phone ───────────────────────────
  it('shows error when phone is too short', () => {
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '12345');
    fireEvent.press(getByText('获取验证码'));
    expect(getByText('请输入正确的手机号')).toBeTruthy();
  });

  // ── handleSendCode: success → countdown starts ────────────
  it('sends code successfully and starts countdown', async () => {
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');

    await act(async () => {
      fireEvent.press(getByText('获取验证码'));
      await flush();
    });

    expect(mockSendCode).toHaveBeenCalledWith({ phone: '13800138000' });
    expect(getByText('60s')).toBeTruthy();
  });

  // ── handleSendCode: shows spinner while sending ───────────
  it('shows activity indicator while sending code', async () => {
    mockSendCode.mockReturnValue(new Promise(() => {}));
    const { getByText, getByPlaceholderText, queryByText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');

    act(() => {
      fireEvent.press(getByText('获取验证码'));
    });

    expect(queryByText('获取验证码')).toBeNull();
  });

  // ── handleSendCode: axios error with message ──────────────
  it('shows axios error message on send code failure', async () => {
    mockSendCode.mockRejectedValueOnce({
      response: { data: { message: '该手机号未注册' } },
    });
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');

    await act(async () => {
      fireEvent.press(getByText('获取验证码'));
      await flush();
    });

    await waitFor(() => {
      expect(getByText('该手机号未注册')).toBeTruthy();
    });
  });

  // ── handleSendCode: axios error without message ───────────
  it('shows fallback when axios error has no message', async () => {
    mockSendCode.mockRejectedValueOnce({ response: { data: {} } });
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');

    await act(async () => {
      fireEvent.press(getByText('获取验证码'));
      await flush();
    });

    await waitFor(() => {
      expect(getByText('发送验证码失败')).toBeTruthy();
    });
  });

  // ── handleSendCode: network error ─────────────────────────
  it('shows network error on non-axios send code error', async () => {
    mockSendCode.mockRejectedValueOnce(new Error('timeout'));
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');

    await act(async () => {
      fireEvent.press(getByText('获取验证码'));
      await flush();
    });

    await waitFor(() => {
      expect(getByText('网络错误，请检查网络连接')).toBeTruthy();
    });
  });

  // ── countdown: decrements and resets ──────────────────────
  it('decrements countdown and resets', async () => {
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');

    // Send code and start countdown (use real timers + real flush)
    await act(async () => {
      fireEvent.press(getByText('获取验证码'));
      await flush();
    });

    expect(getByText('60s')).toBeTruthy();

    // Wait 1 second for countdown to tick
    await act(async () => {
      await new Promise((r) => setTimeout(r, 1100));
    });
    expect(getByText('59s')).toBeTruthy();
  });

  // ── countdown: prevents resend ────────────────────────────
  it('prevents resend during countdown', async () => {
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');

    await act(async () => {
      fireEvent.press(getByText('获取验证码'));
      await flush();
    });

    // During countdown, pressing the button should not resend
    expect(mockSendCode).toHaveBeenCalledTimes(1);
    // Wait for countdown to show
    await act(async () => {
      await new Promise((r) => setTimeout(r, 1100));
    });
    // Press the countdown button (should be disabled)
    fireEvent.press(getByText('59s'));
    expect(mockSendCode).toHaveBeenCalledTimes(1);
  });

  // ── handleLogin: code mode axios error with message ───────
  it('shows login error from axios response', async () => {
    mockAuth.loginByCode.mockRejectedValueOnce({
      response: { data: { message: '验证码已过期' } },
    });
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    fireEvent.changeText(getByPlaceholderText('请输入验证码'), '123456');

    await act(async () => {
      fireEvent.press(getByText('登 录'));
    });

    await waitFor(() => {
      expect(getByText('验证码已过期')).toBeTruthy();
    });
  });

  // ── handleLogin: password mode network error ──────────────
  it('shows network error in password mode', async () => {
    mockAuth.loginByPassword.mockRejectedValueOnce(new Error('timeout'));
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    fireEvent.press(getByText('使用密码登录'));
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'pass123');

    await act(async () => {
      fireEvent.press(getByText('登 录'));
    });

    await waitFor(() => {
      expect(getByText('网络错误，请检查网络连接')).toBeTruthy();
    });
  });

  // ── handleLogin: password mode axios fallback ─────────────
  it('shows fallback in password mode no message', async () => {
    mockAuth.loginByPassword.mockRejectedValueOnce({ response: { data: {} } });
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    fireEvent.press(getByText('使用密码登录'));
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'pass123');

    await act(async () => {
      fireEvent.press(getByText('登 录'));
    });

    await waitFor(() => {
      expect(getByText('登录失败')).toBeTruthy();
    });
  });

  // ── handleLogin: password mode string throw ───────────────
  it('shows network error on string throw in password mode', async () => {
    mockAuth.loginByPassword.mockRejectedValueOnce('crash');
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    fireEvent.press(getByText('使用密码登录'));
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'pass123');

    await act(async () => {
      fireEvent.press(getByText('登 录'));
    });

    await waitFor(() => {
      expect(getByText('网络错误，请检查网络连接')).toBeTruthy();
    });
  });

  // ── error clearing: password field ────────────────────────
  it('clears error when typing in password field', () => {
    const { getByText, getByPlaceholderText, queryByText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    fireEvent.press(getByText('使用密码登录'));
    fireEvent.press(getByText('登 录'));
    expect(getByText('请输入密码')).toBeTruthy();
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'a');
    expect(queryByText('请输入密码')).toBeNull();
  });

  // ── mode switch clears error ──────────────────────────────
  it('clears error when switching mode', () => {
    const { getByText, getByPlaceholderText, queryByText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    fireEvent.press(getByText('登 录'));
    expect(getByText('请输入验证码')).toBeTruthy();
    fireEvent.press(getByText('使用密码登录'));
    expect(queryByText('请输入验证码')).toBeNull();
  });
});
