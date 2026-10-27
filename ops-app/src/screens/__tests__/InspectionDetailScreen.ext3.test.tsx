/**
 * InspectionDetailScreen ext3 — 真缺口闭合 (F1220)
 *
 * coverage-final.json 实勘缺口(branch counts=[...]):
 * - branch0/1/2 + stmt11-16 + fn2: L50-55 loadData wrapper 真臂
 *   (isRefresh=true setRefreshing(true)→L51-52 / finally setRefreshing(false)→L55)
 *   F1203 拆层后 effect 只调 loadCore, wrapper 仅由 onRefresh(L113)/重试(L103)触发,
 *   25+ 既有测试全绕过 — 真缺口
 * - branch5 arm1 + stmt39: L82 `error && !selectedTask` 前者短路臂
 *   (error 非空且 selectedTask 非空 → 跳过 EmptyState 渲染数据)
 * - branch8 default arm: L91 switch getResultIcon(undefined) → '⬜'
 * - fn10 + stmt45: L103 onAction={() => loadData()} 重试按钮回调
 * - fn11 + stmt48: L113 refreshControl onRefresh 回调
 *
 * 附带加固: ext2 首测为空壳假绿(标题声称 RefreshControl 触发 fetchTaskDetail,
 * body 只断言初始调用, 与 F1207 HomeScreen.ext2 空壳同模式), 本文件真测闭合。
 */
import { Alert, RefreshControl } from 'react-native';
import { render, fireEvent, act } from '@testing-library/react-native';
import InspectionDetailScreen from '../InspectionDetailScreen';
import { useInspectionStore } from '../../store/inspectionStore';

const mockFetchTaskDetail = jest.fn();
const mockStartTask = jest.fn();
const mockUpdateItem = jest.fn();
const mockCompleteTask = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { taskId: 1 } }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../store/inspectionStore', () => ({
  useInspectionStore: jest.fn(),
}));

const BASE_TASK = {
  id: 1,
  stationId: 1,
  stationName: '充电站A',
  deviceId: 1,
  deviceName: '充电桩01',
  type: 'daily',
  status: 'in_progress',
  scheduledDate: '2024-01-15T00:00:00Z',
  completedDate: null,
  assignedTo: 2,
  assignedName: '张三',
  description: '日常巡检任务',
  items: [
    { id: 1, name: '外观检查', result: 'pass' as const },
    { id: 2, name: '功能检查', result: 'fail' as const },
    { id: 3, name: '安全检查', result: undefined },
  ],
};

function setupStore(overrides: Record<string, unknown> = {}) {
  (useInspectionStore as unknown as jest.Mock).mockReturnValue({
    selectedTask: BASE_TASK,
    loading: false,
    error: null,
    submitting: false,
    fetchTaskDetail: mockFetchTaskDetail,
    startTask: mockStartTask,
    updateItem: mockUpdateItem,
    completeTask: mockCompleteTask,
    ...overrides,
  });
}

/**
 * fail-fast 直查 RefreshControl 实例 (F1206 修复模式):
 * FlatList/ScrollView 把 refreshControl 作为 prop 传递, 不在 children 树里,
 * UNSAFE_root.findAllByType 直查实例, 找不到时测试变红而非静默通过。
 */
function findRefreshControl(root: { findAllByType: (t: unknown) => unknown[] }): {
  onRefresh?: unknown;
  refreshing?: unknown;
} {
  const rcs = root.findAllByType(RefreshControl);
  expect(rcs.length).toBeGreaterThanOrEqual(1);
  const rc = rcs[0] as { props: { onRefresh?: unknown; refreshing?: unknown } };
  expect(typeof rc.props.onRefresh).toBe('function');
  return rc.props;
}

