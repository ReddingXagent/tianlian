import { useState, useCallback, useRef, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../services/api';

type LoginMode = 'code' | 'password';

interface UseLoginReturn {
  phone: string;
  setPhone: (text: string) => void;
  code: string;
  setCode: (text: string) => void;
  password: string;
  setPassword: (text: string) => void;
  loginMode: LoginMode;
  setLoginMode: (mode: LoginMode) => void;
  loading: boolean;
  sendingCode: boolean;
  error: string | null;
  countdown: number;
  handleSendCode: () => Promise<void>;
  handleLogin: () => Promise<void>;
}

export function useLogin(): UseLoginReturn {
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [loginMode, setLoginMode] = useState<LoginMode>('code');
  const [loading, setLoading] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);
  const loginByCode = useAuthStore((s) => s.loginByCode);
  const loginByPassword = useAuthStore((s) => s.loginByPassword);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startCountdown = useCallback(() => {
    setCountdown(60);
    timerRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  const handleSendCode = useCallback(async () => {
    if (!phone.trim() || phone.trim().length < 11) {
      setError('请输入正确的手机号');
      return;
    }
    setSendingCode(true);
    setError(null);
    try {
      await authApi.sendCode({ phone: phone.trim() });
      startCountdown();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        setError(axiosErr.response?.data?.message || '发送验证码失败');
      } else {
        setError('网络错误，请检查网络连接');
      }
    } finally {
      setSendingCode(false);
    }
  }, [phone, startCountdown]);

  const handleLogin = useCallback(async () => {
    if (!phone.trim() || phone.trim().length < 11) {
      setError('请输入正确的手机号');
      return;
    }

    if (loginMode === 'code') {
      if (!code.trim()) {
        setError('请输入验证码');
        return;
      }
    } else {
      if (!password.trim()) {
        setError('请输入密码');
        return;
      }
    }

    setLoading(true);
    setError(null);

    try {
      if (loginMode === 'code') {
        await loginByCode(phone.trim(), code.trim());
      } else {
        await loginByPassword(phone.trim(), password);
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        setError(axiosErr.response?.data?.message || '登录失败');
      } else {
        setError('网络错误，请检查网络连接');
      }
    } finally {
      setLoading(false);
    }
  }, [phone, code, password, loginMode, loginByCode, loginByPassword]);

  const setPhoneWrapper = (text: string) => {
    setPhone(text);
    if (error) setError(null);
  };
  const setCodeWrapper = (text: string) => {
    setCode(text);
    if (error) setError(null);
  };
  const setPasswordWrapper = (text: string) => {
    setPassword(text);
    if (error) setError(null);
  };
  const setLoginModeWrapper = (mode: LoginMode) => {
    setLoginMode(mode);
    if (error) setError(null);
  };

  return {
    phone,
    setPhone: setPhoneWrapper,
    code,
    setCode: setCodeWrapper,
    password,
    setPassword: setPasswordWrapper,
    loginMode,
    setLoginMode: setLoginModeWrapper,
    loading,
    sendingCode,
    error,
    countdown,
    handleSendCode,
    handleLogin,
  };
}
