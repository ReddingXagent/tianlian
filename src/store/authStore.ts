import { create } from 'zustand';
import { User } from '../types';
import { authApi, tokenStorage } from '../services/api';

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  setUser: (user: User) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isAuthenticated: false,
  isLoading: true,

  login: async (username: string, password: string) => {
    const response = await authApi.login({ username, password });
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