describe('InspectionDetailScreen.ext3 — L50-55/82/93/103/113 真缺口闭合', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    setupStore();
  });

  afterEach(() => {
    (Alert.alert as jest.Mock).mockRestore();
  });

  // L113 onRefresh + L50-55 loadData(true) 真臂: isRefresh=true 两 setState + L51/L55 两 if 真臂
  it('RefreshControl onRefresh: loadData(true) 真重载 (fetch 计数 1→2)', async () => {
    mockFetchTaskDetail.mockResolvedValue(undefined);
    const { UNSAFE_root } = render(<InspectionDetailScreen />);

    // fail-fast 锚定: effect 初始 loadCore 已调一次
    expect(mockFetchTaskDetail).toHaveBeenCalledTimes(1);
    expect(mockFetchTaskDetail).toHaveBeenCalledWith(1);

    const props = findRefreshControl(UNSAFE_root);

    // 真触发 onRefresh 回调 → loadData(true) → L51 setRefreshing(true) → await loadCore → L55 setRefreshing(false)
    await act(async () => {
      (props.onRefresh as () => Promise<void>)();
    });

    // fail-fast 锚定: 重载请求真实发出 (初始1 + 刷新1 = 2)
    expect(mockFetchTaskDetail).toHaveBeenCalledTimes(2);
    expect(mockFetchTaskDetail).toHaveBeenLastCalledWith(1);
  });

  // L103 onAction 重试回调: error 且无 selectedTask → EmptyState 重试按钮 → loadData()
  it('EmptyState error 重试: onAction 走 loadData 触发 fetchTaskDetail', async () => {
    mockFetchTaskDetail.mockResolvedValue(undefined);
    setupStore({ selectedTask: null, error: '网络错误' });
    const { getByText } = render(<InspectionDetailScreen />);

    // fail-fast 锚定: 错误态渲染 (branch5 arm0 已覆盖路径)
    expect(getByText('网络错误')).toBeTruthy();

    await act(async () => {
      fireEvent.press(getByText('重试'));
    });

    // fail-fast 锚定: 重试真实发出请求 (初始1 + 重试1 = 2)
    expect(mockFetchTaskDetail).toHaveBeenCalledTimes(2);
    expect(mockFetchTaskDetail).toHaveBeenLastCalledWith(1);
  });

  // L82 `error && !selectedTask` 前者短路: error 非空但 selectedTask 也非空 → 跳过 EmptyState 渲染数据
  it('error + selectedTask 并存: 渲染数据不渲染 EmptyState', () => {
    setupStore({ error: '后台刷新失败', selectedTask: BASE_TASK });
    const { queryByText, getByText } = render(<InspectionDetailScreen />);

    // fail-fast 锚定: 走过 L82 前者真臂后仍渲染任务数据
    expect(queryByText('加载失败')).toBeNull();
    expect(getByText('日常巡检任务')).toBeTruthy();
  });

  // L82 branch5 arm1: totalCount = items.length || 1 兜底臂 — 空 items 提交走 ||1 (passedCount=0 → 'fail')
  it('handleComplete 空 items: totalCount 走 || 1 兜底, overall=fail', async () => {
    mockCompleteTask.mockResolvedValue(undefined);
    const emptyTask = { ...BASE_TASK, items: [] };
    setupStore({ selectedTask: emptyTask });
    const { getByText, getByPlaceholderText } = render(<InspectionDetailScreen />);

    fireEvent.press(getByText('完成巡检'));
    fireEvent.changeText(getByPlaceholderText('请输入巡检总结...'), '无检查项');
    await act(async () => {
      fireEvent.press(getByText('提交结果'));
    });

    // fail-fast 锚定: items.length=0 → totalCount 走 ||1 兜底臂; passedCount=0 → 'fail'
    expect(mockCompleteTask).toHaveBeenCalledWith(1, '无检查项', 'fail');
  });

  // L93 switch 'na' arm: 检查项 result='na' → '➖' 图标
  it("getResultIcon 'na': 渲染 ➖ 图标", () => {
    const naTask = {
      ...BASE_TASK,
      items: [{ id: 1, name: '不适用检查', result: 'na' as const }],
    };
    setupStore({ selectedTask: naTask });
    const { getByText } = render(<InspectionDetailScreen />);

    // fail-fast 锚定: na 项渲染 ➖ (branch8 'na' arm)
    expect(getByText('➖')).toBeTruthy();
  });
});
