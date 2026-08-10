import { act } from '@testing-library/react-native';
import { useAuthStore } from '../authStore';
import { authApi, tokenStorage } from '../../services/api';
import { User, AuthMe } from '../../types';

// Mock the API module
jest.mock('../../services/api', () => ({
  tokenStorage: {
    getToken: jest.fn(),
    setToken: jest.fn(),
    removeToken: jest.fn(),
  },
  authApi: {
    login: jest.fn(),
    logout: jest.fn(),
    getProfile: jest.fn(),
  },
}));

const TEST_TOKEN = 'test-jwt-token-12345';
const TEST_AUTH_ME: AuthMe = {
  id: 1,
  username: 'admin',
  realName: '管理员',
  role: 'admin',
  permissions: ['read', 'write'],
  teamType: null,
  teamId: null,
};
const TEST_USER: User = {
  id: 1,
  username: 'admin',
  nickname: '管理员',
  email: 'admin@test.com',
  phone: '13800138000',
  role: 'admin',
  stationIds: [1, 2],
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
};

describe('useAuthStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useAuthStore.setState({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: true,
    });
    jest.clearAllMocks();
  });

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useAuthStore.getState();
      expect(state.token).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(true);
    });
  });

  describe('login', () => {
    it('should set token, user and isAuthenticated on successful login', async () => {
      const loginResponse = {
        data: { token: TEST_TOKEN, user: TEST_USER },
      };
      (authApi.login as jest.Mock).mockResolvedValue(loginResponse);

      await act(async () => {
        await useAuthStore.getState().login('admin', '123456');
      });

      const state = useAuthStore.getState();
      expect(authApi.login).toHaveBeenCalledWith({ username: 'admin', password: '123456' });
      expect(tokenStorage.setToken).toHaveBeenCalledWith(TEST_TOKEN);
      expect(state.token).toBe(TEST_TOKEN);
      expect(state.user).toEqual(TEST_USER);
      expect(state.isAuthenticated).toBe(true);
      expect(state.isLoading).toBe(false);
    });

    it('should propagate login failure', async () => {
      const error = new Error('Invalid credentials');
      (authApi.login as jest.Mock).mockRejectedValue(error);

      await expect(
        act(async () => {
          await useAuthStore.getState().login('admin', 'wrong-password');
        })
      ).rejects.toThrow('Invalid credentials');

      const state = useAuthStore.getState();
      expect(state.token).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(tokenStorage.setToken).not.toHaveBeenCalled();
    });
  });

  describe('logout', () => {
    it('should clear token, user and set isAuthenticated to false', async () => {
      // First, set initial authenticated state
      useAuthStore.setState({
        token: TEST_TOKEN,
        user: TEST_USER,
        isAuthenticated: true,
        isLoading: false,
      });

      (authApi.logout as jest.Mock).mockResolvedValue({ data: null });

      await act(async () => {
        await useAuthStore.getState().logout();
      });

      const state = useAuthStore.getState();
      expect(authApi.logout).toHaveBeenCalled();
      expect(tokenStorage.removeToken).toHaveBeenCalled();
      expect(state.token).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(false);
    });

    it('should clear state even if logout API fails', async () => {
      useAuthStore.setState({
        token: TEST_TOKEN,
        user: TEST_USER,
        isAuthenticated: true,
        isLoading: false,
      });

      (authApi.logout as jest.Mock).mockRejectedValue(new Error('Network error'));

      await act(async () => {
        await useAuthStore.getState().logout();
      });

      const state = useAuthStore.getState();
      // Should still clear local state even if API fails
      expect(tokenStorage.removeToken).toHaveBeenCalled();
      expect(state.token).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(false);
    });
  });

  describe('checkAuth', () => {
    it('should set authenticated state when token exists and profile loads', async () => {
      (tokenStorage.getToken as jest.Mock).mockResolvedValue(TEST_TOKEN);
      (authApi.getProfile as jest.Mock).mockResolvedValue({ data: TEST_AUTH_ME });

      await act(async () => {
        await useAuthStore.getState().checkAuth();
      });

      const state = useAuthStore.getState();
      expect(tokenStorage.getToken).toHaveBeenCalled();
      expect(authApi.getProfile).toHaveBeenCalled();
      expect(state.token).toBe(TEST_TOKEN);
      // AuthMe is mapped to User via authMeToUser
      expect(state.user).toEqual({
        id: 1,
        username: 'admin',
        nickname: '管理员',
        email: '',
        phone: '',
        role: 'admin',
        avatar: undefined,
        stationIds: [],
        createdAt: '',
        updatedAt: '',
      });
      expect(state.isAuthenticated).toBe(true);
      expect(state.isLoading).toBe(false);
    });

    it('should set unauthenticated state when no token exists', async () => {
      (tokenStorage.getToken as jest.Mock).mockResolvedValue(null);

      await act(async () => {
        await useAuthStore.getState().checkAuth();
      });

      const state = useAuthStore.getState();
      expect(state.token).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(false);
      expect(authApi.getProfile).not.toHaveBeenCalled();
    });

    it('should clear state when profile fetch fails', async () => {
      (tokenStorage.getToken as jest.Mock).mockResolvedValue(TEST_TOKEN);
      (authApi.getProfile as jest.Mock).mockRejectedValue(new Error('Token expired'));

      await act(async () => {
        await useAuthStore.getState().checkAuth();
      });

      const state = useAuthStore.getState();
      expect(tokenStorage.removeToken).toHaveBeenCalled();
      expect(state.token).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(false);
    });
  });

  describe('setUser', () => {
    it('should update user without changing other state', () => {
      useAuthStore.setState({
        token: TEST_TOKEN,
        user: TEST_USER,
        isAuthenticated: true,
        isLoading: false,
      });

      const updatedUser: User = { ...TEST_USER, nickname: '超级管理员' };
      useAuthStore.getState().setUser(updatedUser);

      const state = useAuthStore.getState();
      expect(state.user?.nickname).toBe('超级管理员');
      expect(state.token).toBe(TEST_TOKEN);
      expect(state.isAuthenticated).toBe(true);
    });
  });
});
