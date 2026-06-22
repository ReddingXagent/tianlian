import { act } from '@testing-library/react-native';
import { useInspectionStore } from '../inspectionStore';
import { inspectionApi } from '../../services/api';
import { InspectionTask } from '../../types';

jest.mock('../../services/api', () => ({
  inspectionApi: {
    getList: jest.fn(),
    getDetail: jest.fn(),
    start: jest.fn(),
    updateItem: jest.fn(),
    complete: jest.fn(),
  },
}));

const MOCK_TASK: InspectionTask = {
  id: 1,
  stationId: 1,
  stationName: '充电站A',
  deviceId: 1,
  deviceName: '充电桩CH001',
  type: 'daily',
  status: 'pending',
  scheduledDate: '2024-01-15T00:00:00Z',
  assignedTo: 2,
  assignedName: '张三',
  description: '日检任务 - 充电桩CH001',
  items: [
    { id: 1, name: '外观检查', expected: '无破损、无异物' },
    { id: 2, name: '绝缘测试', expected: '绝缘电阻 > 1MΩ' },
    { id: 3, name: '充电功能', expected: '正常启动充电' },
  ],
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
};

const MOCK_TASK_2: InspectionTask = {
  id: 2,
  stationId: 2,
  stationName: '充电站B',
  deviceId: 2,
  deviceName: '逆变器INV001',
  type: 'monthly',
  status: 'in_progress',
  scheduledDate: '2024-01-20T00:00:00Z',
  description: '月检 - 逆变器INV001',
  items: [{ id: 4, name: '接线检查', expected: '无松动' }],
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
};

