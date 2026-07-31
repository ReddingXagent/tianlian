import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
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
    id: 'WO-1',
    stationId: 1,
    stationName: '充电站A',
    title: '充电桩故障维修',
    description: '充电桩通信中断',
    type: 'repair',
    priority: 'high',
    status: 'pending',
    creatorId: 1,
    creatorName: 'admin',
    assigneeId: 2,
    assigneeName: '张三',
    createdAt: '2024-01-15T10:00:00Z',
    updatedAt: '2024-01-15T10:00:00Z',
  },
  {
    id: 'WO-2',
    stationId: 1,
    stationName: '充电站B',
    title: '月度巡检工单',
    description: '月度设备巡检',
    type: 'inspection',
    priority: 'normal',
    status: 'in_progress',
    creatorId: 1,
    creatorName: 'admin',
    assigneeId: 3,
    assigneeName: '李四',
    createdAt: '2024-01-14T10:00:00Z',
    updatedAt: '2024-01-14T10:00:00Z',
  },
];

describe('WorkOrderListScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchOrders.mockResolvedValue(undefined);
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: MOCK_ORDERS,
      loading: false,
      error: null,
      total: 2,
      fetchOrders: mockFetchOrders,
    });
  });

  it('shows loading spinner initially', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: [],
      loading: true,
      error: null,
      total: 0,
      fetchOrders: mockFetchOrders,
    });
    const { getByText } = render(<WorkOrderListScreen />);
    expect(getByText('加载工单列表...')).toBeTruthy();
  });

  it('renders order list and header count', () => {
    const { getByText } = render(<WorkOrderListScreen />);
    expect(getByText('充电桩故障维修')).toBeTruthy();
    expect(getByText('月度巡检工单')).toBeTruthy();
    expect(getByText('共 2 条工单')).toBeTruthy();
  });

  it('renders status filter chips', () => {
    const { getByText } = render(<WorkOrderListScreen />);
    expect(getByText('全部')).toBeTruthy();
    expect(getByText('待接单')).toBeTruthy();
  });

  it('navigates to create screen when pressing new button', () => {
    const { getByText } = render(<WorkOrderListScreen />);
    fireEvent.press(getByText('+ 新建'));
    expect(mockNavigate).toHaveBeenCalledWith('WorkOrderCreate');
  });

  it('navigates to detail when an order card is pressed', () => {
    const { getByText } = render(<WorkOrderListScreen />);
    fireEvent.press(getByText('充电桩故障维修'));
    expect(mockNavigate).toHaveBeenCalledWith('WorkOrderDetail', { orderId: 'WO-1' });
  });

  it('shows empty state when no orders', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: [],
      loading: false,
      error: null,
      total: 0,
      fetchOrders: mockFetchOrders,
    });
    const { getByText } = render(<WorkOrderListScreen />);
    expect(getByText('暂无工单')).toBeTruthy();
  });

  it('shows error state when load fails', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: [],
      loading: false,
      error: '获取工单列表失败',
      total: 0,
      fetchOrders: mockFetchOrders,
    });
    const { getByText } = render(<WorkOrderListScreen />);
    expect(getByText('加载失败')).toBeTruthy();
  });
});
