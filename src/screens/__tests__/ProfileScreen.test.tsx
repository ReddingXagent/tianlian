import { Alert, type AlertButton } from 'react-native';
import { render, fireEvent, act } from '@testing-library/react-native';
import ProfileScreen from '../ProfileScreen';
import { useAuthStore } from '../../store/authStore';

const mockLogout = jest.fn();

jest.mock('../../store/authStore', () => ({
  useAuthStore: jest.fn(),
}));

const MOCK_USER = {
  id: 1,
  username: 'admin',
  nickname: '管理员小王',
  email: 'a@b.com',
  phone: '13800000000',
  role: 'admin',
  stationIds: [],
  createdAt: '',
  updatedAt: '',
};

describe('ProfileScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockLogout.mockResolvedValue(undefined);
    (useAuthStore as unknown as jest.Mock).mockReturnValue({
      user: MOCK_USER,
      logout: mockLogout,
    });
  });

  it('renders user profile info and role label', () => {
    const { getByText, getAllByText } = render(<ProfileScreen />);
    // nickname shows in both the profile card and the info list
    expect(getAllByText('管理员小王').length).toBeGreaterThanOrEqual(1);
    expect(getByText('管理员')).toBeTruthy();
    expect(getByText('admin')).toBeTruthy();
    expect(getByText('a@b.com')).toBeTruthy();
    expect(getByText('13800000000')).toBeTruthy();
  });

  it('renders settings menu entries and version', () => {
    const { getByText } = render(<ProfileScreen />);
    expect(getByText('消息通知')).toBeTruthy();
    expect(getByText('修改密码')).toBeTruthy();
    expect(getByText('操作手册')).toBeTruthy();
    expect(getByText('关于')).toBeTruthy();
    expect(getByText('天链运维 v1.0.0')).toBeTruthy();
  });

  it('handles missing user gracefully', () => {
    (useAuthStore as unknown as jest.Mock).mockReturnValue({
      user: null,
      logout: mockLogout,
    });
    const { getByText } = render(<ProfileScreen />);
    expect(getByText('未设置')).toBeTruthy();
    expect(getByText('未知')).toBeTruthy();
  });

  it('shows logout confirmation alert', () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    const { getByText } = render(<ProfileScreen />);
    fireEvent.press(getByText('退出登录'));
    expect(alertSpy).toHaveBeenCalledWith(
      '退出登录',
      '确定要退出当前账号吗？',
      expect.any(Array)
    );
    alertSpy.mockRestore();
  });

  it('calls logout when confirmation is pressed', () => {
    let buttons: AlertButton[] = [];
    const alertSpy = jest
      .spyOn(Alert, 'alert')
      .mockImplementation((_t, _m, b) => {
        buttons = b || [];
      });
    const { getByText } = render(<ProfileScreen />);
    fireEvent.press(getByText('退出登录'));
    const confirm = buttons.find((b) => b.text === '退出');
    act(() => {
      confirm.onPress();
    });
    expect(mockLogout).toHaveBeenCalled();
    alertSpy.mockRestore();
  });
});
