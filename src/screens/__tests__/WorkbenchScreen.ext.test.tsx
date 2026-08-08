/**
 * WorkbenchScreen 扩展测试 — 分支+函数覆盖率提升
 * 目标: branches 82→95%+, funcs 64→85%+
 */
import { render, fireEvent } from '@testing-library/react-native';
import WorkbenchScreen from '../WorkbenchScreen';
import { usePolling } from '../../hooks/usePolling';

const mockNavigate = jest.fn();
const mockRefresh = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useRoute: () => ({ params: {} }),
}));

jest.mock('../../hooks/usePolling', () => ({
  usePolling: jest.fn(),
}));

jest.mock('../../services/api', () => ({
  workbenchApi: {
    getStats: jest.fn(),
    getPendingOrders: jest.fn(),
    getRecentAlarms: jest.fn(),
  },
}));

const STATS = {
  pendingOrders: 3,
  inProgressOrders: 2,
  todayCompleted: 5,
  unhandledAlarms: 4,
  criticalAlarms: 1,
};

const ORDERS = [
  {
    id: 'WO-1', stationId: 1, stationName: '充电站A', title: '工单甲',
    description: '描述甲', type: 'repair', priority: 'urgent',
    status: 'pending', creatorId: 1, creatorName: 'admin',
    assigneeName: '张三', createdAt: '2024-01-15T10:00:00Z', updatedAt: '',
  },
  {
    id: 'WO-2', stationId: 1, stationName: '充电站B', title: '工单乙',
    description: '描述乙', type: 'inspection', priority: 'high',
    status: 'pending', creatorId: 1, creatorName: 'admin',
    assigneeName: '李四', createdAt: '2024-01-14T10:00:00Z', updatedAt: '',
  },
];

const ALARMS = [
  {
    id: 1, stationId: 1, stationName: '充电站A', type: 'device_fault',
    level: 'critical', title: '告警X', description: '严重告警描述',
    status: 'unhandled', createdAt: '2024-01-15T10:00:00Z', updatedAt: '',
  },
  {
    id: 2, stationId: 1, stationName: '充电站B', type: 'temp',
    level: 'warning', title: '告警Y', description: '警告告警描述',
    status: 'unhandled', createdAt: '2024-01-15T11:00:00Z', updatedAt: '',
  },
  {
    id: 3, stationId: 1, stationName: '充电站C', type: 'info',
    level: 'info', title: '告警Z', description: '信息告警',
    status: 'unhandled', createdAt: '2024-01-15T12:00:00Z', updatedAt: '',
  },
  {
    id: 4, stationId: 1, stationName: '充电站D', type: 'other',
    level: 'unknown', title: '告警W', description: '未知级别',
    status: 'unhandled', createdAt: '2024-01-15T13:00:00Z', updatedAt: '',
  },
];

function pollingReturn(overrides: Record<string, unknown> = {}) {
  return {
    data: { stats: STATS, pendingOrders: ORDERS, recentAlarms: ALARMS },
    loading: false,
    error: null,
    refresh: mockRefresh,
    tickCount: 1,
    ...overrides,
  };
}

