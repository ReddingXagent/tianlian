import { renderHook, act, waitFor } from '@testing-library/react-native';
import { authApi, statsApi } from '../../services/api';
import { useAuthStore } from '../../store/authStore';
import { useProfile } from '../useProfile';

jest.mock('../../services/api', () => ({
  authApi: {
    getProfile: jest.fn(),
  },
  statsApi: {
    getUserStats: jest.fn(),
  },
}));

jest.mock('../../store/authStore', () => ({
  useAuthStore: jest.fn(),
}));

const mockSetUser = jest.fn();

const mockStats = {
  totalOrders: 10,
  totalEnergy: 500.5,
  totalAmount: 300,
} as never;

const mockUser = {
  id: 1,
  name: '测试用户',
  phone: '13800138000',
} as never;

describe('useProfile', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (useAuthStore as jest.Mock).mockReturnValue({ setUser: mockSetUser });
  });

  it('should load stats and profile on mount', async () => {
    (statsApi.getUserStats as jest.Mock).mockResolvedValue({ data: mockStats });
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: mockUser });

    const { result } = renderHook(() => useProfile());

    await waitFor(() => {
      expect(result.current.stats).toEqual(mockStats);
    });

    expect(statsApi.getUserStats).toHaveBeenCalled();
    expect(authApi.getProfile).toHaveBeenCalled();
  });

  it('should silently handle stats load failure', async () => {
    (statsApi.getUserStats as jest.Mock).mockRejectedValue(new Error('fail'));
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: mockUser });

    const { result } = renderHook(() => useProfile());

    await waitFor(() => {
      expect(authApi.getProfile).toHaveBeenCalled();
    });

    expect(result.current.stats).toBeNull();
  });

  it('should silently handle profile refresh failure', async () => {
    (statsApi.getUserStats as jest.Mock).mockResolvedValue({ data: mockStats });
    (authApi.getProfile as jest.Mock).mockRejectedValue(new Error('fail'));

    const { result } = renderHook(() => useProfile());

    await waitFor(() => {
      expect(result.current.stats).toEqual(mockStats);
    });

    // profile error is silent
    expect(result.current.stats).toEqual(mockStats);
  });

  it('should reload stats on loadStats call', async () => {
    (statsApi.getUserStats as jest.Mock).mockResolvedValue({ data: mockStats });
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: mockUser });

    const { result } = renderHook(() => useProfile());

    await waitFor(() => {
      expect(result.current.stats).toEqual(mockStats);
    });

    const updated = { ...mockStats, totalOrders: 20 } as never;
    (statsApi.getUserStats as jest.Mock).mockResolvedValue({ data: updated });

    await act(async () => {
      await result.current.loadStats();
    });

    expect(result.current.stats?.totalOrders).toBe(20);
  });

  it('should reload profile on refreshProfile call', async () => {
    (statsApi.getUserStats as jest.Mock).mockResolvedValue({ data: mockStats });
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: mockUser });

    const { result } = renderHook(() => useProfile());

    await waitFor(() => {
      expect(result.current.stats).toEqual(mockStats);
    });

    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: { ...mockUser, name: '新名字' } as never });

    await act(async () => {
      await result.current.refreshProfile();
    });

    expect(authApi.getProfile).toHaveBeenCalledTimes(2);
  });
});
