import { create } from 'zustand';
import { User } from '../types';
import { authApi, setUnauthorizedHandler, tokenStorage } from '../services/api';

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  loginByCode: (phone: string, code: string) => Promise<void>;
  loginByPassword: (phone: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  setUser: (user: User) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isAuthenticated: false,
  isLoading: true,

  loginByCode: async (phone: string, code: string) => {
    const response = await authApi.loginByCode({ phone, code });
    const { token, user } = response.data;
    await tokenStorage.setToken(token);
    set({
      token,
      user,
      isAuthenticated: true,
      isLoading: false,
    });
  },

  loginByPassword: async (phone: string, password: string) => {
    const response = await authApi.loginByPassword({ phone, password });
    const { token, user } = response.data;
    await tokenStorage.setToken(token);
    set({
      token,
      user,
      isAuthenticated: true,
      isLoading: false,
    });
  },

  logout: async () => {
    try {
      await authApi.logout();
    } catch {
      // 即使登出API失败也清除本地状态
    }
    await tokenStorage.removeToken();
    set({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  },

  checkAuth: async () => {
    try {
      const token = await tokenStorage.getToken();
      if (!token) {
        set({ token: null, user: null, isAuthenticated: false, isLoading: false });
        return;
      }
      const response = await authApi.getProfile();
      set({
        token,
        user: response.data,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch {
      await tokenStorage.removeToken();
      set({
        token: null,
        user: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },

  setUser: (user: User) => {
    set({ user });
  },
}));

// token 失效(401)时同步清空登录态; 用回调注册而非反向 import, 避免循环依赖
setUnauthorizedHandler(() => {
  useAuthStore.setState({
    token: null,
    user: null,
    isAuthenticated: false,
    isLoading: false,
  });
});