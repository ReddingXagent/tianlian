import { render, fireEvent, act } from '@testing-library/react-native';
import LoginScreen from '../LoginScreen';
import { useAuthStore } from '../../store/authStore';

const mockLogin = jest.fn();

jest.mock('../../store/authStore', () => ({
  useAuthStore: jest.fn(),
}));

describe('LoginScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
      selector({ login: mockLogin })
    );
    mockLogin.mockResolvedValue(undefined);
  });

  it('renders the app title and form fields', () => {
    const { getByText } = render(<LoginScreen />);
    expect(getByText('天链运维')).toBeTruthy();
    expect(getByText('运维管理平台')).toBeTruthy();
    expect(getByText('用户名')).toBeTruthy();
    expect(getByText('密码')).toBeTruthy();
    expect(getByText('登 录')).toBeTruthy();
  });

  it('shows error when username is empty', () => {
    const { getByText } = render(<LoginScreen />);
    fireEvent.press(getByText('登 录'));
    expect(getByText('请输入用户名')).toBeTruthy();
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('shows error when password is empty', () => {
    const { getByText, getByPlaceholderText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入用户名'), 'admin');
    fireEvent.press(getByText('登 录'));
    expect(getByText('请输入密码')).toBeTruthy();
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('calls login with trimmed credentials on valid submit', async () => {
    const { getByText, getByPlaceholderText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入用户名'), ' admin ');
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'secret');
    await act(async () => {
      fireEvent.press(getByText('登 录'));
    });
    expect(mockLogin).toHaveBeenCalledWith('admin', 'secret');
  });

  it('shows API error message when login fails', async () => {
    mockLogin.mockRejectedValue({
      response: { data: { message: '用户名或密码错误' } },
    });
    const { getByText, getByPlaceholderText, findByText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入用户名'), 'admin');
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'wrong');
    await act(async () => {
      fireEvent.press(getByText('登 录'));
    });
    expect(await findByText('用户名或密码错误')).toBeTruthy();
  });

  it('shows network error when login throws non-axios error', async () => {
    mockLogin.mockRejectedValue(new Error('boom'));
    const { getByText, getByPlaceholderText, findByText } = render(<LoginScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入用户名'), 'admin');
    fireEvent.changeText(getByPlaceholderText('请输入密码'), 'x');
    await act(async () => {
      fireEvent.press(getByText('登 录'));
    });
    expect(await findByText('网络错误，请检查网络连接')).toBeTruthy();
  });

  it('exposes expected testIDs for e2e (guard against children misuse)', () => {
    const { getByTestId } = render(<LoginScreen />);
    expect(getByTestId('login-username-input')).toBeTruthy();
    expect(getByTestId('login-password-input')).toBeTruthy();
    expect(getByTestId('login-submit-btn')).toBeTruthy();
  });});
