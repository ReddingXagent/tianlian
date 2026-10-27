/**
 * WorkOrderListScreen ext2 — lines 98,109: ListFooter + filtered empty message
 */
import { render } from '@testing-library/react-native';
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
  {
    id: 'WO-2', stationId: 2, stationName: '充电站B', title: '月度巡检',
    description: '月度检查', type: 'inspection', priority: 'normal', status: 'cancelled',
    creatorId: 1, creatorName: 'admin', assigneeId: null, assigneeName: null,
    createdAt: '2024-01-10T10:00:00Z', updatedAt: '2024-01-12T10:00:00Z',
  },
];

describe('WorkOrderListScreen.ext2', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchOrders.mockResolvedValue(undefined);
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: MOCK_ORDERS, loading: false, error: null, total: 2,
      fetchOrders: mockFetchOrders,
    });
  });

  // Line 98: ListFooter when orders.length > 0
  it('renders footer with total count when orders exist', () => {
    const { getByText } = render(<WorkOrderListScreen />);
    expect(getByText('共 2 条工单')).toBeTruthy();
  });

  // ListFooter null when orders.length === 0
  it('does not render footer when no orders', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: [], loading: false, error: null, total: 0,
      fetchOrders: mockFetchOrders,
    });
    const { queryByText } = render(<WorkOrderListScreen />);
    expect(queryByText(/共 \d+ 条工单/)).toBeNull();
  });

  // all filter empty message
  it('renders all-filter empty message', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: [], loading: false, error: null, total: 0,
      fetchOrders: mockFetchOrders,
    });
    const { getByText } = render(<WorkOrderListScreen />);
    // activeFilter defaults to 'all'
    expect(getByText('当前没有工单')).toBeTruthy();
  });

  // error with orders coexist → shows FlatList
  it('renders FlatList when error exists but orders are present', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: MOCK_ORDERS, loading: false, error: 'Partial error', total: 2,
      fetchOrders: mockFetchOrders,
    });
    const { getByText } = render(<WorkOrderListScreen />);
    expect(getByText('充电桩故障维修')).toBeTruthy();
  });

  // renders filter buttons
  it('renders filter buttons', () => {
    const { getByText } = render(<WorkOrderListScreen />);
    expect(getByText('全部')).toBeTruthy();
    expect(getByText('待接单')).toBeTruthy();
    expect(getByText('进行中')).toBeTruthy();
  });

  // loading state when loading and no orders
  it('renders loading spinner when loading and no orders', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: [], loading: true, error: null, total: 0,
      fetchOrders: mockFetchOrders,
    });
    const { getByText } = render(<WorkOrderListScreen />);
    expect(getByText('加载工单列表...')).toBeTruthy();
  });
});
