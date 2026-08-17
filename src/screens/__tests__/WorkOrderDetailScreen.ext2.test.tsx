/**
 * WorkOrderDetailScreen.ext2 — F1222 白天降级档
 * 真缺口闭合: 未覆盖行 82-86 (loadData wrapper), 147 (onAction 重试), 161 (onRefresh)
 *
 * F1203 拆层后 effect 只调 loadCore, loadData wrapper 仅由交互触发:
 *   - L161 RefreshControl onRefresh → loadData(true) → setRefreshing(true/false) + loadCore
 *   - L147 EmptyState onAction → loadData() → loadCore
 *   - L80-89 loadData 本体 (28+ 既有测试全绕过)
 *
 * 手法: F1221 InspectionDetailScreen.ext3 同模式 —
 *   findAllByType(RefreshControl) 直查实例 fail-fast (F1206 修复模式, FlatList/ScrollView
 *   的 refreshControl 作为 prop 传递不在 children 树里), fetch 计数锚定初始1→交互后2。
 */
import { RefreshControl } from 'react-native';
import { render, fireEvent, act } from '@testing-library/react-native';
import WorkOrderDetailScreen from '../WorkOrderDetailScreen';
import { useWorkOrderStore } from '../../store/workOrderStore';
import { workOrderRecordApi } from '../../services/api';

const mockFetchOrderDetail = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { orderId: 'WO-1' } }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../store/workOrderStore', () => ({
  useWorkOrderStore: jest.fn(),
}));

jest.mock('../../services/api', () => ({
  workOrderRecordApi: { getRecords: jest.fn() },
  workOrderActionApi: {
    accept: jest.fn(),
    start: jest.fn(),
    complete: jest.fn(),
  },
}));
// 注: workOrderActionApi 虽被 Screen 导入但 ext2 不触发 handleAction,
// 工厂仍需提供完整导出防止 undefined 解构。

const BASE_ORDER = {
  id: 'WO-1',
  stationId: 1,
  stateName: '充电站A',
  title: '维修工单',
  description: '设备故障描述',
  type: 'repair',
  priority: 'high',
  status: 'pending',
  creatorId: 1,
  creatorName: '创建人',
  assigneeId: 2,
  assigneeName: '张三',
  createdAt: '2024-01-15T10:00:00Z',
  updatedAt: '2024-01-15T10:00:00Z',
};

const storeReturn = (overrides: Record<string, unknown> = {}) => ({
  selectedOrder: BASE_ORDER,
  loading: false,
  error: null,
  fetchOrderDetail: mockFetchOrderDetail,
  ...overrides,
});

/**
 * fail-fast 直查 RefreshControl 实例 (F1206 修复模式):
 * 找不到时测试变红而非静默通过。
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

describe('WorkOrderDetailScreen.ext2 — L82-86/147/161 真缺口闭合', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchOrderDetail.mockResolvedValue(undefined);
    (workOrderRecordApi.getRecords as jest.Mock).mockResolvedValue({ data: [] });
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(storeReturn());
  });

  // L161 onRefresh + L80-89 loadData(true) 真臂: isRefresh=true 两 setState + loadCore
  it('RefreshControl onRefresh: loadData(true) 真重载 (fetch 计数 1→2)', async () => {
    const { UNSAFE_root } = render(<WorkOrderDetailScreen />);

    // fail-fast 锚定: effect 初始 loadCore 已调一次
    expect(mockFetchOrderDetail).toHaveBeenCalledTimes(1);
    expect(mockFetchOrderDetail).toHaveBeenCalledWith('WO-1');

    const props = findRefreshControl(UNSAFE_root);

    // 真触发 onRefresh → loadData(true) → setRefreshing(true) → await loadCore → setRefreshing(false)
    await act(async () => {
      (props.onRefresh as () => Promise<void>)();
    });

    // fail-fast 锚定: 重载请求真实发出 (初始1 + 刷新1 = 2)
    expect(mockFetchOrderDetail).toHaveBeenCalledTimes(2);
    expect(mockFetchOrderDetail).toHaveBeenLastCalledWith('WO-1');
  });

  // L147 onAction 重试回调: error 且无 selectedOrder → EmptyState 重试按钮 → loadData()
  it('EmptyState error 重试: onAction 走 loadData 触发 fetchOrderDetail', async () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedOrder: null, error: '网络错误' })
    );
    const { getByText } = render(<WorkOrderDetailScreen />);

    // fail-fast 锚定: 错误态渲染
    expect(getByText('网络错误')).toBeTruthy();

    await act(async () => {
      fireEvent.press(getByText('重试'));
    });

    // fail-fast 锚定: 重试真实发出请求 (初始1 + 重试1 = 2)
    expect(mockFetchOrderDetail).toHaveBeenCalledTimes(2);
    expect(mockFetchOrderDetail).toHaveBeenLastCalledWith('WO-1');
  });
});