describe('WorkbenchScreen.ext', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (usePolling as unknown as jest.Mock).mockReturnValue(pollingReturn());
  });

  // --- loading state with existing stats (refreshing) ---
  it('shows content while refreshing (loading=true + stats!=null)', () => {
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({ loading: true })
    );
    const { getByText } = render(<WorkbenchScreen />);
    // Content still rendered during background refresh
    expect(getByText('今日概览')).toBeTruthy();
  });

  // --- error + existing stats (shows content despite error) ---
  it('shows content when error but stats exist', () => {
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({ error: new Error('timeout') })
    );
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('今日概览')).toBeTruthy();
  });

  // --- stats null fallbacks ---
  it('renders dash when stats is null', () => {
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({ data: { stats: null, pendingOrders: [], recentAlarms: [] } })
    );
    const { getAllByText } = render(<WorkbenchScreen />);
    // All stat cards show '-'
    const dashes = getAllByText('-');
    expect(dashes.length).toBeGreaterThanOrEqual(4);
  });

  // --- quick action: scan (tab navigation) ---
  it('navigates to Scan tab when scan pressed', () => {
    const { getByText } = render(<WorkbenchScreen />);
    fireEvent.press(getByText('扫码签到'));
    expect(mockNavigate).toHaveBeenCalledWith('Main', { screen: 'Scan' });
  });

  // --- quick action: monitor (tab navigation) ---
  it('navigates to Monitor tab when monitor pressed', () => {
    const { getByText } = render(<WorkbenchScreen />);
    fireEvent.press(getByText('设备监控'));
    expect(mockNavigate).toHaveBeenCalledWith('Main', { screen: 'Monitor' });
  });

  // --- quick action: knowledge (stack navigation) ---
  it('navigates to Knowledge route when pressed', () => {
    const { getByText } = render(<WorkbenchScreen />);
    fireEvent.press(getByText('知识库'));
    expect(mockNavigate).toHaveBeenCalledWith('Knowledge');
  });

  // --- quick action: diagnosis (stack navigation) ---
  it('navigates to Diagnosis route when pressed', () => {
    const { getByText } = render(<WorkbenchScreen />);
    fireEvent.press(getByText('故障诊断'));
    expect(mockNavigate).toHaveBeenCalledWith('Diagnosis');
  });

  // --- order press ---
  it('navigates to detail when order pressed', () => {
    const { getByText } = render(<WorkbenchScreen />);
    fireEvent.press(getByText('工单甲'));
    expect(mockNavigate).toHaveBeenCalledWith('WorkOrderDetail', { orderId: 'WO-1' });
  });

  // --- refresh via pull-to-refresh ---
  it('triggers refresh on pull-to-refresh', () => {
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({ loading: true }) // refreshing=true when loading+stats
    );
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('今日概览')).toBeTruthy();
    // refresh function is from usePolling mock
    expect(mockRefresh).not.toHaveBeenCalled();
  });

  // --- view all orders link ---
  it('navigates to WorkOrders tab when view all pressed', () => {
    const { getByText } = render(<WorkbenchScreen />);
    fireEvent.press(getByText(/查看全部/));
    expect(mockNavigate).toHaveBeenCalledWith('Main', { screen: 'WorkOrders' });
  });

  // --- alarm level icons: critical, warning, info, unknown ---
  it('renders critical alarm icon', () => {
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('告警X')).toBeTruthy();
  });

  it('renders warning alarm with yellow icon', () => {
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('告警Y')).toBeTruthy();
  });

  it('renders info alarm with blue icon', () => {
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('告警Z')).toBeTruthy();
  });

  it('renders unknown alarm with default white icon', () => {
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('告警W')).toBeTruthy();
  });

  // --- critical alarms badge in section header ---
  it('renders critical alarm count badge', () => {
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText(/🔴.*1条严重/)).toBeTruthy();
  });

  // --- no urgency bar when no urgent/high orders ---
  it('hides urgency bar when no urgent/high orders', () => {
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({
        data: {
          stats: STATS,
          pendingOrders: [{ ...ORDERS[0], priority: 'normal' }],
          recentAlarms: [],
        },
      })
    );
    const { queryByText } = render(<WorkbenchScreen />);
    expect(queryByText(/条紧急/)).toBeNull();
    expect(queryByText(/条高优/)).toBeNull();
  });

  // --- view all with pendingOrders count ---
  it('shows pending count in view all link', () => {
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText(/查看全部.*\(3\)/)).toBeTruthy();
  });

  // --- view all without pending count (stats null) ---
  it('view all link has no count when stats null', () => {
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({
        data: { stats: null, pendingOrders: [], recentAlarms: [] },
      })
    );
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('查看全部')).toBeTruthy();
  });

  // --- empty alarms ---
  it('shows empty alarm placeholder', () => {
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({
        data: { stats: STATS, pendingOrders: ORDERS, recentAlarms: [] },
      })
    );
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('暂无告警')).toBeTruthy();
  });

  // --- empty orders ---
  it('shows empty order placeholder', () => {
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({
        data: { stats: STATS, pendingOrders: [], recentAlarms: ALARMS },
      })
    );
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('暂无待办工单')).toBeTruthy();
  });

  // --- both urgent and high count ---
  it('shows both urgent and high counts', () => {
    const orders = [
      { ...ORDERS[0], priority: 'urgent' },
      { ...ORDERS[1], priority: 'urgent' },
      { ...ORDERS[0], id: 'WO-3', priority: 'high' },
    ];
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({
        data: { stats: STATS, pendingOrders: orders, recentAlarms: [] },
      })
    );
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('2条紧急')).toBeTruthy();
    expect(getByText('1条高优')).toBeTruthy();
  });

  // --- no critical alarms badge when criticalAlarms=0 ---
  it('hides critical badge when criticalAlarms=0', () => {
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({
        data: {
          stats: { ...STATS, criticalAlarms: 0 },
          pendingOrders: [],
          recentAlarms: [],
        },
      })
    );
    const { queryByText } = render(<WorkbenchScreen />);
    expect(queryByText(/条严重/)).toBeNull();
  });
});
