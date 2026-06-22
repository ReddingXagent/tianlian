import { act } from '@testing-library/react-native';
import { useWorkOrderStore } from '../workOrderStore';
import { workOrderApi } from '../../services/api';
import { WorkOrder } from '../../types';

// Mock the API module
jest.mock('../../services/api', () => ({
  workOrderApi: {
    getList: jest.fn(),
    getDetail: jest.fn(),
    updateStatus: jest.fn(),
  },
}));

const MOCK_ORDER: WorkOrder = {
  id: 1,
  stationId: 1,
  stationName: '充电站A',
  title: '充电桩故障维修',
  description: '充电桩CH001无法正常启动',
  type: 'repair',
  priority: 'high',
  status: 'pending',
  assigneeId: undefined,
  assigneeName: undefined,
  creatorId: 1,
  creatorName: '管理员',
  alarmId: undefined,
  scheduledAt: undefined,
  completedAt: undefined,
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
};

const MOCK_ORDER_2: WorkOrder = {
  id: 2,
  stationId: 2,
  stationName: '充电站B',
  title: '定期巡检',
  description: '月度设备巡检',
  type: 'inspection',
  priority: 'normal',
  status: 'in_progress',
  assigneeId: 2,
  assigneeName: '张三',
  creatorId: 1,
  creatorName: '管理员',
  alarmId: undefined,
  scheduledAt: '2024-01-15T00:00:00Z',
  completedAt: undefined,
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-02T00:00:00Z',
};

describe('useWorkOrderStore', () => {
  beforeEach(() => {
    useWorkOrderStore.setState({
      orders: [],
      selectedOrder: null,
      total: 0,
      page: 1,
      pageSize: 20,
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
      expect(state.pageSize).toBe(20);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });
  });

  describe('fetchOrders', () => {
    it('should fetch orders successfully', async () => {
      const response = {
        data: {
          items: [MOCK_ORDER, MOCK_ORDER_2],
          total: 2,
          page: 1,
          pageSize: 20,
        },
      };
      (workOrderApi.getList as jest.Mock).mockResolvedValue(response);

      await act(async () => {
        await useWorkOrderStore.getState().fetchOrders({ page: 1, pageSize: 20 });
      });

      const state = useWorkOrderStore.getState();
      expect(state.orders).toEqual([MOCK_ORDER, MOCK_ORDER_2]);
      expect(state.total).toBe(2);
      expect(state.page).toBe(1);
      expect(state.pageSize).toBe(20);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('should handle fetch orders failure', async () => {
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

    it('should handle non-Error failure with default message', async () => {
      (workOrderApi.getList as jest.Mock).mockRejectedValue('Unknown error');

      await act(async () => {
        await useWorkOrderStore.getState().fetchOrders();
      });

      const state = useWorkOrderStore.getState();
      expect(state.loading).toBe(false);
      expect(state.error).toBe('获取工单列表失败');
    });

    it('should pass filter params to API', async () => {
      const response = {
        data: { items: [MOCK_ORDER], total: 1, page: 1, pageSize: 20 },
      };
      (workOrderApi.getList as jest.Mock).mockResolvedValue(response);

      await act(async () => {
        await useWorkOrderStore.getState().fetchOrders({
          stationId: 1,
          status: 'pending',
          priority: 'high',
        });
      });

      expect(workOrderApi.getList).toHaveBeenCalledWith({
        stationId: 1,
        status: 'pending',
        priority: 'high',
      });
    });
  });

  describe('fetchOrderDetail', () => {
    it('should fetch order detail successfully', async () => {
      const response = { data: MOCK_ORDER };
      (workOrderApi.getDetail as jest.Mock).mockResolvedValue(response);

      await act(async () => {
        await useWorkOrderStore.getState().fetchOrderDetail(1);
      });

      const state = useWorkOrderStore.getState();
      expect(state.selectedOrder).toEqual(MOCK_ORDER);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('should handle fetch order detail failure', async () => {
      const error = new Error('Order not found');
      (workOrderApi.getDetail as jest.Mock).mockRejectedValue(error);

      await act(async () => {
        await useWorkOrderStore.getState().fetchOrderDetail(999);
      });

      const state = useWorkOrderStore.getState();
      expect(state.selectedOrder).toBeNull();
      expect(state.loading).toBe(false);
      expect(state.error).toBe('Order not found');
    });

    it('should handle non-Error failure with default message', async () => {
      (workOrderApi.getDetail as jest.Mock).mockRejectedValue('Unknown error');

      await act(async () => {
        await useWorkOrderStore.getState().fetchOrderDetail(1);
      });

      const state = useWorkOrderStore.getState();
      expect(state.error).toBe('获取工单详情失败');
    });
  });

  describe('updateOrderStatus', () => {
    it('should update order status successfully', async () => {
      // Pre-populate the store with orders
      useWorkOrderStore.setState({
        orders: [MOCK_ORDER, MOCK_ORDER_2],
        selectedOrder: MOCK_ORDER,
      });

      const updatedOrder: WorkOrder = {
        ...MOCK_ORDER,
        status: 'in_progress',
        assigneeId: 2,
        assigneeName: '张三',
      };
      (workOrderApi.updateStatus as jest.Mock).mockResolvedValue({ data: updatedOrder });

      await act(async () => {
        await useWorkOrderStore.getState().updateOrderStatus(1, 'in_progress');
      });

      const state = useWorkOrderStore.getState();
      expect(state.selectedOrder).toEqual(updatedOrder);
      expect(state.orders[0].status).toBe('in_progress');
      expect(state.orders[0].assigneeId).toBe(2);
      // Order 2 should remain unchanged
      expect(state.orders[1].status).toBe('in_progress');
    });

    it('should throw error on update failure', async () => {
      const error = new Error('Update failed');
      (workOrderApi.updateStatus as jest.Mock).mockRejectedValue(error);

      await expect(
        act(async () => {
          await useWorkOrderStore.getState().updateOrderStatus(1, 'completed');
        })
      ).rejects.toThrow('Update failed');

      const state = useWorkOrderStore.getState();
      expect(state.error).toBe('Update failed');
    });

    it('should throw with default message for non-Error failure', async () => {
      (workOrderApi.updateStatus as jest.Mock).mockRejectedValue('Unknown error');

      await expect(
        act(async () => {
          await useWorkOrderStore.getState().updateOrderStatus(1, 'completed');
        })
      ).rejects.toThrow('更新工单状态失败');

      const state = useWorkOrderStore.getState();
      expect(state.error).toBe('更新工单状态失败');
    });
  });

  describe('setSelectedOrder', () => {
    it('should set selected order', () => {
      useWorkOrderStore.getState().setSelectedOrder(MOCK_ORDER);
      expect(useWorkOrderStore.getState().selectedOrder).toEqual(MOCK_ORDER);
    });

    it('should clear selected order when passing null', () => {
      useWorkOrderStore.setState({ selectedOrder: MOCK_ORDER });
      useWorkOrderStore.getState().setSelectedOrder(null);
      expect(useWorkOrderStore.getState().selectedOrder).toBeNull();
    });
  });
});