describe('useInspectionStore', () => {
  beforeEach(() => {
    useInspectionStore.getState().reset();
    jest.clearAllMocks();
  });

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useInspectionStore.getState();
      expect(state.tasks).toEqual([]);
      expect(state.selectedTask).toBeNull();
      expect(state.total).toBe(0);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.submitting).toBe(false);
      expect(state.submitError).toBeNull();
    });
  });

  describe('fetchTasks', () => {
    it('should fetch tasks successfully', async () => {
      (inspectionApi.getList as jest.Mock).mockResolvedValue({
        data: { items: [MOCK_TASK, MOCK_TASK_2], total: 2, page: 1, pageSize: 20 },
      });

      await act(async () => {
        await useInspectionStore.getState().fetchTasks({ page: 1, pageSize: 20 });
      });

      const state = useInspectionStore.getState();
      expect(state.tasks).toEqual([MOCK_TASK, MOCK_TASK_2]);
      expect(state.total).toBe(2);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('should handle fetch failure', async () => {
      (inspectionApi.getList as jest.Mock).mockRejectedValue(new Error('Network error'));

      await act(async () => {
        await useInspectionStore.getState().fetchTasks();
      });

      const state = useInspectionStore.getState();
      expect(state.loading).toBe(false);
      expect(state.error).toBe('Network error');
    });

    it('should pass filter params', async () => {
      (inspectionApi.getList as jest.Mock).mockResolvedValue({
        data: { items: [MOCK_TASK], total: 1, page: 1, pageSize: 20 },
      });

      await act(async () => {
        await useInspectionStore.getState().fetchTasks({ stationId: 1, status: 'pending' });
      });

      expect(inspectionApi.getList).toHaveBeenCalledWith({ stationId: 1, status: 'pending' });
    });
  });

  describe('fetchTaskDetail', () => {
    it('should fetch detail successfully', async () => {
      (inspectionApi.getDetail as jest.Mock).mockResolvedValue({ data: MOCK_TASK });

      await act(async () => {
        await useInspectionStore.getState().fetchTaskDetail(1);
      });

      const state = useInspectionStore.getState();
      expect(state.selectedTask).toEqual(MOCK_TASK);
      expect(state.loading).toBe(false);
    });

    it('should handle fetch detail failure', async () => {
      (inspectionApi.getDetail as jest.Mock).mockRejectedValue(new Error('Not found'));

      await act(async () => {
        await useInspectionStore.getState().fetchTaskDetail(999);
      });

      const state = useInspectionStore.getState();
      expect(state.selectedTask).toBeNull();
      expect(state.error).toBe('Not found');
    });
  });

  describe('startTask', () => {
    it('should start task successfully', async () => {
      const startedTask = { ...MOCK_TASK, status: 'in_progress' as const };
      (inspectionApi.start as jest.Mock).mockResolvedValue({ data: startedTask });
      useInspectionStore.setState({ tasks: [MOCK_TASK] });

      await act(async () => {
        await useInspectionStore.getState().startTask(1);
      });

      const state = useInspectionStore.getState();
      expect(state.selectedTask?.status).toBe('in_progress');
      expect(state.tasks[0].status).toBe('in_progress');
    });

    it('should handle start failure', async () => {
      (inspectionApi.start as jest.Mock).mockRejectedValue(new Error('Start failed'));

      await act(async () => {
        await useInspectionStore.getState().startTask(1);
      });

      const state = useInspectionStore.getState();
      expect(state.submitError).toBe('Start failed');
    });
  });

  describe('updateItem', () => {
    it('should update item result successfully', async () => {
      const updatedTask = {
        ...MOCK_TASK,
        items: [{ ...MOCK_TASK.items[0], result: 'pass' as const }, ...MOCK_TASK.items.slice(1)],
      };
      (inspectionApi.updateItem as jest.Mock).mockResolvedValue({ data: updatedTask });

      await act(async () => {
        await useInspectionStore.getState().updateItem(1, 1, 'pass');
      });

      const state = useInspectionStore.getState();
      expect(state.selectedTask?.items[0].result).toBe('pass');
    });

    it('should handle update failure', async () => {
      (inspectionApi.updateItem as jest.Mock).mockRejectedValue(new Error('Update failed'));

      await act(async () => {
        await useInspectionStore.getState().updateItem(1, 1, 'fail');
      });

      const state = useInspectionStore.getState();
      expect(state.submitError).toBe('Update failed');
    });
  });

  describe('completeTask', () => {
    it('should complete task successfully', async () => {
      const completedTask = { ...MOCK_TASK, status: 'completed' as const };
      (inspectionApi.complete as jest.Mock).mockResolvedValue({ data: completedTask });
      useInspectionStore.setState({ tasks: [MOCK_TASK] });

      await act(async () => {
        await useInspectionStore.getState().completeTask(1, '巡检完成', 'pass');
      });

      const state = useInspectionStore.getState();
      expect(state.selectedTask?.status).toBe('completed');
      expect(state.tasks[0].status).toBe('completed');
    });

    it('should handle complete failure', async () => {
      (inspectionApi.complete as jest.Mock).mockRejectedValue(new Error('Complete failed'));

      await act(async () => {
        await useInspectionStore.getState().completeTask(1, 'summary', 'pass');
      });

      const state = useInspectionStore.getState();
      expect(state.submitError).toBe('Complete failed');
    });
  });

  describe('setSelectedTask', () => {
    it('should set and clear selected task', () => {
      useInspectionStore.getState().setSelectedTask(MOCK_TASK);
      expect(useInspectionStore.getState().selectedTask).toEqual(MOCK_TASK);

      useInspectionStore.getState().setSelectedTask(null);
      expect(useInspectionStore.getState().selectedTask).toBeNull();
    });
  });

  describe('reset', () => {
    it('should reset all state', () => {
      useInspectionStore.setState({
        tasks: [MOCK_TASK],
        selectedTask: MOCK_TASK,
        total: 1,
        loading: true,
        error: 'error',
        submitting: true,
        submitError: 'error',
      });

      useInspectionStore.getState().reset();

      const state = useInspectionStore.getState();
      expect(state.tasks).toEqual([]);
      expect(state.selectedTask).toBeNull();
      expect(state.total).toBe(0);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.submitting).toBe(false);
      expect(state.submitError).toBeNull();
    });
  });
});
