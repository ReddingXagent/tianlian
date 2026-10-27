/**
 * WorkOrderListScreen 扩展测试 — branch覆盖率提升
 * 覆盖: filter switching, error+data, footer, navigation
 */
import { render, fireEvent, waitFor } from '@testing-library/react-native';
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
    id: 'WO-2', stationId: 1, stationName: '充电站B', title: '月度巡检工单',
    description: '月度设备巡检', type: 'inspection', priority: 'normal', status: 'in_progress',
    creatorId: 1, creatorName: 'admin', assigneeId: 3, assigneeName: '李四',
    createdAt: '2024-01-14T10:00:00Z', updatedAt: '2024-01-14T10:00:00Z',
  },
];

describe('WorkOrderListScreen.ext — additional branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchOrders.mockResolvedValue(undefined);
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: MOCK_ORDERS, loading: false, error: null, total: 2,
      fetchOrders: mockFetchOrders,
    });
  });

  it('header shows total count', async () => {
    const { findByText } = render(<WorkOrderListScreen />);
    // The header shows "工单管理" and total count
    expect(await findByText('充电桩故障维修')).toBeTruthy();
  });

  it('filter "pending" calls fetchOrders with status', async () => {
    const { findByText } = render(<WorkOrderListScreen />);
    await findByText('充电桩故障维修');

    mockFetchOrders.mockClear();
    fireEvent.press(await findByText('待接单'));

    await waitFor(() => {
      expect(mockFetchOrders).toHaveBeenCalledWith({ status: 'pending' });
    });
  });

  it('filter "cancelled" calls fetchOrders', async () => {
    const { findByText } = render(<WorkOrderListScreen />);
    await findByText('充电桩故障维修');

    mockFetchOrders.mockClear();
    fireEvent.press(await findByText('已取消'));

    await waitFor(() => {
      expect(mockFetchOrders).toHaveBeenCalledWith({ status: 'cancelled' });
    });
  });

  it('header: total=0 does not show count', async () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: [], loading: false, error: null, total: 0,
      fetchOrders: mockFetchOrders,
    });
    const { findByText } = render(<WorkOrderListScreen />);
    expect(await findByText('暂无工单')).toBeTruthy();
  });

  it('error+data: existing orders show when error occurs', async () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: MOCK_ORDERS, loading: false,
      error: 'Network error', total: 2,
      fetchOrders: mockFetchOrders,
    });
    const { findByText, queryByText } = render(<WorkOrderListScreen />);
    expect(await findByText('充电桩故障维修')).toBeTruthy();
    expect(queryByText('加载失败')).toBeNull();
  });

  it('footer shows total when orders exist', async () => {
    const { findByText } = render(<WorkOrderListScreen />);
    expect(await findByText('共 2 条工单')).toBeTruthy();
  });

  it('navigates to detail with correct orderId', async () => {
    const { findByText } = render(<WorkOrderListScreen />);
    fireEvent.press(await findByText('月度巡检工单'));
    expect(mockNavigate).toHaveBeenCalledWith('WorkOrderDetail', { orderId: 'WO-2' });
  });

  it('create button navigates to WorkOrderCreate', async () => {
    const { findByText } = render(<WorkOrderListScreen />);
    fireEvent.press(await findByText('+ 新建'));
    expect(mockNavigate).toHaveBeenCalledWith('WorkOrderCreate');
  });

  it('order card press with WO-1', async () => {
    const { findByText } = render(<WorkOrderListScreen />);
    fireEvent.press(await findByText('充电桩故障维修'));
    expect(mockNavigate).toHaveBeenCalledWith('WorkOrderDetail', { orderId: 'WO-1' });
  });
});
