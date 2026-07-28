import { act } from '@testing-library/react-native';
import { useWorkOrderStore } from '../workOrderStore';
import { workOrderApi } from '../../services/api';
import { WorkOrder } from '../../types';

// Mock the API module
jest.mock('../../services/api', () => ({
  workOrderApi: {
    getList: jest.fn(),
    getDetail: jest.fn(),
    createWorkOrder: jest.fn(),
    completeWorkOrder: jest.fn(),
  },
}));

const MOCK_ORDERS: WorkOrder[] = [
  {
    id: 'WO-1',
    stationId: 1,
    stationName: '充电站A',
    title: '维修工单',
    description: '需要维修',
    type: 'repair',
    priority: 'high',
    status: 'pending',
    creatorId: 1,
    creatorName: 'admin',
    createdAt: '2024-01-15T10:30:00Z',
    updatedAt: '2024-01-15T10:30:00Z',
  },
  {
    id: 'WO-2',
    stationId: 1,
    stationName: '充电站A',
    title: '巡检工单',
    description: '需要巡检',
    type: 'inspection',
    priority: 'normal',
    status: 'in_progress',
    creatorId: 1,
    creatorName: 'admin',
    assigneeName: '张三',
    createdAt: '2024-01-14T08:00:00Z',
    updatedAt: '2024-01-14T08:00:00Z',
  },
];

describe('useWorkOrderStore', () => {
  beforeEach(() => {
    useWorkOrderStore.setState({
      orders: [],
      selectedOrder: null,
      total: 0,
      page: 1,
      loading: false,
      error: null,
    });
    jest.clearAllMocks();
  });

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useWorkOrderStore.getState();
      expect(state.orders).toEqual([]);
      expect(state.selectedOrder).toBeNull();
      expect(state.total).toBe(0);
      expect(state.page).toBe(1);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });
  });

  describe('fetchOrders', () => {
    it('should fetch orders successfully', async () => {
      const response = {
        data: {
          items: MOCK_ORDERS,
          total: 2,
          page: 1,
          pageSize: 20,
        },
      };
      (workOrderApi.getList as jest.Mock).mockResolvedValue(response);

      await act(async () => {
        await useWorkOrderStore.getState().fetchOrders({ stationId: 1 });
      });

      const state = useWorkOrderStore.getState();
      expect(state.orders).toEqual(MOCK_ORDERS);
      expect(state.total).toBe(2);
      expect(state.page).toBe(1);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
      expect(workOrderApi.getList).toHaveBeenCalledWith({ stationId: 1 });
    });

    it('should handle fetch failure', async () => {
      const error = new Error('Network Error');
      (workOrderApi.getList as jest.Mock).mockRejectedValue(error);

      await act(async () => {
        await useWorkOrderStore.getState().fetchOrders();
      });

      const state = useWorkOrderStore.getState();
      expect(state.orders).toEqual([]);
      expect(state.loading).toBe(false);
      expect(state.error).toBe('Network Error');
    });
  });

  describe('fetchOrderDetail', () => {
    it('should fetch order detail successfully', async () => {
      const response = { data: MOCK_ORDERS[0] };
      (workOrderApi.getDetail as jest.Mock).mockResolvedValue(response);

      await act(async () => {
        await useWorkOrderStore.getState().fetchOrderDetail('WO-1');
      });

      const state = useWorkOrderStore.getState();
      expect(state.selectedOrder).toEqual(MOCK_ORDERS[0]);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('should handle fetch detail failure', async () => {
      const error = new Error('Not found');
      (workOrderApi.getDetail as jest.Mock).mockRejectedValue(error);

      await act(async () => {
        await useWorkOrderStore.getState().fetchOrderDetail('WO-999');
      });

      const state = useWorkOrderStore.getState();
      expect(state.selectedOrder).toBeNull();
      expect(state.loading).toBe(false);
      expect(state.error).toBe('Not found');
    });
  });

  describe('createOrder', () => {
    it('should create order successfully', async () => {
      const newOrder = { ...MOCK_ORDERS[0], id: 3 };
      (workOrderApi.createWorkOrder as jest.Mock).mockResolvedValue({ data: newOrder });
      (workOrderApi.getList as jest.Mock).mockResolvedValue({
        data: { items: [...MOCK_ORDERS, newOrder], total: 3, page: 1, pageSize: 20 },
      });

      await act(async () => {
        await useWorkOrderStore.getState().createOrder({
          stationId: 1,
          title: '新工单',
          description: '测试',
          type: 'repair',
          priority: 'normal',
        });
      });

      expect(workOrderApi.createWorkOrder).toHaveBeenCalledWith({
        stationId: 1,
        title: '新工单',
        description: '测试',
        type: 'repair',
        priority: 'normal',
      });
    });
  });

  describe('setSelectedOrder', () => {
    it('should set selected order', () => {
      useWorkOrderStore.getState().setSelectedOrder(MOCK_ORDERS[0]);
      expect(useWorkOrderStore.getState().selectedOrder).toEqual(MOCK_ORDERS[0]);
    });

    it('should clear selected order with null', () => {
      useWorkOrderStore.setState({ selectedOrder: MOCK_ORDERS[0] });
      useWorkOrderStore.getState().setSelectedOrder(null);
      expect(useWorkOrderStore.getState().selectedOrder).toBeNull();
    });
  });

  describe('reset', () => {
    it('should reset state to initial values', () => {
      useWorkOrderStore.setState({
        orders: MOCK_ORDERS,
        selectedOrder: MOCK_ORDERS[0],
        total: 2,
        page: 2,
        loading: true,
        error: 'some error',
      });

      useWorkOrderStore.getState().reset();

      const state = useWorkOrderStore.getState();
      expect(state.orders).toEqual([]);
      expect(state.selectedOrder).toBeNull();
      expect(state.total).toBe(0);
      expect(state.page).toBe(1);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });
  });
});