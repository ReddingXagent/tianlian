/**
 * useWorkOrderList Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';

const mockFetchOrders = jest.fn();

jest.mock('../../store/workOrderStore', () => ({
  useWorkOrderStore: () => ({
    orders: [{ id: 1, title: 'WO1' }],
    loading: false,
    error: null,
    total: 1,
    fetchOrders: mockFetchOrders,
  }),
}));

import { useWorkOrderList } from '../useWorkOrderList';

describe('useWorkOrderList', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchOrders.mockResolvedValue(undefined);
  });

  it('初始状态: filter=all, 不refreshing', () => {
    const { result } = renderHook(() => useWorkOrderList());
    expect(result.current.activeFilter).toBe('all');
    expect(result.current.refreshing).toBe(false);
    expect(result.current.orders).toEqual([{ id: 1, title: 'WO1' }]);
  });

  it('挂载时自动加载(status=undefined)', async () => {
    renderHook(() => useWorkOrderList());
    await waitFor(() => expect(mockFetchOrders).toHaveBeenCalledWith(undefined));
  });

  it('切换filter: 传status参数', async () => {
    const { result } = renderHook(() => useWorkOrderList());
    await waitFor(() => expect(mockFetchOrders).toHaveBeenCalled());
    mockFetchOrders.mockClear();
    act(() => result.current.setActiveFilter('pending'));
    await waitFor(() => expect(mockFetchOrders).toHaveBeenCalledWith({ status: 'pending' }));
  });

  it('loadData(isRefresh=true) 设置refreshing', async () => {
    const { result } = renderHook(() => useWorkOrderList());
    await waitFor(() => expect(mockFetchOrders).toHaveBeenCalled());
    mockFetchOrders.mockClear();
    await act(async () => { await result.current.loadData(true); });
    expect(result.current.refreshing).toBe(false);
  });

  it('loadData(isRefresh=false) 不设置refreshing', async () => {
    const { result } = renderHook(() => useWorkOrderList());
    await waitFor(() => expect(mockFetchOrders).toHaveBeenCalled());
    mockFetchOrders.mockClear();
    await act(async () => { await result.current.loadData(false); });
    expect(result.current.refreshing).toBe(false);
  });
});
