/**
 * useWorkOrderDetail Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';

const mockFetchOrderDetail = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { orderId: 'WO-1' } }),
}));

jest.mock('../../store/workOrderStore', () => ({
  useWorkOrderStore: () => ({
    selectedOrder: { id: 'WO-1', title: 'Test' },
    loading: false,
    error: null,
    fetchOrderDetail: mockFetchOrderDetail,
  }),
}));

jest.mock('../../services/api', () => ({
  workOrderRecordApi: {
    getRecords: jest.fn().mockResolvedValue({ data: [{ id: 1, action: 'created' }] }),
  },
  workOrderActionApi: {
    accept: jest.fn(),
    start: jest.fn(),
    complete: jest.fn(),
  },
}));

import { useWorkOrderDetail } from '../useWorkOrderDetail';
import { workOrderRecordApi, workOrderActionApi } from '../../services/api';

const mockGetRecords = workOrderRecordApi.getRecords as jest.MockedFunction<typeof workOrderRecordApi.getRecords>;
const mockAccept = workOrderActionApi.accept as jest.MockedFunction<typeof workOrderActionApi.accept>;
const mockStart = workOrderActionApi.start as jest.MockedFunction<typeof workOrderActionApi.start>;
const mockComplete = workOrderActionApi.complete as jest.MockedFunction<typeof workOrderActionApi.complete>;

describe('useWorkOrderDetail', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchOrderDetail.mockResolvedValue(undefined);
    mockGetRecords.mockResolvedValue({ data: [{ id: 1, action: 'created' }] } as never);
  });

  it('初始状态: orderId正确, 不refreshing', () => {
    const { result } = renderHook(() => useWorkOrderDetail());
    expect(result.current.orderId).toBe('WO-1');
    expect(result.current.refreshing).toBe(false);
    expect(result.current.statusUpdating).toBe(false);
  });

  it('挂载时加载详情+记录', async () => {
    renderHook(() => useWorkOrderDetail());
    await waitFor(() => expect(mockFetchOrderDetail).toHaveBeenCalledWith('WO-1'));
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledWith('WO-1'));
  });

  it('loadData(isRefresh=true) 设置refreshing', async () => {
    const { result } = renderHook(() => useWorkOrderDetail());
    await waitFor(() => expect(mockFetchOrderDetail).toHaveBeenCalled());
    mockFetchOrderDetail.mockClear();
    mockGetRecords.mockClear();
    await act(async () => { await result.current.loadData(true); });
    expect(result.current.refreshing).toBe(false);
    expect(mockFetchOrderDetail).toHaveBeenCalledWith('WO-1');
  });

  it('performAction(accept) 成功', async () => {
    mockAccept.mockResolvedValueOnce(undefined as never);
    const { result } = renderHook(() => useWorkOrderDetail());
    await waitFor(() => expect(mockFetchOrderDetail).toHaveBeenCalled());
    mockFetchOrderDetail.mockClear();
    mockGetRecords.mockClear();
    let success;
    await act(async () => { success = await result.current.performAction('accept'); });
    expect(success).toBe(true);
    expect(mockAccept).toHaveBeenCalledWith('WO-1');
    expect(mockFetchOrderDetail).toHaveBeenCalledWith('WO-1');
    expect(mockGetRecords).toHaveBeenCalledWith('WO-1');
  });

  it('performAction(execute) 调用start', async () => {
    mockStart.mockResolvedValueOnce(undefined as never);
    const { result } = renderHook(() => useWorkOrderDetail());
    await waitFor(() => expect(mockFetchOrderDetail).toHaveBeenCalled());
    let success;
    await act(async () => { success = await result.current.performAction('execute'); });
    expect(success).toBe(true);
    expect(mockStart).toHaveBeenCalledWith('WO-1');
  });

  it('performAction(complete) 调用complete', async () => {
    mockComplete.mockResolvedValueOnce(undefined as never);
    const { result } = renderHook(() => useWorkOrderDetail());
    await waitFor(() => expect(mockFetchOrderDetail).toHaveBeenCalled());
    let success;
    await act(async () => { success = await result.current.performAction('complete'); });
    expect(success).toBe(true);
    expect(mockComplete).toHaveBeenCalledWith('WO-1');
  });

  it('performAction 失败返回false', async () => {
    mockAccept.mockRejectedValueOnce(new Error('fail') as never);
    const { result } = renderHook(() => useWorkOrderDetail());
    await waitFor(() => expect(mockFetchOrderDetail).toHaveBeenCalled());
    let success;
    await act(async () => { success = await result.current.performAction('accept'); });
    expect(success).toBe(false);
    expect(result.current.statusUpdating).toBe(false);
  });
});
