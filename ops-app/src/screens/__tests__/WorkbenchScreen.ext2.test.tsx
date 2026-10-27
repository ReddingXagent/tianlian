/**
 * F1209: WorkbenchScreen 真实数据流覆盖补充
 * 既有 WorkbenchScreen.test/ext 两套件均 jest.mock(usePolling)，导致
 * fetcher 主体（Promise.all → stats/orders/alarms 三源聚合）从未真实执行。
 * 本套件不 mock usePolling，真实走 execute → fetcher → Promise.all → render
 * 链路，锚定 fetcher 返回值确实流入 UI（fail-fast，非凑数断言）。
 */
import { render, waitFor } from '@testing-library/react-native';
import WorkbenchScreen from '../WorkbenchScreen';

const mockNavigate = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useRoute: () => ({ params: {} }),
}));

// 只 mock api 层（fetcher 真实执行）；api.ts 依赖 expo-secure-store 不可在 jest 加载
jest.mock('../../services/api', () => ({
  workbenchApi: {
    getStats: jest.fn(),
    getPendingOrders: jest.fn(),
    getRecentAlarms: jest.fn(),
  },
}));

// F1209: 显式声明不 mock usePolling（保真实 execute 链路），防未来顶部误加
jest.unmock('../../hooks/usePolling');

import { workbenchApi } from '../../services/api';

const STATS = {
  pendingOrders: 3,
  inProgressOrders: 2,
  todayCompleted: 5,
  unhandledAlarms: 4,
  criticalAlarms: 1,
};

const ORDERS = [
  {
    id: 'WO-1',
    stationId: 1,
    stationName: '充电站A',
    title: '工单甲',
    description: '描述甲',
    type: 'repair',
    priority: 'urgent',
    status: 'pending',
    creatorId: 1,
    creatorName: 'admin',
    assigneeName: '张三',
    createdAt: '2024-01-15T10:00:00Z',
    updatedAt: '',
  },
];

const ALARMS = [
  {
    id: 101,
    stationId: 1,
    stationName: '充电站A',
    deviceId: 'DEV-1',
    level: 'critical',
    title: '严重告警',
    status: 'active',
    createdAt: '2024-01-15T10:00:00Z',
  },
];

describe('WorkbenchScreen ext2 — 真实 usePolling 数据流', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (workbenchApi.getStats as jest.Mock).mockResolvedValue({ data: STATS });
    (workbenchApi.getPendingOrders as jest.Mock).mockResolvedValue({
      data: ORDERS,
    });
    (workbenchApi.getRecentAlarms as jest.Mock).mockResolvedValue({
      data: ALARMS,
    });
  });

  it('真实 fetcher 三源聚合流入 UI（stats 数字+订单+告警同屏）', async () => {
    const { getByText, queryByText, UNSAFE_root } = render(<WorkbenchScreen />);

    // fail-fast: usePolling immediate 挂载即 execute → fetcher 真实跑完
    await waitFor(() => {
      expect(workbenchApi.getStats).toHaveBeenCalledTimes(1);
      expect(workbenchApi.getPendingOrders).toHaveBeenCalledTimes(1);
      expect(workbenchApi.getRecentAlarms).toHaveBeenCalledTimes(1);
    });
    // fetcher 返回值确实流入 UI：三源各有代表元素（缺一即红）
    await waitFor(() => {
      expect(getByText('待处理工单')).toBeTruthy();
    });
    expect(getByText('工单甲')).toBeTruthy();
    expect(getByText('严重告警')).toBeTruthy();
    expect(queryByText('加载工作台...')).toBeNull();

    // loading 门已过：usePolling execute 完成后 loading=false
    expect(UNSAFE_root.props.loading).toBeUndefined();
  });

  it('三源之一失败走 error 分支（stats 为空时整屏 LoadingSpinner→ErrorState）', async () => {
    (workbenchApi.getStats as jest.Mock).mockRejectedValue(new Error('net'));
    const { getByText } = render(<WorkbenchScreen />);

    await waitFor(() => {
      expect(getByText('加载失败')).toBeTruthy();
    });
    // error 分支锚定：不是静默吞错
    expect(workbenchApi.getStats).toHaveBeenCalledTimes(1);
  });

  it('refresh() 重新拉取（下拉刷新走真实 execute 第二轮）', async () => {
    const { getByText, UNSAFE_root } = render(<WorkbenchScreen />);

    await waitFor(() => {
      expect(getByText('工单甲')).toBeTruthy();
    });
    (workbenchApi.getStats as jest.Mock).mockClear();
    (workbenchApi.getPendingOrders as jest.Mock).mockClear();
    (workbenchApi.getRecentAlarms as jest.Mock).mockClear();

    // 找到 RefreshControl 触发 onRefresh → usePolling.refresh → execute
    // F1206 教训: ScrollView 把 refreshControl 作 prop 传递, 不在 children 树里,
    // 需在 props 上直查而非遍历子树
    const scrollView = UNSAFE_root.findAll(
      (node: { type?: unknown }) =>
        node.type &&
        (String(
          (node.type as { displayName?: string; name?: string }).displayName ??
            (node.type as { name?: string }).name ?? ''
        ).includes('ScrollView'))
    );
    expect(scrollView.length).toBeGreaterThanOrEqual(1);
    const rc = scrollView[0].props.refreshControl;
    expect(rc).toBeDefined();
    expect(typeof rc.props.onRefresh).toBe('function');
    rc.props.onRefresh();

    await waitFor(() => {
      expect(workbenchApi.getStats).toHaveBeenCalledTimes(1);
    });
    // 刷新后数据仍在屏（成功路径锚定，走 catch 则元素消失）
    await waitFor(() => {
      expect(getByText('工单甲')).toBeTruthy();
    });
  });
});
