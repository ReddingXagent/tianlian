import { renderHook, act, waitFor } from '@testing-library/react-native';
import { authApi, walletApi } from '../../services/api';
import { useAuthStore } from '../../store/authStore';
import { useWallet } from '../useWallet';
import { WalletRecord } from '../../types';

jest.mock('../../services/api', () => ({
  authApi: {
    getProfile: jest.fn(),
  },
  walletApi: {
    getRecords: jest.fn(),
    recharge: jest.fn(),
  },
}));

jest.mock('../../store/authStore', () => ({
  useAuthStore: jest.fn(),
}));

const mockSetUser = jest.fn();

const mockRecord = (id: number): WalletRecord => ({
  id,
  type: 'recharge',
  amount: 100,
  balance: 500,
  description: '充值',
  createdAt: '2026-08-01T10:00:00Z',
} as never);

const mockPage = (items: WalletRecord[], total: number, page: number) => ({
  data: { items, total, page },
});

describe('useWallet', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (useAuthStore as jest.Mock).mockReturnValue({ setUser: mockSetUser });
  });

  it('should load records and profile on mount', async () => {
    (walletApi.getRecords as jest.Mock).mockResolvedValue(
      mockPage([mockRecord(1)], 1, 1)
    );
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: { id: 1 } });

    const { result } = renderHook(() => useWallet());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.records).toHaveLength(1);
    expect(result.current.error).toBeNull();
    expect(result.current.hasMore).toBe(false);
  });

  it('should set error on records load failure', async () => {
    (walletApi.getRecords as jest.Mock).mockRejectedValue(new Error('服务器错误'));
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: {} });

    const { result } = renderHook(() => useWallet());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('服务器错误');
  });

  it('should set default error on non-Error throw', async () => {
    (walletApi.getRecords as jest.Mock).mockRejectedValue('fail');
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: {} });

    const { result } = renderHook(() => useWallet());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('获取交易记录失败');
  });

  it('should set hasMore when items < total', async () => {
    (walletApi.getRecords as jest.Mock).mockResolvedValue(
      mockPage([mockRecord(1)], 5, 1)
    );
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: {} });

    const { result } = renderHook(() => useWallet());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.hasMore).toBe(true);
  });

  it('should load more records with dedupe', async () => {
    (walletApi.getRecords as jest.Mock)
      .mockResolvedValueOnce(mockPage([mockRecord(1)], 2, 1))
      .mockResolvedValueOnce(mockPage([mockRecord(1), mockRecord(2)], 2, 2));
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: {} });

    const { result } = renderHook(() => useWallet());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    await act(async () => {
      await result.current.loadMoreRecords();
    });

    expect(result.current.records).toHaveLength(2); // deduped
    expect(result.current.hasMore).toBe(false);
  });

  it('should not load more when hasMore is false', async () => {
    (walletApi.getRecords as jest.Mock).mockResolvedValue(
      mockPage([mockRecord(1)], 1, 1)
    );
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: {} });

    const { result } = renderHook(() => useWallet());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    await act(async () => {
      await result.current.loadMoreRecords();
    });

    expect(walletApi.getRecords).toHaveBeenCalledTimes(1);
  });

  it('should silently handle loadMore failure', async () => {
    (walletApi.getRecords as jest.Mock).mockResolvedValue(
      mockPage([mockRecord(1)], 5, 1)
    );
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: {} });

    const { result } = renderHook(() => useWallet());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    (walletApi.getRecords as jest.Mock).mockRejectedValue(new Error('fail'));

    await act(async () => {
      await result.current.loadMoreRecords();
    });

    expect(result.current.loadingMore).toBe(false);
    expect(result.current.records).toHaveLength(1);
  });

  it('should handle refresh', async () => {
    (walletApi.getRecords as jest.Mock).mockResolvedValue(
      mockPage([mockRecord(1)], 1, 1)
    );
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: {} });

    const { result } = renderHook(() => useWallet());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    await act(async () => {
      await result.current.handleRefresh();
    });

    expect(result.current.refreshing).toBe(false);
  });

  it('should recharge successfully', async () => {
    (walletApi.getRecords as jest.Mock).mockResolvedValue(
      mockPage([mockRecord(1)], 1, 1)
    );
    (walletApi.recharge as jest.Mock).mockResolvedValue({});
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: {} });

    const { result } = renderHook(() => useWallet());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let rechargeResult: boolean;
    await act(async () => {
      rechargeResult = await result.current.recharge(50);
    });

    expect(rechargeResult).toBe(true);
    expect(walletApi.recharge).toHaveBeenCalledWith(50);
    expect(result.current.recharging).toBe(false);
  });

  it('should handle recharge failure', async () => {
    (walletApi.getRecords as jest.Mock).mockResolvedValue(
      mockPage([mockRecord(1)], 1, 1)
    );
    (walletApi.recharge as jest.Mock).mockRejectedValue(new Error('fail'));
    (authApi.getProfile as jest.Mock).mockResolvedValue({ data: {} });

    const { result } = renderHook(() => useWallet());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let rechargeResult: boolean;
    await act(async () => {
      rechargeResult = await result.current.recharge(50);
    });

    expect(rechargeResult).toBe(false);
    expect(result.current.recharging).toBe(false);
  });
});
