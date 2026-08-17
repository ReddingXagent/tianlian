/**
 * useWorkOrderTransfer Hook 测试
 */
import { renderHook, act } from '@testing-library/react-native';

const mockTransferOrder = jest.fn();
const mockUrgeOrder = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { orderId: 'WO-1' } }),
}));

jest.mock('../../store/workOrderEnhancedStore', () => ({
  useWorkOrderEnhancedStore: () => ({
    transferring: false,
    transferError: null,
    transferOrder: mockTransferOrder,
    urgeOrder: mockUrgeOrder,
  }),
}));

import { useWorkOrderTransfer } from '../useWorkOrderTransfer';

describe('useWorkOrderTransfer', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('初始状态: orderId正确', () => {
    const { result } = renderHook(() => useWorkOrderTransfer());
    expect(result.current.orderId).toBe('WO-1');
    expect(result.current.assigneeId).toBe('');
    expect(result.current.reason).toBe('');
    expect(result.current.localError).toBeNull();
  });

  it('set字段更新值', () => {
    const { result } = renderHook(() => useWorkOrderTransfer());
    act(() => {
      result.current.setAssigneeId('5');
      result.current.setReason('test reason');
    });
    expect(result.current.assigneeId).toBe('5');
    expect(result.current.reason).toBe('test reason');
  });

  it('空assigneeId → localError', async () => {
    const { result } = renderHook(() => useWorkOrderTransfer());
    let success;
    await act(async () => { success = await result.current.handleTransfer(); });
    expect(success).toBe(false);
    expect(result.current.localError).toBe('请输入有效的运维人员ID');
    expect(mockTransferOrder).not.toHaveBeenCalled();
  });

  it('非数字assigneeId → localError', async () => {
    const { result } = renderHook(() => useWorkOrderTransfer());
    act(() => result.current.setAssigneeId('abc'));
    let success;
    await act(async () => { success = await result.current.handleTransfer(); });
    expect(success).toBe(false);
    expect(result.current.localError).toBe('请输入有效的运维人员ID');
  });

  it('空reason → localError', async () => {
    const { result } = renderHook(() => useWorkOrderTransfer());
    act(() => result.current.setAssigneeId('5'));
    let success;
    await act(async () => { success = await result.current.handleTransfer(); });
    expect(success).toBe(false);
    expect(result.current.localError).toBe('请输入转派原因');
  });

  it('成功转派: 返回true', async () => {
    mockTransferOrder.mockResolvedValueOnce({ id: 1 });
    const { result } = renderHook(() => useWorkOrderTransfer());
    act(() => {
      result.current.setAssigneeId('5');
      result.current.setReason('reassign');
    });
    let success;
    await act(async () => { success = await result.current.handleTransfer(); });
    expect(success).toBe(true);
    expect(mockTransferOrder).toHaveBeenCalledWith('WO-1', 5, 'reassign');
  });

  it('转派失败: 返回false', async () => {
    mockTransferOrder.mockResolvedValueOnce(null);
    const { result } = renderHook(() => useWorkOrderTransfer());
    act(() => {
      result.current.setAssigneeId('5');
      result.current.setReason('reassign');
    });
    let success;
    await act(async () => { success = await result.current.handleTransfer(); });
    expect(success).toBe(false);
  });

  it('handleUrge: 调用urgeOrder', async () => {
    mockUrgeOrder.mockResolvedValueOnce({ id: 1 });
    const { result } = renderHook(() => useWorkOrderTransfer());
    let success;
    await act(async () => { success = await result.current.handleUrge(); });
    expect(success).toBe(true);
    expect(mockUrgeOrder).toHaveBeenCalledWith('WO-1', '请尽快处理');
  });

  it('handleUrge: 失败返回false', async () => {
    mockUrgeOrder.mockResolvedValueOnce(null);
    const { result } = renderHook(() => useWorkOrderTransfer());
    let success;
    await act(async () => { success = await result.current.handleUrge(); });
    expect(success).toBe(false);
  });

  it('clearError 清除localError', async () => {
    const { result } = renderHook(() => useWorkOrderTransfer());
    await act(async () => { await result.current.handleTransfer(); });
    expect(result.current.localError).not.toBeNull();
    act(() => result.current.clearError());
    expect(result.current.localError).toBeNull();
  });
});
