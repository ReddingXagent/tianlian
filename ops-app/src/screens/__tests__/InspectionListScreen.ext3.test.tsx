/**
 * InspectionListScreen ext3 — loadData wrapper + 错误态重试 + onRefresh 补覆盖 (F1213)
 * 目标行: 53-57 (loadData wrapper — effect 只调 loadCore, wrapper 仅由交互触发),
 *         130 (错误态 EmptyState 重试按钮 onAction), 141 (RefreshControl onRefresh)
 * 背景: 实测 coverage Lines 80% (75% stmts) — loadData wrapper 整块从未被任何测试
 *       调用(既有 25 测试全走 effect 直调 loadCore 或静态渲染), 三处均为真实缺口。
 * 手法: store mock 受控 — 挂载 error 态按"重新加载" (L130) → loadData() → loadCore
 *       (fetchTasks 被调); 列表态拉 RefreshControl onRefresh (L141) → loadData(true)
 *       → L53 setRefreshing(true) + L57 finally setRefreshing(false)。
 */
import { render, act, fireEvent } from '@testing-library/react-native';
import { RefreshControl } from 'react-native';
import InspectionListScreen from '../InspectionListScreen';
import { useInspectionStore } from '../../store/inspectionStore';

const mockNavigate = jest.fn();
const mockFetchTasks = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useRoute: () => ({ params: {} }),
}));

jest.mock('../../store/inspectionStore', () => ({
  useInspectionStore: jest.fn(),
}));

const MOCK_TASKS = [
  {
    id: 1,
    stationId: 1,
    stationName: '充电站A',
    deviceId: 1,
    deviceName: '充电桩01',
    type: 'daily',
    status: 'pending',
    scheduledDate: '2024-01-15T00:00:00Z',
    description: '日常巡检任务一',
    items: [{ id: 1, name: '检查项', expected: '正常' }],
    createdAt: '',
    updatedAt: '',
  },
];

describe('InspectionListScreen.ext3 — loadData wrapper / retry / pull-to-refresh', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchTasks.mockResolvedValue(undefined);
  });

  it('错误态点重新加载 → loadData() wrapper 真实执行 (L130, L54-58)', async () => {
    (useInspectionStore as unknown as jest.Mock).mockImplementation(() => ({
      tasks: [],
      loading: false,
      error: '加载失败',
      fetchTasks: mockFetchTasks,
    }));
    const { findByText, getByText, queryByText } = render(<InspectionListScreen />);
    expect(await findByText('重新加载')).toBeTruthy();
    mockFetchTasks.mockClear();
    // L130 onAction → loadData() → L54 try + L55 loadCore → fetchTasks
    fireEvent.press(getByText('重新加载'));
    await act(async () => {
      await Promise.resolve();
    });
    expect(mockFetchTasks).toHaveBeenCalledTimes(1);
    // store mock 仍是 error 态 — 按钮仍在, 无列表项
    expect(getByText('重新加载')).toBeTruthy();
    expect(queryByText('日常巡检任务一')).toBeNull();
  });

  it('onRefresh → loadData(true) wrapper → setRefreshing 走完 (L141, L53/L57)', async () => {
    (useInspectionStore as unknown as jest.Mock).mockImplementation(() => ({
      tasks: MOCK_TASKS,
      loading: false,
      error: null,
      total: 1,
      fetchTasks: mockFetchTasks,
    }));
    const { UNSAFE_root, findByText } = render(<InspectionListScreen />);
    await findByText('日常巡检任务一');
    mockFetchTasks.mockClear();
    // L141 onRefresh → loadData(true) → L53 setRefreshing(true) + L57 finally
    const all = (UNSAFE_root as unknown as {
      findAllByType?: (type: unknown) => { props?: { onRefresh?: () => void } }[];
    }).findAllByType?.(RefreshControl);
    const rc = all?.[0];
    expect(rc).toBeDefined(); // fail-fast: 找不到 RefreshControl = 假绿
    expect(typeof rc?.props?.onRefresh).toBe('function');
    await act(async () => {
      rc?.props?.onRefresh?.();
      await Promise.resolve();
    });
    expect(mockFetchTasks).toHaveBeenCalledTimes(1);
  });
});
