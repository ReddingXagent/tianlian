import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { Alert, ActivityIndicator, TouchableOpacity, KeyboardAvoidingView, Platform } from 'react-native';
import LoginScreen from '../LoginScreen';

const mockLogin = jest.fn();
jest.mock('../../store/authStore', () => ({
  useAuthStore: () => ({ login: mockLogin }),
}));

describe('LoginScreen', () => {
  let alertSpy: jest.SpyInstance;

  beforeEach(() => {
    mockLogin.mockReset();
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

  it('用户名为空时提示且不调用login', async () => {
    const { getByPlaceholderText, getByText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('密码'), 'secret');
    fireEvent.press(getByText('登录'));
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('提示', '请输入用户名和密码');
    });
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('密码为空白时提示且不调用login', async () => {
    const { getByPlaceholderText, getByText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('用户名'), 'admin');
    fireEvent.changeText(getByPlaceholderText('密码'), '   ');
    fireEvent.press(getByText('登录'));
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('提示', '请输入用户名和密码');
    });
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('登录成功时以trim后的用户名与原始密码调用login且不弹错', async () => {
    mockLogin.mockResolvedValueOnce(undefined);
    const { getByPlaceholderText, getByText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('用户名'), '  admin ');
    fireEvent.changeText(getByPlaceholderText('密码'), 'p@ss');
    fireEvent.press(getByText('登录'));
    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('admin', 'p@ss');
    });
    expect(alertSpy).not.toHaveBeenCalled();
  });

  it('登录失败(Error)时弹出服务端错误信息并复位按钮', async () => {
    mockLogin.mockRejectedValueOnce(new Error('密码错误'));
    const { getByPlaceholderText, getByText, queryByText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('用户名'), 'admin');
    fireEvent.changeText(getByPlaceholderText('密码'), 'wrong');
    fireEvent.press(getByText('登录'));
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('登录失败', '密码错误');
    });
    // finally复位: spinner消失, 登录按钮恢复
    await waitFor(() => {
      expect(queryByText('登录')).toBeTruthy();
    });
  });

  it('登录失败(非Error)时使用兜底错误文案', async () => {
    mockLogin.mockRejectedValueOnce('network down');
    const { getByPlaceholderText, getByText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('用户名'), 'admin');
    fireEvent.changeText(getByPlaceholderText('密码'), 'x');
    fireEvent.press(getByText('登录'));
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('登录失败', '登录失败，请检查网络');
    });
  });

  it('登录进行中显示spinner并禁用按钮(挂起第二刷探针)', async () => {
    let releaseLogin!: () => void;
    mockLogin.mockReturnValueOnce(new Promise<void>((resolve) => { releaseLogin = resolve; }));
    const { getByPlaceholderText, getByText, UNSAFE_getByType, UNSAFE_getAllByType } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('用户名'), 'admin');
    fireEvent.changeText(getByPlaceholderText('密码'), 'p@ss');
    // 表单内唯一TouchableOpacity即登录按钮(加载中文本节点卸载, 按钮容器引用稳定)
    const button = UNSAFE_getAllByType(TouchableOpacity)[0];
    fireEvent.press(button);
    await waitFor(() => {
      expect(UNSAFE_getByType(ActivityIndicator)).toBeTruthy();
    });
    expect(button.props.disabled).toBe(true);
    // 放行避免泄漏
    releaseLogin();
    await waitFor(() => {
      expect(getByText('登录')).toBeTruthy();
    });
    expect(button.props.disabled).toBe(false);
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
