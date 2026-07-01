import { authApi, tokenStorage } from '../../services/api';
import { useAuthStore } from '../authStore';
import { User } from '../../types';

// Mock the API module
jest.mock('../../services/api', () => ({
  authApi: {
    sendCode: jest.fn(),
    loginByCode: jest.fn(),
    loginByPassword: jest.fn(),
    logout: jest.fn(),
    getProfile: jest.fn(),
    updateProfile: jest.fn(),
  },
  tokenStorage: {
    getToken: jest.fn(),
    setToken: jest.fn(),
    removeToken: jest.fn(),
  },
}));

const mockUser: User = {
  id: 1,
  phone: '13800138000',
  nickname: '测试用户',
  balance: 100.5,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

const mockLoginResponse = {
  data: {
    token: 'mock-jwt-token',
    user: mockUser,
  },
};

describe('authStore', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Reset store state
    useAuthStore.setState({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: true,
    });
  });

  describe('loginByCode', () => {
    it('should login successfully with phone and code', async () => {
      (authApi.loginByCode as jest.Mock).mockResolvedValue(mockLoginResponse);

      await useAuthStore.getState().loginByCode('13800138000', '123456');

      expect(authApi.loginByCode).toHaveBeenCalledWith({
        phone: '13800138000',
        code: '123456',
      });
      expect(tokenStorage.setToken).toHaveBeenCalledWith('mock-jwt-token');
      const state = useAuthStore.getState();
      expect(state.token).toBe('mock-jwt-token');
      expect(state.user).toEqual(mockUser);
      expect(state.isAuthenticated).toBe(true);
      expect(state.isLoading).toBe(false);
    });

    it('should handle login failure', async () => {
      const error = new Error('验证码错误');
      (authApi.loginByCode as jest.Mock).mockRejectedValue(error);

      await expect(
        useAuthStore.getState().loginByCode('13800138000', '000000')
      ).rejects.toThrow('验证码错误');
    });
  });

  describe('loginByPassword', () => {
    it('should login successfully with phone and password', async () => {
      (authApi.loginByPassword as jest.Mock).mockResolvedValue(mockLoginResponse);

      await useAuthStore.getState().loginByPassword('13800138000', 'password123');

      expect(authApi.loginByPassword).toHaveBeenCalledWith({
        phone: '13800138000',
        password: 'password123',
      });
      expect(tokenStorage.setToken).toHaveBeenCalledWith('mock-jwt-token');
      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(true);
    });
  });

  describe('logout', () => {
    it('should clear auth state on logout', async () => {
      // Setup logged in state
      useAuthStore.setState({
        token: 'mock-token',
        user: mockUser,
        isAuthenticated: true,
        isLoading: false,
      });
      (authApi.logout as jest.Mock).mockResolvedValue({ data: null });

      await useAuthStore.getState().logout();

      expect(authApi.logout).toHaveBeenCalled();
      expect(tokenStorage.removeToken).toHaveBeenCalled();
      const state = useAuthStore.getState();
      expect(state.token).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
    });

    it('should clear local state even if logout API fails', async () => {
      useAuthStore.setState({
        token: 'mock-token',
        user: mockUser,
        isAuthenticated: true,
        isLoading: false,
      });
      (authApi.logout as jest.Mock).mockRejectedValue(new Error('网络错误'));

      await useAuthStore.getState().logout();

      expect(tokenStorage.removeToken).toHaveBeenCalled();
      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(false);
    });
  });

  describe('checkAuth', () => {
    it('should set unauthenticated if no token', async () => {
      (tokenStorage.getToken as jest.Mock).mockResolvedValue(null);

      await useAuthStore.getState().checkAuth();

      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(false);
    });

    it('should restore session if valid token exists', async () => {
      (tokenStorage.getToken as jest.Mock).mockResolvedValue('valid-token');
      (authApi.getProfile as jest.Mock).mockResolvedValue({ data: mockUser });

      await useAuthStore.getState().checkAuth();

      expect(authApi.getProfile).toHaveBeenCalled();
      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(true);
      expect(state.user).toEqual(mockUser);
      expect(state.isLoading).toBe(false);
    });

    it('should clear token if profile fetch fails', async () => {
      (tokenStorage.getToken as jest.Mock).mockResolvedValue('expired-token');
      (authApi.getProfile as jest.Mock).mockRejectedValue(new Error('401'));

      await useAuthStore.getState().checkAuth();

      expect(tokenStorage.removeToken).toHaveBeenCalled();
      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(false);
    });
  });

  describe('setUser', () => {
    it('should update user in store', () => {
      useAuthStore.getState().setUser(mockUser);
      expect(useAuthStore.getState().user).toEqual(mockUser);
    });
  });
});