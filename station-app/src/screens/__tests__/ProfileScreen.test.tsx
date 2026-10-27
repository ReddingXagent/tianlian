import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';
import ProfileScreen from '../ProfileScreen';
import { useAuthStore } from '../../store/authStore';

jest.mock('../../store/authStore', () => ({
  useAuthStore: jest.fn(),
}));

const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
}));

interface MockUser {
  username?: string;
  nickname?: string;
  role?: string;
  email?: string;
  phone?: string;
}

const setup = (user: MockUser | null = {
  username: 'zhangsan',
  nickname: '张三',
  role: 'station_master',
  email: 'zhangsan@example.com',
  phone: '13800000000',
}) => {
  const logout = jest.fn().mockResolvedValue(undefined);
  (useAuthStore as unknown as jest.Mock).mockReturnValue({ user, logout });
  return { logout };
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('ProfileScreen', () => {
  it('渲染用户卡片与账号信息', () => {
    setup();
    const { getByText, getAllByText } = render(<ProfileScreen />);
    expect(getByText('张')).toBeTruthy(); // 头像取昵称首字
    expect(getAllByText('张三').length).toBe(2); // 昵称卡片+信息行
    expect(getByText('站长')).toBeTruthy(); // role映射
    expect(getByText('zhangsan')).toBeTruthy();
    expect(getByText('zhangsan@example.com')).toBeTruthy();
    expect(getByText('13800000000')).toBeTruthy();
  });

  it('已知角色映射为中文标签', () => {
    setup({ username: 'u1', role: 'admin' });
    const { getByText } = render(<ProfileScreen />);
    expect(getByText('管理员')).toBeTruthy();
  });

  it('未知角色原样透传', () => {
    setup({ username: 'u2', role: 'custom_role_x' });
    const { getByText } = render(<ProfileScreen />);
    expect(getByText('custom_role_x')).toBeTruthy();
  });

  it('user缺失时走兜底文案', () => {
    setup(null);
    const { getByText, getAllByText } = render(<ProfileScreen />);
    expect(getByText('?')).toBeTruthy(); // 头像兜底
    expect(getByText('未设置')).toBeTruthy(); // 昵称兜底
    expect(getByText('未知')).toBeTruthy(); // 角色兜底
    expect(getAllByText('-').length).toBe(4); // 用户名/昵称/邮箱/手机号兜底
  });

  it('设置菜单三项齐全', () => {
    setup();
    const { getByText } = render(<ProfileScreen />);
    expect(getByText('消息通知')).toBeTruthy();
    expect(getByText('修改密码')).toBeTruthy();
    expect(getByText('关于')).toBeTruthy();
  });

  it('退出登录: 确认后调用logout', async () => {
    const { logout } = setup();
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_title, _msg, buttons) => {
      const destructive = buttons?.find((b) => b.style === 'destructive');
      destructive?.onPress?.();
    });
    const { getByText, getByTestId } = render(<ProfileScreen />);
    // testID守卫: 退出登录锚点必须是prop而非children(F3688回归)
    expect(getByTestId('profile-logout-btn')).toBeTruthy();
    fireEvent.press(getByText('退出登录'));
    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1));
    alertSpy.mockRestore();
  });

  it('退出登录: 取消不调用logout', () => {
    const { logout } = setup();
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_title, _msg, buttons) => {
      const cancel = buttons?.find((b) => b.style === 'cancel');
      cancel?.onPress?.();
    });
    const { getByText } = render(<ProfileScreen />);
    fireEvent.press(getByText('退出登录'));
    expect(logout).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it('logout异常静默处理不崩溃', async () => {
    const { logout } = setup();
    logout.mockRejectedValueOnce(new Error('network down'));
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_title, _msg, buttons) => {
      const destructive = buttons?.find((b) => b.style === 'destructive');
      destructive?.onPress?.();
    });
    const { getByText } = render(<ProfileScreen />);
    fireEvent.press(getByText('退出登录'));
    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1));
    alertSpy.mockRestore();
  });
});

describe('ProfileScreen 商户进件入口 (卡 a8ca56aa)', () => {
  it('商户服务区含进件入口, 点击跳转 MerchantKYC', () => {
    setup();
    mockNavigate.mockClear();
    const { getByTestId } = render(<ProfileScreen />);
    const entry = getByTestId('kyc-entry-btn');
    expect(entry).toBeTruthy();
    fireEvent.press(entry);
    expect(mockNavigate).toHaveBeenCalledWith('MerchantKYC');
  });
});
