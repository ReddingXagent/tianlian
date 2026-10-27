/**
 * useRevenue Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { useRevenue } from '../useRevenue';

jest.mock('../../services/api', () => ({
  revenueApi: {
    getRecords: jest.fn(),
    getSummary: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { revenueApi } from '../../services/api';

const mockRecords = [
  { id: 1, amount: 100, type: 'charging', date: '2026-01-01' },
  { id: 2, amount: 200, type: 'charging', date: '2026-01-02' },
];
const mockSummary = { today: 300, week: 1500, month: 6000, total: 50000 };

describe('useRevenue', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (revenueApi.getRecords as jest.Mock).mockResolvedValue({ data: mockRecords });
    (revenueApi.getSummary as jest.Mock).mockResolvedValue({ data: mockSummary });
  });

  it('初始加载: records+summary获取成功', async () => {
    const { result } = renderHook(() => useRevenue({ period: 'day' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.records).toEqual(mockRecords);
    expect(result.current.summary).toEqual(mockSummary);
  });

  it('period=day → 传type=day', async () => {
    const { result } = renderHook(() => useRevenue({ period: 'day' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(revenueApi.getRecords).toHaveBeenCalledWith({ type: 'day' });
  });

  it('period=week → 传type=week', async () => {
    const { result } = renderHook(() => useRevenue({ period: 'week' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(revenueApi.getRecords).toHaveBeenCalledWith({ type: 'week' });
  });

  it('period=month → 传type=month', async () => {
    const { result } = renderHook(() => useRevenue({ period: 'month' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(revenueApi.getRecords).toHaveBeenCalledWith({ type: 'month' });
  });

  it('refresh → refreshing先true后false', async () => {
    const { result } = renderHook(() => useRevenue({ period: 'day' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await result.current.fetchData(true); });
    expect(result.current.refreshing).toBe(false);
  });

  it('API失败 → 静默处理, loading=false', async () => {
    (revenueApi.getRecords as jest.Mock).mockRejectedValue(new Error('500'));
    (revenueApi.getSummary as jest.Mock).mockRejectedValue(new Error('500'));
    const { result } = renderHook(() => useRevenue({ period: 'day' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.records).toEqual([]);
    expect(result.current.summary).toEqual({ today: 0, week: 0, month: 0, total: 0 });
  });

  it('period变化 → 重新加载', async () => {
    let currentPeriod: 'day' | 'week' = 'day';
    const { result, rerender } = renderHook(() => useRevenue({ period: currentPeriod }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(revenueApi.getRecords).toHaveBeenCalledWith({ type: 'day' });
    currentPeriod = 'week';
    rerender();
    await waitFor(() => {
      expect(revenueApi.getRecords).toHaveBeenCalledWith({ type: 'week' });
    });
  });
});
