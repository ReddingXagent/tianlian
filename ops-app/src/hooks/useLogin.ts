import { useState, useCallback } from 'react';
import { useAuthStore } from '../store/authStore';

interface UseLoginReturn {
  username: string;
  setUsername: (text: string) => void;
  password: string;
  setPassword: (text: string) => void;
  loading: boolean;
  error: string | null;
  handleLogin: () => Promise<void>;
}

export function useLogin(): UseLoginReturn {
  const [username, setUsernameState] = useState('');
  const [password, setPasswordState] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const login = useAuthStore((s) => s.login);

  const setUsername = useCallback((text: string) => {
    setUsernameState(text);
    setError(null);
  }, []);

  const setPassword = useCallback((text: string) => {
    setPasswordState(text);
    setError(null);
  }, []);

  const handleLogin = useCallback(async () => {
    if (!username.trim()) {
      setError('请输入用户名');
      return;
    }
    if (!password.trim()) {
      setError('请输入密码');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await login(username.trim(), password);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        setError(axiosErr.response?.data?.message || '登录失败，请检查用户名和密码');
      } else {
        setError('网络错误，请检查网络连接');
      }
    } finally {
      setLoading(false);
    }
  }, [username, password, login]);

  return {
    username,
    setUsername,
    password,
    setPassword,
    loading,
    error,
    handleLogin,
  };
}
