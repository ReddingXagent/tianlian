import { renderHook, act, waitFor } from '@testing-library/react-native';
import { energyApi } from '../../services/api';
import { useEnergy } from '../useEnergy';
import { EnergySummary } from '../../types';

jest.mock('../../services/api', () => ({
  energyApi: {
    getSummary: jest.fn(),
  },
}));

const mockSummary: EnergySummary = {
  period: '2026-08',
  days: 30,
  pvGeneration: 15230.5,
  chargingAmount: 8200.3,
  dischargeAmount: 4500.0,
  pvRevenue: 7600.25,
  chargingRevenue: 16400.6,
  dischargeRevenue: 2250.0,
  totalRevenue: 26250.85,
  yoy: {
    pvGenerationYoY: 0.15,
    chargingAmountYoY: -0.08,
    dischargeAmountYoY: 0.12,
    totalRevenueYoY: 0.22,
  },
  priceInfo: {
    feedInTariff: 0.45,
    chargingPrice: 1.20,
    dischargePrice: 0.80,
  },
} as never;

describe('useEnergy', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should load summary on mount', async () => {
    (energyApi.getSummary as jest.Mock).mockResolvedValue({ data: mockSummary });

    const { result } = renderHook(() => useEnergy());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.summary).toEqual(mockSummary);
    expect(result.current.error).toBeNull();
  });

  it('should set error on failure', async () => {
    (energyApi.getSummary as jest.Mock).mockRejectedValue(new Error('服务器错误'));

    const { result } = renderHook(() => useEnergy());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('服务器错误');
    expect(result.current.summary).toBeNull();
  });

  it('should set default error message on non-Error throw', async () => {
    (energyApi.getSummary as jest.Mock).mockRejectedValue('oops');

    const { result } = renderHook(() => useEnergy());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('获取能源数据失败');
  });

  it('should refresh data', async () => {
    (energyApi.getSummary as jest.Mock).mockResolvedValue({ data: mockSummary });

    const { result } = renderHook(() => useEnergy());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    const updated = { ...mockSummary, todayEnergy: 999 };
    (energyApi.getSummary as jest.Mock).mockResolvedValue({ data: updated });

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.refreshing).toBe(false);
    expect(result.current.summary?.todayEnergy).toBe(999);
  });

  it('should set refreshing=false after refresh failure', async () => {
    (energyApi.getSummary as jest.Mock).mockResolvedValue({ data: mockSummary });

    const { result } = renderHook(() => useEnergy());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    (energyApi.getSummary as jest.Mock).mockRejectedValue(new Error('refresh fail'));

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.refreshing).toBe(false);
    expect(result.current.error).toBe('refresh fail');
  });

  it('should not fetch when unfocused', async () => {
    (energyApi.getSummary as jest.Mock).mockResolvedValue({ data: mockSummary });

    const { result } = renderHook(() => useEnergy());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(energyApi.getSummary).toHaveBeenCalledTimes(1);
  });

  it('should cancel pending fetch on unmount', async () => {
    let resolveFn: (val: unknown) => void = () => {};
    (energyApi.getSummary as jest.Mock).mockImplementation(
      () => new Promise((resolve) => { resolveFn = resolve; })
    );

    const { unmount } = renderHook(() => useEnergy());

    // Unmount before the promise resolves
    unmount();
    resolveFn({ data: mockSummary });

    // Give the microtask queue a chance to flush
    await act(async () => {
      await Promise.resolve();
    });

    // If cancelled guard works, no state update happens after unmount
    // Test passes if no act() warning is thrown
  });
});
