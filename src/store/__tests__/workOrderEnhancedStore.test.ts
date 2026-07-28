import { act } from '@testing-library/react-native';
import { useWorkOrderEnhancedStore } from '../workOrderEnhancedStore';
import { workOrderApi, workOrderRecordApi, workOrderTransferApi } from '../../services/api';
import { WorkOrder, WorkOrderRecord } from '../../types';

jest.mock('../../services/api', () => ({
  workOrderApi: {
    create: jest.fn(),
    assign: jest.fn(),
    getDetail: jest.fn(),
  },
  workOrderRecordApi: {
    getRecords: jest.fn(),
    addRecord: jest.fn(),
  },
  workOrderTransferApi: {
    transfer: jest.fn(),
    urge: jest.fn(),
  },
  WO_PRIORITY_TO_LEVEL: {
    low: 'info',
    normal: 'warning',
    high: 'critical',
    urgent: 'critical',
  },
}));

const MOCK_ORDER: WorkOrder = {
  id: 'WO-1',
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

const MOCK_RECORD: WorkOrderRecord = {
  id: 1,
  orderId: 'WO-1',
  action: 'created',
  operatorId: 1,
  operatorName: '管理员',
  note: '创建工单',
  createdAt: '2024-01-01T00:00:00Z',
};

describe('useWorkOrderEnhancedStore', () => {
  beforeEach(() => {
    useWorkOrderEnhancedStore.getState().reset();
    jest.clearAllMocks();
  });

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useWorkOrderEnhancedStore.getState();
      expect(state.creating).toBe(false);
      expect(state.createError).toBeNull();
      expect(state.assigning).toBe(false);
      expect(state.assignError).toBeNull();
      expect(state.transferring).toBe(false);
      expect(state.transferError).toBeNull();
      expect(state.records).toEqual([]);
      expect(state.recordsLoading).toBe(false);
    });
  });

  describe('createOrder', () => {
    it('should create order successfully', async () => {
      (workOrderApi.create as jest.Mock).mockResolvedValue({ data: MOCK_ORDER });

      let result: WorkOrder | null = null;
      await act(async () => {
        result = await useWorkOrderEnhancedStore.getState().createOrder({
          title: '充电桩故障维修',
          description: '充电桩CH001无法正常启动',
          stationId: 1,
          type: 'repair',
          priority: 'high',
        });
      });

      expect(result).toEqual(MOCK_ORDER);
      expect(workOrderApi.create).toHaveBeenCalledWith({
        faultDesc: '充电桩故障维修: 充电桩CH001无法正常启动',
        type: 'repair',
        level: 'critical',
        stationId: 1,
      });
      const state = useWorkOrderEnhancedStore.getState();
      expect(state.creating).toBe(false);
      expect(state.createError).toBeNull();
    });

    it('should handle create failure', async () => {
      (workOrderApi.create as jest.Mock).mockRejectedValue(new Error('Create failed'));

      let result: WorkOrder | null = null;
      await act(async () => {
        result = await useWorkOrderEnhancedStore.getState().createOrder({
          title: 'test',
          description: 'test',
          stationId: 1,
          type: 'repair',
          priority: 'normal',
        });
      });

      expect(result).toBeNull();
      const state = useWorkOrderEnhancedStore.getState();
      expect(state.createError).toBe('Create failed');
      expect(state.creating).toBe(false);
    });
  });

  describe('assignOrder', () => {
    it('should assign order successfully', async () => {
      const assignedOrder = { ...MOCK_ORDER, assigneeId: 2, assigneeName: '张三' };
      (workOrderApi.assign as jest.Mock).mockResolvedValue({ data: assignedOrder });

      let result: WorkOrder | null = null;
      await act(async () => {
        result = await useWorkOrderEnhancedStore.getState().assignOrder('WO-1', 2);
      });

      expect(result).toEqual(assignedOrder);
      expect(workOrderApi.assign).toHaveBeenCalledWith('WO-1', 2);
    });

    it('should handle assign failure', async () => {
      (workOrderApi.assign as jest.Mock).mockRejectedValue(new Error('Assign failed'));

      let result: WorkOrder | null = null;
      await act(async () => {
        result = await useWorkOrderEnhancedStore.getState().assignOrder('WO-1', 2);
      });

      expect(result).toBeNull();
      const state = useWorkOrderEnhancedStore.getState();
      expect(state.assignError).toBe('Assign failed');
    });
  });

  describe('transferOrder', () => {
    it('should transfer order successfully', async () => {
      const transferredOrder = { ...MOCK_ORDER, assigneeId: 3, assigneeName: '李四' };
      (workOrderTransferApi.transfer as jest.Mock).mockResolvedValue({ message: '转单成功' });
      (workOrderApi.getDetail as jest.Mock).mockResolvedValue({ data: transferredOrder });

      let result: WorkOrder | null = null;
      await act(async () => {
        result = await useWorkOrderEnhancedStore.getState().transferOrder('WO-1', 3, '需要其他人处理');
      });

      expect(result).toEqual(transferredOrder);
      expect(workOrderTransferApi.transfer).toHaveBeenCalledWith('WO-1', {
        targetEngineerId: 3,
        reason: '需要其他人处理',
      });
    });

    it('should handle transfer failure', async () => {
      (workOrderTransferApi.transfer as jest.Mock).mockRejectedValue(new Error('Transfer failed'));

      let result: WorkOrder | null = null;
      await act(async () => {
        result = await useWorkOrderEnhancedStore.getState().transferOrder('WO-1', 3, 'test');
      });

      expect(result).toBeNull();
      const state = useWorkOrderEnhancedStore.getState();
      expect(state.transferError).toBe('Transfer failed');
    });
  });

  describe('urgeOrder', () => {
    it('should urge order successfully', async () => {
      (workOrderTransferApi.urge as jest.Mock).mockResolvedValue({ message: '催单成功' });
      (workOrderApi.getDetail as jest.Mock).mockResolvedValue({ data: MOCK_ORDER });

      let result: WorkOrder | null = null;
      await act(async () => {
        result = await useWorkOrderEnhancedStore.getState().urgeOrder('WO-1', '请尽快处理');
      });

      expect(result).toEqual(MOCK_ORDER);
      expect(workOrderTransferApi.urge).toHaveBeenCalledWith('WO-1', '请尽快处理');
    });

    it('should handle urge failure', async () => {
      (workOrderTransferApi.urge as jest.Mock).mockRejectedValue(new Error('Urge failed'));

      let result: WorkOrder | null = null;
      await act(async () => {
        result = await useWorkOrderEnhancedStore.getState().urgeOrder('WO-1', 'test');
      });

      expect(result).toBeNull();
      const state = useWorkOrderEnhancedStore.getState();
      expect(state.transferError).toBe('Urge failed');
    });
  });

  describe('fetchRecords', () => {
    it('should fetch records successfully', async () => {
      (workOrderRecordApi.getRecords as jest.Mock).mockResolvedValue({ data: [MOCK_RECORD] });

      await act(async () => {
        await useWorkOrderEnhancedStore.getState().fetchRecords('WO-1');
      });

      const state = useWorkOrderEnhancedStore.getState();
      expect(state.records).toEqual([MOCK_RECORD]);
      expect(state.recordsLoading).toBe(false);
    });

    it('should handle fetch records failure', async () => {
      (workOrderRecordApi.getRecords as jest.Mock).mockRejectedValue(new Error('Not found'));

      await act(async () => {
        await useWorkOrderEnhancedStore.getState().fetchRecords('WO-999');
      });

      const state = useWorkOrderEnhancedStore.getState();
      expect(state.recordsLoading).toBe(false);
    });
  });

  describe('addRecord', () => {
    it('should add record and refresh', async () => {
      (workOrderRecordApi.addRecord as jest.Mock).mockResolvedValue({ data: MOCK_RECORD });
      (workOrderRecordApi.getRecords as jest.Mock).mockResolvedValue({ data: [MOCK_RECORD, { ...MOCK_RECORD, id: 2 }] });

      await act(async () => {
        await useWorkOrderEnhancedStore.getState().addRecord('WO-1', 'executing', '正在处理');
      });

      expect(workOrderRecordApi.addRecord).toHaveBeenCalledWith('WO-1', { action: 'executing', note: '正在处理' });
      const state = useWorkOrderEnhancedStore.getState();
      expect(state.records.length).toBe(2);
    });
  });

  describe('reset', () => {
    it('should reset all state', () => {
      useWorkOrderEnhancedStore.setState({
        creating: true,
        createError: 'error',
        assigning: true,
        assignError: 'error',
        transferring: true,
        transferError: 'error',
        records: [MOCK_RECORD],
        recordsLoading: true,
      });

      useWorkOrderEnhancedStore.getState().reset();

      const state = useWorkOrderEnhancedStore.getState();
      expect(state.creating).toBe(false);
      expect(state.createError).toBeNull();
      expect(state.assigning).toBe(false);
      expect(state.assignError).toBeNull();
      expect(state.transferring).toBe(false);
      expect(state.transferError).toBeNull();
      expect(state.records).toEqual([]);
      expect(state.recordsLoading).toBe(false);
    });
  });
});
