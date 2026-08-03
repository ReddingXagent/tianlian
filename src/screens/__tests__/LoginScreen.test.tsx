import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import LoginScreen from '../LoginScreen';

// ── Mock auth store ──────────────────────────────────────────
const mockAuth = {
  loginByCode: jest.fn().mockResolvedValue(undefined),
  loginByPassword: jest.fn().mockResolvedValue(undefined),
};

jest.mock('../../store/authStore', () => ({
  useAuthStore: (selector: (s: typeof mockAuth) => unknown) => selector(mockAuth),
}));

const renderLogin = () =>
  render(
    <SafeAreaProvider>
      <LoginScreen />
    </SafeAreaProvider>
  );

describe('LoginScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAuth.loginByCode.mockResolvedValue(undefined);
    mockAuth.loginByPassword.mockResolvedValue(undefined);
  });

  // ── Basic rendering ────────────────────────────────────────
  it('renders app name and subtitle', () => {
    const { getByText } = renderLogin();
    expect(getByText('天链充电')).toBeTruthy();
    expect(getByText('新能源充电服务平台')).toBeTruthy();
  });

  it('renders phone input', () => {
    const { getByPlaceholderText } = renderLogin();
    expect(getByPlaceholderText('请输入手机号')).toBeTruthy();
  });

  it('renders verification code input by default', () => {
    const { getByPlaceholderText } = renderLogin();
    expect(getByPlaceholderText('请输入验证码')).toBeTruthy();
  });

  it('renders login button', () => {
    const { getByText } = renderLogin();
    expect(getByText('登 录')).toBeTruthy();
  });

  it('renders mode switch link', () => {
    const { getByText } = renderLogin();
    expect(getByText('使用密码登录')).toBeTruthy();
  });

  it('renders send code button', () => {
    const { getByText } = renderLogin();
    expect(getByText('获取验证码')).toBeTruthy();
  });

  // ── Mode switching ─────────────────────────────────────────
  it('switches to password mode when tapping switch link', () => {
    const { getByText, getByPlaceholderText, queryByPlaceholderText } = renderLogin();
    fireEvent.press(getByText('使用密码登录'));
    expect(getByPlaceholderText('请输入密码')).toBeTruthy();
    expect(queryByPlaceholderText('请输入验证码')).toBeNull();
    expect(getByText('使用验证码登录')).toBeTruthy();
  });

  it('switches back to code mode', () => {
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.press(getByText('使用密码登录'));
    fireEvent.press(getByText('使用验证码登录'));
    expect(getByPlaceholderText('请输入验证码')).toBeTruthy();
  });

  // ── Validation ─────────────────────────────────────────────
  it('shows error for short phone on send code', () => {
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '123');
    fireEvent.press(getByText('获取验证码'));
    expect(getByText('请输入正确的手机号')).toBeTruthy();
  });

  it('shows error for short phone on login', () => {
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '123');
    fireEvent.press(getByText('登 录'));
    expect(getByText('请输入正确的手机号')).toBeTruthy();
    expect(mockAuth.loginByCode).not.toHaveBeenCalled();
  });

  it('shows error when code is empty on login', () => {
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    fireEvent.press(getByText('登 录'));
    expect(getByText('请输入验证码')).toBeTruthy();
  });

  it('shows error when password is empty in password mode', () => {
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    fireEvent.press(getByText('使用密码登录'));
    fireEvent.press(getByText('登 录'));
    expect(getByText('请输入密码')).toBeTruthy();
  });

  // ── Login flow ─────────────────────────────────────────────
  it('calls loginByCode with phone and code', async () => {
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    fireEvent.changeText(getByPlaceholderText('请输入验证码'), '123456');
    fireEvent.press(getByText('登 录'));
    await waitFor(() => {
      expect(mockAuth.loginByCode).toHaveBeenCalledWith('13800138000', '123456');
    });
  });

  it('calls loginByPassword in password mode', async () => {
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    fireEvent.press(getByText('使用密码登录'));
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'mypass123');
    fireEvent.press(getByText('登 录'));
    await waitFor(() => {
      expect(mockAuth.loginByPassword).toHaveBeenCalledWith('13800138000', 'mypass123');
    });
  });

  it('shows error when loginByCode fails', async () => {
    mockAuth.loginByCode.mockRejectedValueOnce({
      response: { data: { message: '验证码错误' } },
    });
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    fireEvent.changeText(getByPlaceholderText('请输入验证码'), 'wrong');
    fireEvent.press(getByText('登 录'));
    await waitFor(() => {
      expect(getByText('验证码错误')).toBeTruthy();
    });
  });

  it('shows network error when login throws non-axios error', async () => {
    mockAuth.loginByCode.mockRejectedValueOnce(new Error('timeout'));
    const { getByText, getByPlaceholderText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    fireEvent.changeText(getByPlaceholderText('请输入验证码'), '123456');
    fireEvent.press(getByText('登 录'));
    await waitFor(() => {
      expect(getByText('网络错误，请检查网络连接')).toBeTruthy();
    });
  });

  // ── Error clearing ─────────────────────────────────────────
  it('clears error when typing in phone field', () => {
    const { getByText, getByPlaceholderText, queryByText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '123');
    fireEvent.press(getByText('登 录'));
    expect(getByText('请输入正确的手机号')).toBeTruthy();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '13800138000');
    expect(queryByText('请输入正确的手机号')).toBeNull();
  });

  it('clears error when typing in code field', () => {
    const { getByText, getByPlaceholderText, queryByText } = renderLogin();
    fireEvent.changeText(getByPlaceholderText('请输入手机号'), '123');
    fireEvent.press(getByText('登 录'));
    expect(getByText('请输入正确的手机号')).toBeTruthy();
    fireEvent.changeText(getByPlaceholderText('请输入验证码'), '4');
    expect(queryByText('请输入正确的手机号')).toBeNull();
  });
});
