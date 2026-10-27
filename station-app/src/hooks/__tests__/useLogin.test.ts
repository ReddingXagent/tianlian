/**
 * useLogin Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { useLogin } from '../useLogin';

// Mock authStore
const mockLogin = jest.fn();
jest.mock('../../store/authStore', () => ({
  useAuthStore: () => ({ login: mockLogin }),
}));

describe('useLogin', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('初始状态: 空字段, loading=false, error=null', () => {
    const { result } = renderHook(() => useLogin());
    expect(result.current.username).toBe('');
    expect(result.current.password).toBe('');
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('setUsername/setPassword 更新字段', () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setUsername('admin'));
    act(() => result.current.setPassword('pass123'));
    expect(result.current.username).toBe('admin');
    expect(result.current.password).toBe('pass123');
  });

  it('空用户名+密码 → login返回false, error设置', async () => {
    const { result } = renderHook(() => useLogin());
    let ok: boolean | undefined;
    await act(async () => { ok = await result.current.login(); });
    expect(ok).toBe(false);
    expect(result.current.error).toBe('请输入用户名和密码');
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('仅用户名 → login返回false', async () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setUsername('admin'));
    let ok: boolean | undefined;
    await act(async () => { ok = await result.current.login(); });
    expect(ok).toBe(false);
    expect(result.current.error).toBe('请输入用户名和密码');
  });

  it('仅密码 → login返回false', async () => {
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setPassword('pass'));
    let ok: boolean | undefined;
    await act(async () => { ok = await result.current.login(); });
    expect(ok).toBe(false);
    expect(result.current.error).toBe('请输入用户名和密码');
  });

  it('有效凭据 → login成功, loading先true后false', async () => {
    mockLogin.mockResolvedValue(undefined);
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setUsername('admin'));
    act(() => result.current.setPassword('pass123'));
    let ok: boolean | undefined;
    await act(async () => { ok = await result.current.login(); });
    expect(ok).toBe(true);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(mockLogin).toHaveBeenCalledWith('admin', 'pass123');
  });

  it('login失败 → error设置, loading=false', async () => {
    mockLogin.mockRejectedValue(new Error('密码错误'));
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setUsername('admin'));
    act(() => result.current.setPassword('wrong'));
    let ok: boolean | undefined;
    await act(async () => { ok = await result.current.login(); });
    expect(ok).toBe(false);
    expect(result.current.error).toBe('密码错误');
    expect(result.current.loading).toBe(false);
  });

  it('login失败(非Error) → 默认error信息', async () => {
    mockLogin.mockRejectedValue('string error');
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setUsername('admin'));
    act(() => result.current.setPassword('pass'));
    let ok: boolean | undefined;
    await act(async () => { ok = await result.current.login(); });
    expect(ok).toBe(false);
    expect(result.current.error).toBe('登录失败');
  });

  it('username trim → 前后空格被去除', async () => {
    mockLogin.mockResolvedValue(undefined);
    const { result } = renderHook(() => useLogin());
    act(() => result.current.setUsername('  admin  '));
    act(() => result.current.setPassword('pass'));
    await act(async () => { await result.current.login(); });
    expect(mockLogin).toHaveBeenCalledWith('admin', 'pass');
  });
});
