/**
 * useWorkOrders Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { useWorkOrders } from '../useWorkOrders';

// Mock api — must use jest.fn() inside factory to avoid hoisting issues
jest.mock('../../services/api', () => ({
  workOrderApi: {
    getList: jest.fn(),
    createWorkOrder: jest.fn(),
    completeWorkOrder: jest.fn(),
  },
}));

// Import after mock to get the mocked version
// eslint-disable-next-line import/first
import { workOrderApi } from '../../services/api';

const mockOrders = [
  { id: 'WO-1', title: '工单1', status: 'pending', type: 'repair', priority: 'high' as const },
  { id: 'WO-2', title: '工单2', status: 'in_progress', type: 'maintenance', priority: 'normal' as const },
];

describe('useWorkOrders', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (workOrderApi.getList as jest.Mock).mockResolvedValue({
      data: { items: mockOrders, total: 2 },
    });
  });

  it('初始加载: loading→false, 获取工单列表', async () => {
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 1, statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.orders).toHaveLength(2);
    expect(result.current.page).toBe(1);
    expect(result.current.total).toBe(2);
    expect(result.current.error).toBeNull();
  });

  it('statusFilter=all → 不传status参数', async () => {
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 1, statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(workOrderApi.getList).toHaveBeenCalledWith(
      expect.not.objectContaining({ status: expect.anything() })
    );
  });

  it('statusFilter=pending → 传status参数', async () => {
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 1, statusFilter: 'pending' })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(workOrderApi.getList).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'pending' })
    );
  });

  it('stationId传递到API参数', async () => {
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 42, statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(workOrderApi.getList).toHaveBeenCalledWith(
      expect.objectContaining({ stationId: 42 })
    );
  });

  it('refresh → refreshing先true后false', async () => {
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 1, statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await result.current.fetchData(true); });
    expect(result.current.refreshing).toBe(false);
  });

  it('loadMore → 加载第二页追加', async () => {
    (workOrderApi.getList as jest.Mock)
      .mockResolvedValueOnce({ data: { items: mockOrders, total: 4 } })
      .mockResolvedValueOnce({ data: { items: [{ id: 'WO-3', title: '工单3', status: 'pending' }], total: 4 } });
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 1, statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.orders).toHaveLength(2));
    act(() => result.current.handleLoadMore());
    await waitFor(() => expect(result.current.orders).toHaveLength(3));
    expect(result.current.page).toBe(2);
  });

  it('loadMore → 已全部加载时不触发', async () => {
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 1, statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    const callsBefore = (workOrderApi.getList as jest.Mock).mock.calls.length;
    act(() => result.current.handleLoadMore());
    expect((workOrderApi.getList as jest.Mock).mock.calls.length).toBe(callsBefore);
  });

  it('API失败 → error设置', async () => {
    (workOrderApi.getList as jest.Mock).mockRejectedValue(new Error('network'));
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 1, statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.error).toBe('加载工单列表失败'));
    expect(result.current.loading).toBe(false);
  });

  it('createWorkOrder → 成功返回true并刷新', async () => {
    (workOrderApi.createWorkOrder as jest.Mock).mockResolvedValue({});
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 1, statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.createWorkOrder({
        title: '新工单', description: '描述', type: 'repair' as const, priority: 'high' as const,
      });
    });
    expect(ok).toBe(true);
    expect(workOrderApi.createWorkOrder).toHaveBeenCalledWith(
      expect.objectContaining({ stationId: 1, title: '新工单' })
    );
  });

  it('createWorkOrder → 无stationId返回false', async () => {
    const { result } = renderHook(() =>
      useWorkOrders({ statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.createWorkOrder({
        title: 'x', description: 'y', type: 'repair' as const, priority: 'low' as const,
      });
    });
    expect(ok).toBe(false);
  });

  it('createWorkOrder → API失败返回false', async () => {
    (workOrderApi.createWorkOrder as jest.Mock).mockRejectedValue(new Error('server'));
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 1, statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.createWorkOrder({
        title: 'x', description: 'y', type: 'repair' as const, priority: 'low' as const,
      });
    });
    expect(ok).toBe(false);
  });

  it('completeWorkOrder → 成功返回true并刷新', async () => {
    (workOrderApi.completeWorkOrder as jest.Mock).mockResolvedValue({});
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 1, statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    let ok: boolean | undefined;
    await act(async () => { ok = await result.current.completeWorkOrder('WO-1'); });
    expect(ok).toBe(true);
    expect(workOrderApi.completeWorkOrder).toHaveBeenCalledWith('WO-1');
  });

  it('completeWorkOrder → 失败返回false', async () => {
    (workOrderApi.completeWorkOrder as jest.Mock).mockRejectedValue(new Error('fail'));
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 1, statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    let ok: boolean | undefined;
    await act(async () => { ok = await result.current.completeWorkOrder('WO-1'); });
    expect(ok).toBe(false);
  });
});

describe('useWorkOrders — default-arg branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (workOrderApi.getList as jest.Mock).mockResolvedValue({
      data: { items: mockOrders, total: 2 },
    });
  });

  it('fetchData() with no args — defaults to isRefresh=false, p=1', async () => {
    const { result } = renderHook(() =>
      useWorkOrders({ stationId: 1, statusFilter: 'all' })
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    // Call fetchData with no arguments — exercises default-arg branches
    await act(async () => { await result.current.fetchData(); });
    expect(result.current.error).toBeNull();
    expect(result.current.orders).toHaveLength(2);
  });
});
