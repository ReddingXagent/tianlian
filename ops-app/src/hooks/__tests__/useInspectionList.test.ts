/**
 * useInspectionList Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';

const mockFetchTasks = jest.fn();

jest.mock('../../store/inspectionStore', () => ({
  useInspectionStore: () => ({
    tasks: [{ id: 1, title: 'Task1' }],
    loading: false,
    error: null,
    total: 1,
    fetchTasks: mockFetchTasks,
  }),
}));

import { useInspectionList } from '../useInspectionList';

describe('useInspectionList', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchTasks.mockResolvedValue(undefined);
  });

  it('初始状态: filter=all', () => {
    const { result } = renderHook(() => useInspectionList());
    expect(result.current.activeFilter).toBe('all');
    expect(result.current.refreshing).toBe(false);
    expect(result.current.tasks).toEqual([{ id: 1, title: 'Task1' }]);
  });

  it('挂载时自动加载', async () => {
    renderHook(() => useInspectionList());
    await waitFor(() => expect(mockFetchTasks).toHaveBeenCalledWith(undefined));
  });

  it('切换filter传status参数', async () => {
    const { result } = renderHook(() => useInspectionList());
    await waitFor(() => expect(mockFetchTasks).toHaveBeenCalled());
    mockFetchTasks.mockClear();
    act(() => result.current.setActiveFilter('in_progress'));
    await waitFor(() => expect(mockFetchTasks).toHaveBeenCalledWith({ status: 'in_progress' }));
  });

  it('loadData(isRefresh=true) 设置refreshing后清除', async () => {
    const { result } = renderHook(() => useInspectionList());
    await waitFor(() => expect(mockFetchTasks).toHaveBeenCalled());
    mockFetchTasks.mockClear();
    await act(async () => { await result.current.loadData(true); });
    expect(result.current.refreshing).toBe(false);
  });
});
