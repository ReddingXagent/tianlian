import { useState, useCallback } from 'react';
import { useAuthStore } from '../store/authStore';

interface UseLoginReturn {
  username: string;
  password: string;
  loading: boolean;
  error: string | null;
  setUsername: (v: string) => void;
  setPassword: (v: string) => void;
  login: () => Promise<boolean>;
}

export function useLogin(): UseLoginReturn {
  const { login: doLogin } = useAuthStore();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = useCallback(async () => {
    if (!username.trim() || !password.trim()) {
      setError('请输入用户名和密码');
      return false;
    }
    setLoading(true);
    setError(null);
    try {
      await doLogin(username.trim(), password);
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '登录失败';
      setError(message);
      return false;
    } finally {
      setLoading(false);
    }
  }, [username, password, doLogin]);

  return { username, password, loading, error, setUsername, setPassword, login };
}
