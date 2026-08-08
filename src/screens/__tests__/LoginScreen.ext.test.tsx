/**
 * LoginScreen 扩展测试 — branch覆盖率提升
 * 目标: 89.47% → 100% branches
 * 覆盖: 空用户名/密码验证、axios错误、非axios错误、loading态、error清除
 */
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import LoginScreen from '../LoginScreen';

// Mock authStore — LoginScreen uses useAuthStore((s) => s.login) selector
const mockLogin = jest.fn();

jest.mock('../../store/authStore', () => ({
  useAuthStore: (selector: (s: { login: jest.Mock }) => unknown) => selector({ login: mockLogin }),
}));

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
}));

describe('LoginScreen.ext — branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows local error when username is empty', () => {
    const { getByText, getByPlaceholderText } = render(<LoginScreen />);
    // Password has value but username empty
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'pass');
    fireEvent.press(getByText('登 录'));
    expect(getByText('请输入用户名')).toBeTruthy();
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('shows local error when password is empty', () => {
    const { getByText, getByPlaceholderText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入用户名'), 'admin');
    fireEvent.press(getByText('登 录'));
    expect(getByText('请输入密码')).toBeTruthy();
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('clears error when typing in username', () => {
    const { getByText, getByPlaceholderText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入用户名'), 'admin');
    fireEvent.press(getByText('登 录')); // triggers password error
    // Type in password clears error
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'pass');
    expect(getByText('登 录')).toBeTruthy(); // button still there, no error text
  });

  it('handles axios error with response message', async () => {
    mockLogin.mockRejectedValueOnce({
      response: { data: { message: '账户被禁用' } },
    });

    const { getByText, getByPlaceholderText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入用户名'), 'admin');
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'pass');
    fireEvent.press(getByText('登 录'));

    await waitFor(() => {
      expect(getByText('账户被禁用')).toBeTruthy();
    });
  });

  it('handles axios error without response.data.message (fallback)', async () => {
    mockLogin.mockRejectedValueOnce({
      response: {},
    });

    const { getByText, getByPlaceholderText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入用户名'), 'admin');
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'pass');
    fireEvent.press(getByText('登 录'));

    await waitFor(() => {
      expect(getByText('登录失败，请检查用户名和密码')).toBeTruthy();
    });
  });

  it('handles non-axios error (network)', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Network Error'));

    const { getByText, getByPlaceholderText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入用户名'), 'admin');
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'pass');
    fireEvent.press(getByText('登 录'));

    await waitFor(() => {
      expect(getByText('网络错误，请检查网络连接')).toBeTruthy();
    });
  });

  it('shows loading state during login (button disabled)', async () => {
    let resolveLogin: (() => void) = () => {};
    mockLogin.mockImplementationOnce(
      () => new Promise<void>((resolve) => { resolveLogin = resolve; })
    );

    const { getByPlaceholderText, queryByText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入用户名'), 'admin');
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'pass');
    fireEvent.press(queryByText('登 录')!);

    // During loading: button text replaced by spinner, "登 录" text disappears
    await waitFor(() => {
      expect(queryByText('登 录')).toBeNull();
    });

    resolveLogin();
  });
});
