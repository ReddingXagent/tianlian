/**
 * useWorkOrderCreate Hook 测试
 */
import { renderHook, act } from '@testing-library/react-native';

const mockCreateOrder = jest.fn();

jest.mock('../../store/workOrderEnhancedStore', () => ({
  useWorkOrderEnhancedStore: () => ({
    creating: false,
    createError: null,
    createOrder: mockCreateOrder,
  }),
}));

import { useWorkOrderCreate } from '../useWorkOrderCreate';

describe('useWorkOrderCreate', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('初始状态: 默认值', () => {
    const { result } = renderHook(() => useWorkOrderCreate());
    expect(result.current.title).toBe('');
    expect(result.current.description).toBe('');
    expect(result.current.stationId).toBe('');
    expect(result.current.type).toBe('repair');
    expect(result.current.priority).toBe('normal');
    expect(result.current.localError).toBeNull();
  });

  it('set字段更新值', () => {
    const { result } = renderHook(() => useWorkOrderCreate());
    act(() => {
      result.current.setTitle('Test WO');
      result.current.setDescription('Desc');
      result.current.setStationId('123');
      result.current.setType('inspection');
      result.current.setPriority('urgent');
    });
    expect(result.current.title).toBe('Test WO');
    expect(result.current.description).toBe('Desc');
    expect(result.current.stationId).toBe('123');
    expect(result.current.type).toBe('inspection');
    expect(result.current.priority).toBe('urgent');
  });

  it('空标题 → localError', async () => {
    const { result } = renderHook(() => useWorkOrderCreate());
    let ret;
    await act(async () => { ret = await result.current.handleSubmit(); });
    expect(result.current.localError).toBe('请输入工单标题');
    expect(ret).toBeNull();
    expect(mockCreateOrder).not.toHaveBeenCalled();
  });

  it('空描述 → localError', async () => {
    const { result } = renderHook(() => useWorkOrderCreate());
    act(() => result.current.setTitle('Test'));
    let ret;
    await act(async () => { ret = await result.current.handleSubmit(); });
    expect(result.current.localError).toBe('请输入工单描述');
    expect(ret).toBeNull();
  });

  it('无效站点ID → localError', async () => {
    const { result } = renderHook(() => useWorkOrderCreate());
    act(() => {
      result.current.setTitle('Test');
      result.current.setDescription('Desc');
      result.current.setStationId('abc');
    });
    let ret;
    await act(async () => { ret = await result.current.handleSubmit(); });
    expect(result.current.localError).toBe('请输入有效的站点ID');
    expect(ret).toBeNull();
  });

  it('成功提交: 返回order + resetForm', async () => {
    const mockOrder = { id: 1, title: 'Test' };
    mockCreateOrder.mockResolvedValueOnce(mockOrder);
    const { result } = renderHook(() => useWorkOrderCreate());
    act(() => {
      result.current.setTitle('Test');
      result.current.setDescription('Desc');
      result.current.setStationId('123');
    });
    let ret;
    await act(async () => { ret = await result.current.handleSubmit(); });
    expect(mockCreateOrder).toHaveBeenCalledWith({
      title: 'Test',
      description: 'Desc',
      stationId: 123,
      type: 'repair',
      priority: 'normal',
    });
    expect(ret).toEqual(mockOrder);
    expect(result.current.title).toBe('');
    expect(result.current.description).toBe('');
    expect(result.current.stationId).toBe('');
  });

  it('提交失败: 返回null, 不resetForm', async () => {
    mockCreateOrder.mockResolvedValueOnce(null);
    const { result } = renderHook(() => useWorkOrderCreate());
    act(() => {
      result.current.setTitle('Test');
      result.current.setDescription('Desc');
      result.current.setStationId('123');
    });
    let ret;
    await act(async () => { ret = await result.current.handleSubmit(); });
    expect(ret).toBeNull();
    expect(result.current.title).toBe('Test');
  });

  it('clearError 清除localError', async () => {
    const { result } = renderHook(() => useWorkOrderCreate());
    await act(async () => { await result.current.handleSubmit(); });
    expect(result.current.localError).not.toBeNull();
    act(() => result.current.clearError());
    expect(result.current.localError).toBeNull();
  });

  it('resetForm 重置所有字段', () => {
    const { result } = renderHook(() => useWorkOrderCreate());
    act(() => {
      result.current.setTitle('X');
      result.current.setDescription('Y');
      result.current.setStationId('1');
      result.current.setType('inspection');
      result.current.setPriority('urgent');
    });
    act(() => result.current.resetForm());
    expect(result.current.title).toBe('');
    expect(result.current.type).toBe('repair');
    expect(result.current.priority).toBe('normal');
  });
});
