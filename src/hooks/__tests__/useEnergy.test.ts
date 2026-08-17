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
  totalEnergy: 15230.5,
  todayEnergy: 320.8,
  monthEnergy: 4500.2,
  yearEnergy: 15230.5,
  unit: 'kWh',
  trend: [],
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
});
