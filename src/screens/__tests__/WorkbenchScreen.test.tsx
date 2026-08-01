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

// usePolling is mocked so these are never called; the mock only prevents the
// real api module (which pulls in expo-secure-store) from loading under jest.
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
  {
    id: 'WO-2',
    stationId: 1,
    stationName: '充电站B',
    title: '工单乙',
    description: '描述乙',
    type: 'inspection',
    priority: 'high',
    status: 'pending',
    creatorId: 1,
    creatorName: 'admin',
    assigneeName: '李四',
    createdAt: '2024-01-14T10:00:00Z',
    updatedAt: '',
  },
];

const ALARMS = [
  {
    id: 1,
    stationId: 1,
    stationName: '充电站A',
    type: 'device_fault',
    level: 'critical',
    title: '告警X',
    description: '严重告警描述',
    status: 'unhandled',
    createdAt: '2024-01-15T10:00:00Z',
    updatedAt: '',
  },
];

const pollingReturn = (overrides: Record<string, unknown> = {}) => ({
  data: { stats: STATS, pendingOrders: ORDERS, recentAlarms: ALARMS },
  loading: false,
  error: null,
  refresh: mockRefresh,
  tickCount: 1,
  ...overrides,
});

describe('WorkbenchScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (usePolling as unknown as jest.Mock).mockReturnValue(pollingReturn());
  });

  it('shows loading spinner initially', () => {
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({ data: null, loading: true })
    );
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('加载工作台...')).toBeTruthy();
  });

  it('shows error state when polling fails', () => {
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({ data: null, error: new Error('网络异常') })
    );
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('加载失败')).toBeTruthy();
    expect(getByText('网络异常')).toBeTruthy();
  });

  it('renders stats, quick actions, orders and alarms', () => {
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('今日概览')).toBeTruthy();
    expect(getByText('快捷操作')).toBeTruthy();
    expect(getByText('工单甲')).toBeTruthy();
    expect(getByText('告警X')).toBeTruthy();
    expect(getByText('1条紧急')).toBeTruthy();
    expect(getByText('1条高优')).toBeTruthy();
  });

  it('navigates when a quick action is pressed', () => {
    const { getByText } = render(<WorkbenchScreen />);
    fireEvent.press(getByText('知识库'));
    expect(mockNavigate).toHaveBeenCalled();
  });

  it('shows empty placeholders when no orders or alarms', () => {
    (usePolling as unknown as jest.Mock).mockReturnValue(
      pollingReturn({
        data: { stats: STATS, pendingOrders: [], recentAlarms: [] },
      })
    );
    const { getByText } = render(<WorkbenchScreen />);
    expect(getByText('暂无待办工单')).toBeTruthy();
    expect(getByText('暂无告警')).toBeTruthy();
  });
});
