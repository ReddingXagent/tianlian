import { renderHook, act } from '@testing-library/react-native';
import { authApi } from '../../services/api';
import { useAuthStore } from '../../store/authStore';
import { useLogin } from '../useLogin';

jest.mock('../../services/api', () => ({
  authApi: {
    sendCode: jest.fn(),
  },
}));

jest.mock('../../store/authStore', () => ({
  useAuthStore: jest.fn((selector) =>
    selector({
      loginByCode: jest.fn(),
      loginByPassword: jest.fn(),
    })
  ),
}));

describe('useLogin', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('should have correct initial state', () => {
    const { result } = renderHook(() => useLogin());

    expect(result.current.phone).toBe('');
    expect(result.current.code).toBe('');
    expect(result.current.password).toBe('');
    expect(result.current.loginMode).toBe('code');
    expect(result.current.loading).toBe(false);
    expect(result.current.sendingCode).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.countdown).toBe(0);
  });

  it('should update phone and clear error', () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setPhone('13800138000'));
    expect(result.current.phone).toBe('13800138000');
  });

  it('should update code and clear error', () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setCode('1234'));
    expect(result.current.code).toBe('1234');
  });

  it('should update password', () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setPassword('pass123'));
    expect(result.current.password).toBe('pass123');
  });

  it('should switch login mode', () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setLoginMode('password'));
    expect(result.current.loginMode).toBe('password');
  });

  it('should validate phone on sendCode (empty)', async () => {
    const { result } = renderHook(() => useLogin());

    await act(async () => {
      await result.current.handleSendCode();
    });

    expect(result.current.error).toBe('请输入正确的手机号');
    expect(authApi.sendCode).not.toHaveBeenCalled();
  });

  it('should validate phone on sendCode (too short)', async () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setPhone('138'));

    await act(async () => {
      await result.current.handleSendCode();
    });

    expect(result.current.error).toBe('请输入正确的手机号');
    expect(authApi.sendCode).not.toHaveBeenCalled();
  });

  it('should send code successfully and start countdown', async () => {
    (authApi.sendCode as jest.Mock).mockResolvedValue({});
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setPhone('13800138000'));

    await act(async () => {
      await result.current.handleSendCode();
    });

    expect(authApi.sendCode).toHaveBeenCalledWith({ phone: '13800138000' });
    expect(result.current.sendingCode).toBe(false);
    expect(result.current.countdown).toBe(60);
  });

  it('should handle sendCode axios error', async () => {
    (authApi.sendCode as jest.Mock).mockRejectedValue({
      response: { data: { message: '手机号已注册' } },
    });
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setPhone('13800138000'));

    await act(async () => {
      await result.current.handleSendCode();
    });

    expect(result.current.error).toBe('手机号已注册');
    expect(result.current.sendingCode).toBe(false);
  });

  it('should handle sendCode network error', async () => {
    (authApi.sendCode as jest.Mock).mockRejectedValue(new Error('Network'));
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setPhone('13800138000'));

    await act(async () => {
      await result.current.handleSendCode();
    });

    expect(result.current.error).toBe('网络错误，请检查网络连接');
  });

  it('should validate phone on login (empty)', async () => {
    const { result } = renderHook(() => useLogin());

    await act(async () => {
      await result.current.handleLogin();
    });

    expect(result.current.error).toBe('请输入正确的手机号');
    expect(result.current.loading).toBe(false);
  });

  it('should validate code in code mode', async () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setPhone('13800138000'));

    await act(async () => {
      await result.current.handleLogin();
    });

    expect(result.current.error).toBe('请输入验证码');
  });

  it('should validate password in password mode', async () => {
    const { result } = renderHook(() => useLogin());
    act(() => {
      result.current.setPhone('13800138000');
      result.current.setLoginMode('password');
    });

    await act(async () => {
      await result.current.handleLogin();
    });

    expect(result.current.error).toBe('请输入密码');
  });

  it('should login by code successfully', async () => {
    const mockLoginByCode = jest.fn().mockResolvedValue(undefined);
    (useAuthStore as unknown as jest.Mock).mockImplementation((selector: (s: unknown) => unknown) =>
      selector({ loginByCode: mockLoginByCode, loginByPassword: jest.fn() })
    );

    (authApi.sendCode as jest.Mock).mockResolvedValue({});
    const { result } = renderHook(() => useLogin());
    act(() => {
      result.current.setPhone('13800138000');
      result.current.setCode('1234');
    });

    await act(async () => {
      await result.current.handleLogin();
    });

    expect(mockLoginByCode).toHaveBeenCalledWith('13800138000', '1234');
    expect(result.current.loading).toBe(false);
  });

  it('should login by password successfully', async () => {
    const mockLoginByPassword = jest.fn().mockResolvedValue(undefined);
    (useAuthStore as unknown as jest.Mock).mockImplementation((selector: (s: unknown) => unknown) =>
      selector({ loginByCode: jest.fn(), loginByPassword: mockLoginByPassword })
    );

    const { result } = renderHook(() => useLogin());
    act(() => {
      result.current.setPhone('13800138000');
      result.current.setLoginMode('password');
      result.current.setPassword('pass123');
    });

    await act(async () => {
      await result.current.handleLogin();
    });

    expect(mockLoginByPassword).toHaveBeenCalledWith('13800138000', 'pass123');
    expect(result.current.loading).toBe(false);
  });

  it('should handle login axios error', async () => {
    const mockLoginByCode = jest.fn().mockRejectedValue({
      response: { data: { message: '验证码错误' } },
    });
    (useAuthStore as unknown as jest.Mock).mockImplementation((selector: (s: unknown) => unknown) =>
      selector({ loginByCode: mockLoginByCode, loginByPassword: jest.fn() })
    );

    const { result } = renderHook(() => useLogin());
    act(() => {
      result.current.setPhone('13800138000');
      result.current.setCode('1234');
    });

    await act(async () => {
      await result.current.handleLogin();
    });

    expect(result.current.error).toBe('验证码错误');
    expect(result.current.loading).toBe(false);
  });

  it('should handle login network error', async () => {
    const mockLoginByCode = jest.fn().mockRejectedValue(new Error('Network'));
    (useAuthStore as unknown as jest.Mock).mockImplementation((selector: (s: unknown) => unknown) =>
      selector({ loginByCode: mockLoginByCode, loginByPassword: jest.fn() })
    );

    const { result } = renderHook(() => useLogin());
    act(() => {
      result.current.setPhone('13800138000');
      result.current.setCode('1234');
    });

    await act(async () => {
      await result.current.handleLogin();
    });

    expect(result.current.error).toBe('网络错误，请检查网络连接');
    expect(result.current.loading).toBe(false);
  });

  it('should clear error when typing', () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setPhone('138'));
    // trigger error
    act(() => {
      void result.current.handleSendCode();
    });
    // now type again → should clear error
    act(() => result.current.setPhone('139'));
    expect(result.current.error).toBeNull();
  });
});
