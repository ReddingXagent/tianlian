/**
 * useInspectionDetail Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';

const mockFetchTaskDetail = jest.fn();
const mockStartTask = jest.fn();
const mockUpdateItem = jest.fn();
const mockCompleteTask = jest.fn();

let mockStore = {
  selectedTask: {
    id: 1,
    items: [
      { id: 10, result: 'pass' },
      { id: 11, result: 'fail' },
      { id: 12, result: 'na' },
    ],
  },
  loading: false,
  error: null,
  submitting: false,
  fetchTaskDetail: mockFetchTaskDetail,
  startTask: mockStartTask,
  updateItem: mockUpdateItem,
  completeTask: mockCompleteTask,
};

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { taskId: 1 } }),
}));

jest.mock('../../store/inspectionStore', () => ({
  useInspectionStore: () => mockStore,
}));

import { useInspectionDetail } from '../useInspectionDetail';

describe('useInspectionDetail', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchTaskDetail.mockResolvedValue(undefined);
    mockStartTask.mockResolvedValue(undefined);
    mockUpdateItem.mockResolvedValue(undefined);
    mockCompleteTask.mockResolvedValue(undefined);
    mockStore.selectedTask = {
      id: 1,
      items: [
        { id: 10, result: 'pass' },
        { id: 11, result: 'fail' },
        { id: 12, result: 'na' },
      ],
    };
  });

  it('初始状态: taskId正确', () => {
    const { result } = renderHook(() => useInspectionDetail());
    expect(result.current.taskId).toBe(1);
    expect(result.current.refreshing).toBe(false);
  });

  it('挂载时加载详情', async () => {
    renderHook(() => useInspectionDetail());
    await waitFor(() => expect(mockFetchTaskDetail).toHaveBeenCalledWith(1));
  });

  it('loadData(isRefresh=true)', async () => {
    const { result } = renderHook(() => useInspectionDetail());
    await waitFor(() => expect(mockFetchTaskDetail).toHaveBeenCalled());
    mockFetchTaskDetail.mockClear();
    await act(async () => { await result.current.loadData(true); });
    expect(result.current.refreshing).toBe(false);
    expect(mockFetchTaskDetail).toHaveBeenCalledWith(1);
  });

  it('handleStart 调用startTask', async () => {
    const { result } = renderHook(() => useInspectionDetail());
    await waitFor(() => expect(mockFetchTaskDetail).toHaveBeenCalled());
    await act(async () => { await result.current.handleStart(); });
    expect(mockStartTask).toHaveBeenCalledWith(1);
  });

  it('handleItemResult 调用updateItem', async () => {
    const { result } = renderHook(() => useInspectionDetail());
    await waitFor(() => expect(mockFetchTaskDetail).toHaveBeenCalled());
    const item = { id: 10, result: 'pass' };
    await act(async () => { await result.current.handleItemResult(item, 'fail'); });
    expect(mockUpdateItem).toHaveBeenCalledWith(1, 10, 'fail');
  });

  it('handleComplete: 全pass → overall=pass', async () => {
    mockStore.selectedTask = {
      id: 1,
      items: [
        { id: 10, result: 'pass' },
        { id: 11, result: 'pass' },
      ],
    };
    const { result } = renderHook(() => useInspectionDetail());
    await waitFor(() => expect(mockFetchTaskDetail).toHaveBeenCalled());
    await act(async () => { await result.current.handleComplete('all good'); });
    expect(mockCompleteTask).toHaveBeenCalledWith(1, 'all good', 'pass');
  });

  it('handleComplete: 有pass有fail → overall=partial', async () => {
    mockStore.selectedTask = {
      id: 1,
      items: [
        { id: 10, result: 'pass' },
        { id: 11, result: 'fail' },
      ],
    };
    const { result } = renderHook(() => useInspectionDetail());
    await waitFor(() => expect(mockFetchTaskDetail).toHaveBeenCalled());
    await act(async () => { await result.current.handleComplete('mixed'); });
    expect(mockCompleteTask).toHaveBeenCalledWith(1, 'mixed', 'partial');
  });

  it('handleComplete: 全fail → overall=fail', async () => {
    mockStore.selectedTask = {
      id: 1,
      items: [
        { id: 10, result: 'fail' },
        { id: 11, result: 'fail' },
      ],
    };
    const { result } = renderHook(() => useInspectionDetail());
    await waitFor(() => expect(mockFetchTaskDetail).toHaveBeenCalled());
    await act(async () => { await result.current.handleComplete('all bad'); });
    expect(mockCompleteTask).toHaveBeenCalledWith(1, 'all bad', 'fail');
  });

  it('handleComplete: 空items → overall=fail (bug修复)', async () => {
    mockStore.selectedTask = { id: 1, items: [] };
    const { result } = renderHook(() => useInspectionDetail());
    await waitFor(() => expect(mockFetchTaskDetail).toHaveBeenCalled());
    await act(async () => { await result.current.handleComplete('empty'); });
    expect(mockCompleteTask).toHaveBeenCalledWith(1, 'empty', 'fail');
  });
});
