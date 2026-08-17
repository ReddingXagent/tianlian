import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { Alert, ActivityIndicator, TouchableOpacity, KeyboardAvoidingView, Platform } from 'react-native';
import LoginScreen from '../LoginScreen';

const mockUseLogin = {
  username: '',
  password: '',
  loading: false,
  error: null as string | null,
  setUsername: jest.fn(),
  setPassword: jest.fn(),
  login: jest.fn(),
};

jest.mock('../../hooks/useLogin', () => ({
  useLogin: () => mockUseLogin,
}));

describe('LoginScreen', () => {
  let alertSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseLogin.username = '';
    mockUseLogin.password = '';
    mockUseLogin.loading = false;
    mockUseLogin.error = null;
    mockUseLogin.setUsername = jest.fn();
    mockUseLogin.setPassword = jest.fn();
    mockUseLogin.login = jest.fn();
    alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });

  afterEach(() => {
    alertSpy.mockRestore();
  });

  it('渲染logo与登录表单', () => {
    const { getByText, getByPlaceholderText } = render(<LoginScreen />);
    expect(getByText('天链')).toBeTruthy();
    expect(getByText('站长管理平台')).toBeTruthy();
    expect(getByPlaceholderText('用户名')).toBeTruthy();
    expect(getByPlaceholderText('密码')).toBeTruthy();
    expect(getByText('登录')).toBeTruthy();
  });

  it('用户名为空时login返回false+error, 弹Alert', async () => {
    mockUseLogin.login.mockResolvedValue(false);
    mockUseLogin.error = '请输入用户名和密码';
    const { getByText } = render(<LoginScreen />);
    fireEvent.press(getByText('登录'));
    await waitFor(() => {
      expect(mockUseLogin.login).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('登录失败', '请输入用户名和密码');
    });
  });

  it('登录成功时不弹Alert', async () => {
    mockUseLogin.login.mockResolvedValue(true);
    const { getByText } = render(<LoginScreen />);
    fireEvent.press(getByText('登录'));
    await waitFor(() => {
      expect(mockUseLogin.login).toHaveBeenCalledTimes(1);
    });
    expect(alertSpy).not.toHaveBeenCalled();
  });

  it('登录失败时弹出错误信息', async () => {
    mockUseLogin.login.mockResolvedValue(false);
    mockUseLogin.error = '密码错误';
    const { getByText } = render(<LoginScreen />);
    fireEvent.press(getByText('登录'));
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('登录失败', '密码错误');
    });
  });

  it('登录进行中显示spinner并禁用按钮', async () => {
    mockUseLogin.loading = true;
    const { UNSAFE_getByType, UNSAFE_getAllByType } = render(<LoginScreen />);
    expect(UNSAFE_getByType(ActivityIndicator)).toBeTruthy();
    const button = UNSAFE_getAllByType(TouchableOpacity)[0];
    expect(button.props.disabled).toBe(true);
  });

  it('KAV平台适配: android侧behavior为undefined(不做padding避让)', () => {
    const origOS = Platform.OS;
    (Platform as { OS: string }).OS = 'android';
    try {
      const { UNSAFE_getByType } = render(<LoginScreen />);
      expect(UNSAFE_getByType(KeyboardAvoidingView).props.behavior).toBeUndefined();
    } finally {
      (Platform as { OS: string }).OS = origOS;
    }
  });
});
