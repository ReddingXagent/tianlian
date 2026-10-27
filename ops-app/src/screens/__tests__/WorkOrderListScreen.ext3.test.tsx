/**
 * WorkOrderListScreen ext3 — loadData wrapper 补覆盖 (F1219)
 * 目标行: 43-49 (loadData wrapper — effect 只调 loadCore, wrapper 仅由交互触发),
 *         106 (错误态 EmptyState 重试按钮 onAction), 117 (RefreshControl onRefresh)
 * 背景: 实测 coverage — loadData wrapper 整块零覆盖 (s9-s14/f2, b1-b3 全零),
 *       25 个既有测试全走 effect 直调 loadCore 或静态渲染, 与 F1213
 *       InspectionListScreen ext3 同构。
 * 手法: store mock 受控 — 挂载 error 态按"重新加载" (L106) → loadData() →
 *       loadCore (fetchOrders 被调); 列表态拉 RefreshControl onRefresh (L117)
 *       → loadData(true) → L44 setRefreshing(true) + L48 finally false。
 */
import { render, act, fireEvent } from '@testing-library/react-native';
import { RefreshControl } from 'react-native';
import WorkOrderListScreen from '../WorkOrderListScreen';
import { useWorkOrderStore } from '../../store/workOrderStore';

const mockNavigate = jest.fn();
const mockFetchOrders = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useRoute: () => ({ params: {} }),
}));

jest.mock('../../store/workOrderStore', () => ({
  useWorkOrderStore: jest.fn(),
}));

const MOCK_ORDERS = [
  {
    id: 'WO-1', stationId: 1, stationName: '充电站A', title: '充电桩故障维修',
    description: '充电桩通信中断', type: 'repair', priority: 'high', status: 'pending',
    creatorId: 1, creatorName: 'admin', assigneeId: 2, assigneeName: '张三',
    createdAt: '2024-01-15T10:00:00Z', updatedAt: '2024-01-15T10:00:00Z',
  },
];

describe('WorkOrderListScreen.ext3', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchOrders.mockResolvedValue(undefined);
    (useWorkOrderStore as unknown as jest.Mock).mockImplementation(() => ({
      orders: [], loading: false, error: null, total: 0,
      fetchOrders: mockFetchOrders,
    }));
  });

  // L106: EmptyState onAction → loadData() → L44 try + loadCore → fetchOrders
  it('error state retry button → loadData() wrapper → fetchOrders called (L106, L43-45)', async () => {
    (useWorkOrderStore as unknown as jest.Mock).mockImplementation(() => ({
      orders: [], loading: false, error: '获取工单列表失败', total: 0,
      fetchOrders: mockFetchOrders,
    }));
    const { getByText, queryByText } = render(<WorkOrderListScreen />);
    expect(getByText('重新加载')).toBeTruthy();
    mockFetchOrders.mockClear();
    // L106 onAction → loadData() → loadCore → fetchOrders
    fireEvent.press(getByText('重新加载'));
    await act(async () => {
      await Promise.resolve();
    });
    expect(mockFetchOrders).toHaveBeenCalledTimes(1);
    // store mock 仍是 error 态 — 按钮仍在, 无列表项
    expect(getByText('重新加载')).toBeTruthy();
    expect(queryByText('充电桩故障维修')).toBeNull();
  });

  // L117: RefreshControl onRefresh → loadData(true) → setRefreshing 走完 (L44/L48)
  it('onRefresh → loadData(true) wrapper → setRefreshing completes (L117, L43-49)', async () => {
    (useWorkOrderStore as unknown as jest.Mock).mockImplementation(() => ({
      orders: MOCK_ORDERS, loading: false, error: null, total: 1,
      fetchOrders: mockFetchOrders,
    }));
    const { UNSAFE_root, findByText } = render(<WorkOrderListScreen />);
    await findByText('充电桩故障维修');
    mockFetchOrders.mockClear();
    // L117 onRefresh → loadData(true) → L44 setRefreshing(true) + L48 finally
    const all = (UNSAFE_root as unknown as {
      findAllByType?: (type: unknown) => { props?: { onRefresh?: () => void } }[];
    }).findAllByType?.(RefreshControl);
    const rc = all?.[0];
    expect(rc).toBeDefined(); // fail-fast: 找不到 RefreshControl = 假绿 (F1206 教训)
    expect(typeof rc?.props?.onRefresh).toBe('function');
    await act(async () => {
      rc?.props?.onRefresh?.();
      await Promise.resolve();
    });
    expect(mockFetchOrders).toHaveBeenCalledTimes(1);
  });
});
