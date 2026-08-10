/**
 * workOrderEnhancedStore 扩展覆盖率 — non-Error throw + description==title 分支
 * 目标: branches 64.28% → 100%
 */
import { act } from '@testing-library/react-native';
import { useWorkOrderEnhancedStore } from '../workOrderEnhancedStore';
import { workOrderApi, workOrderRecordApi, workOrderTransferApi } from '../../services/api';

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
    medium: 'warning',
    high: 'critical',
  },
}));

describe('useWorkOrderEnhancedStore — 扩展分支', () => {
  beforeEach(() => {
    useWorkOrderEnhancedStore.getState().reset();
    jest.clearAllMocks();
  });

  describe('createOrder', () => {
    it('description === title → faultDesc 只有 title', async () => {
      (workOrderApi.create as jest.Mock).mockResolvedValue({ data: { id: 'wo1' } });

      await act(async () => {
        await useWorkOrderEnhancedStore.getState().createOrder({
          title: '相同标题',
          description: '相同标题',
          stationId: 1,
          type: 'fault',
          priority: 'low',
        });
      });

      const call = (workOrderApi.create as jest.Mock).mock.calls[0][0];
      expect(call.faultDesc).toBe('相同标题');
    });

    it('description 为空 → faultDesc 只有 title', async () => {
      (workOrderApi.create as jest.Mock).mockResolvedValue({ data: { id: 'wo2' } });

      await act(async () => {
        await useWorkOrderEnhancedStore.getState().createOrder({
          title: '标题',
          description: '',
          stationId: 1,
          type: 'fault',
          priority: 'medium',
        });
      });

      const call = (workOrderApi.create as jest.Mock).mock.calls[0][0];
      expect(call.faultDesc).toBe('标题');
    });

    it('未知 priority → WO_PRIORITY_TO_LEVEL fallback undefined', async () => {
      (workOrderApi.create as jest.Mock).mockResolvedValue({ data: { id: 'wo3' } });

      await act(async () => {
        await useWorkOrderEnhancedStore.getState().createOrder({
          title: '标题',
          description: '描述',
          stationId: 1,
          type: 'fault',
          priority: 'unknown',
        });
      });

      const call = (workOrderApi.create as jest.Mock).mock.calls[0][0];
      expect(call.level).toBe('warning'); // ?? 'warning'
    });

    it('non-Error throw → 默认错误消息', async () => {
      (workOrderApi.create as jest.Mock).mockRejectedValue('fail');

      await act(async () => {
        await useWorkOrderEnhancedStore.getState().createOrder({
          title: '标题',
          description: '描述',
          stationId: 1,
          type: 'fault',
          priority: 'high',
        });
      });

      expect(useWorkOrderEnhancedStore.getState().createError).toBe('创建工单失败');
      expect(useWorkOrderEnhancedStore.getState().creating).toBe(false);
    });
  });

  describe('assignOrder — non-Error', () => {
    it('non-Error throw → 默认消息', async () => {
      (workOrderApi.assign as jest.Mock).mockRejectedValue(42);

      await act(async () => {
        await useWorkOrderEnhancedStore.getState().assignOrder('wo1', 5);
      });

      expect(useWorkOrderEnhancedStore.getState().assignError).toBe('分配工单失败');
      expect(useWorkOrderEnhancedStore.getState().assigning).toBe(false);
    });
  });

  describe('transferOrder — non-Error', () => {
    it('non-Error throw → 默认消息', async () => {
      (workOrderTransferApi.transfer as jest.Mock).mockRejectedValue(null);

      await act(async () => {
        await useWorkOrderEnhancedStore.getState().transferOrder('wo1', 5, 'reason');
      });

      expect(useWorkOrderEnhancedStore.getState().transferError).toBe('转派工单失败');
      expect(useWorkOrderEnhancedStore.getState().transferring).toBe(false);
    });
  });

  describe('urgeOrder', () => {
    it('成功 → 返回detail', async () => {
      (workOrderTransferApi.urge as jest.Mock).mockResolvedValue({});
      (workOrderApi.getDetail as jest.Mock).mockResolvedValue({ data: { id: 'wo1', title: '工单' } });

      let result: unknown;
      await act(async () => {
        result = await useWorkOrderEnhancedStore.getState().urgeOrder('wo1', '催一下');
      });

      expect(result).toEqual({ id: 'wo1', title: '工单' });
      expect(useWorkOrderEnhancedStore.getState().transferring).toBe(false);
    });

    it('non-Error throw → 默认消息', async () => {
      (workOrderTransferApi.urge as jest.Mock).mockRejectedValue({ status: 500 });

      await act(async () => {
        await useWorkOrderEnhancedStore.getState().urgeOrder('wo1', 'msg');
      });

      expect(useWorkOrderEnhancedStore.getState().transferError).toBe('催单失败');
    });
  });

  describe('fetchRecords — error', () => {
    it('reject → recordsLoading false', async () => {
      (workOrderRecordApi.getRecords as jest.Mock).mockRejectedValue(new Error('network'));

      await act(async () => {
        await useWorkOrderEnhancedStore.getState().fetchRecords('wo1');
      });

      expect(useWorkOrderEnhancedStore.getState().recordsLoading).toBe(false);
    });
  });

  describe('addRecord — error', () => {
    it('reject → silent fail', async () => {
      (workOrderRecordApi.addRecord as jest.Mock).mockRejectedValue(new Error('fail'));

      await act(async () => {
        await useWorkOrderEnhancedStore.getState().addRecord('wo1', 'comment', 'note');
      });

      // should not throw, silent catch
      // error被静默捕获，records/loading状态不变
      const state = useWorkOrderEnhancedStore.getState();
      expect(state.recordsLoading).toBe(false);
      expect(state.recordsError).toBeUndefined();
    });
  });
});
