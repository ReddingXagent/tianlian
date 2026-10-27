/**
 * useLogin Hook 测试
 */
import { renderHook, act } from '@testing-library/react-native';

const mockLogin = jest.fn();

jest.mock('../../store/authStore', () => ({
  useAuthStore: jest.fn((selector: (s: { login: jest.Mock }) => unknown) =>
    selector({ login: mockLogin }),
  ),
}));

import { useLogin } from '../useLogin';

describe('useLogin', () => {
  beforeEach(() => jest.clearAllMocks());

  it('初始状态: 空字段+无错误+不加载', () => {
    const { result } = renderHook(() => useLogin());
    expect(result.current.username).toBe('');
    expect(result.current.password).toBe('');
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('setUsername 更新用户名', () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setUsername('admin'));
    expect(result.current.username).toBe('admin');
  });

  it('setPassword 更新密码', () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setPassword('pass123'));
    expect(result.current.password).toBe('pass123');
  });

  it('空用户名 → 错误"请输入用户名"', async () => {
    const { result } = renderHook(() => useLogin());
    await act(async () => { await result.current.handleLogin(); });
    expect(result.current.error).toBe('请输入用户名');
  });

  it('空密码 → 错误"请输入密码"', async () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setUsername('admin'));
    await act(async () => { await result.current.handleLogin(); });
    expect(result.current.error).toBe('请输入密码');
  });

  it('用户名仅空格 → 错误"请输入用户名"', async () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setUsername('   '));
    await act(async () => { await result.current.handleLogin(); });
    expect(result.current.error).toBe('请输入用户名');
  });

  it('成功登录: 无错误', async () => {
    mockLogin.mockResolvedValueOnce(undefined);
    const { result } = renderHook(() => useLogin());
    act(() => {
      result.current.setUsername('admin');
      result.current.setPassword('pass123');
    });
    await act(async () => { await result.current.handleLogin(); });
    expect(mockLogin).toHaveBeenCalledWith('admin', 'pass123');
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('登录失败(axios错误): 显示服务端message', async () => {
    mockLogin.mockRejectedValueOnce({
      response: { data: { message: '密码错误' } },
    });
    const { result } = renderHook(() => useLogin());
    act(() => {
      result.current.setUsername('admin');
      result.current.setPassword('wrong');
    });
    await act(async () => { await result.current.handleLogin(); });
    expect(result.current.error).toBe('密码错误');
    expect(result.current.loading).toBe(false);
  });

  it('登录失败(网络错误): 显示网络错误提示', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Network'));
    const { result } = renderHook(() => useLogin());
    act(() => {
      result.current.setUsername('admin');
      result.current.setPassword('pass');
    });
    await act(async () => { await result.current.handleLogin(); });
    expect(result.current.error).toBe('网络错误，请检查网络连接');
  });

  it('输入字段时清除已有错误', async () => {
    const { result } = renderHook(() => useLogin());
    await act(async () => { await result.current.handleLogin(); });
    expect(result.current.error).toBe('请输入用户名');
    act(() => result.current.setUsername('a'));
    expect(result.current.error).toBeNull();
  });
});
