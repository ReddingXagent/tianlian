import React from 'react';
import { render } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import LoginScreen from '../LoginScreen';

// Mock the auth store
const mockLoginByCode = jest.fn();
const mockLoginByPassword = jest.fn();

jest.mock('../../store/authStore', () => ({
  useAuthStore: (selector: (state: unknown) => unknown) =>
    selector({
      loginByCode: mockLoginByCode,
      loginByPassword: mockLoginByPassword,
    }),
}));

// Mock dynamic import for authApi
jest.mock('../../services/api', () => ({
  authApi: {
    sendCode: jest.fn(),
  },
}));

describe('LoginScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const renderLoginScreen = () =>
    render(
      <SafeAreaProvider>
        <LoginScreen />
      </SafeAreaProvider>
    );

  it('renders app name and subtitle', () => {
    const { getByText } = renderLoginScreen();
    expect(getByText('天链充电')).toBeTruthy();
    expect(getByText('新能源充电服务平台')).toBeTruthy();
  });

  it('renders phone input', () => {
    const { getByPlaceholderText } = renderLoginScreen();
    expect(getByPlaceholderText('请输入手机号')).toBeTruthy();
  });

  it('renders login mode by default as code', () => {
    const { getByText, getByPlaceholderText } = renderLoginScreen();
    expect(getByPlaceholderText('请输入验证码')).toBeTruthy();
    expect(getByText('使用密码登录')).toBeTruthy();
  });

  it('renders login button', () => {
    const { getByText } = renderLoginScreen();
    expect(getByText('登 录')).toBeTruthy();
  });

  it('renders get code button', () => {
    const { getByText } = renderLoginScreen();
    expect(getByText('获取验证码')).toBeTruthy();
  });
});