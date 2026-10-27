/**
 * inspectionStore 扩展覆盖率 — non-Error throw 分支
 * 目标: branches 50%(7/14) → 100%
 */
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
  description: '日检任务',
  items: [{ id: 1, name: '外观检查', expected: '无破损' }],
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
};

describe('useInspectionStore — non-Error throw 分支', () => {
  beforeEach(() => {
    useInspectionStore.getState().reset();
    jest.clearAllMocks();
  });

  it('fetchTasks: non-Error throw → 默认错误消息', async () => {
    (inspectionApi.getList as jest.Mock).mockRejectedValue('string error');

    await act(async () => {
      await useInspectionStore.getState().fetchTasks();
    });

    expect(useInspectionStore.getState().error).toBe('获取巡检任务失败');
    expect(useInspectionStore.getState().loading).toBe(false);
  });

  it('fetchTaskDetail: non-Error throw → 默认错误消息', async () => {
    (inspectionApi.getDetail as jest.Mock).mockRejectedValue({ code: 500 });

    await act(async () => {
      await useInspectionStore.getState().fetchTaskDetail(1);
    });

    expect(useInspectionStore.getState().error).toBe('获取巡检详情失败');
    expect(useInspectionStore.getState().loading).toBe(false);
  });

  it('startTask: non-Error throw → 默认错误消息', async () => {
    (inspectionApi.start as jest.Mock).mockRejectedValue(null);

    await act(async () => {
      await useInspectionStore.getState().startTask(1);
    });

    expect(useInspectionStore.getState().submitError).toBe('启动巡检失败');
    expect(useInspectionStore.getState().submitting).toBe(false);
  });

  it('updateItem: non-Error throw → 默认错误消息', async () => {
    (inspectionApi.updateItem as jest.Mock).mockRejectedValue(undefined);

    await act(async () => {
      await useInspectionStore.getState().updateItem(1, 1, 'fail');
    });

    expect(useInspectionStore.getState().submitError).toBe('更新检查项失败');
    expect(useInspectionStore.getState().submitting).toBe(false);
  });

  it('completeTask: non-Error throw → 默认错误消息', async () => {
    (inspectionApi.complete as jest.Mock).mockRejectedValue(42);

    await act(async () => {
      await useInspectionStore.getState().completeTask(1, 'summary', 'pass');
    });

    expect(useInspectionStore.getState().submitError).toBe('完成巡检失败');
    expect(useInspectionStore.getState().submitting).toBe(false);
  });

  it('completeTask: 不在tasks列表中的task → tasks不变', async () => {
    const completedTask = { ...MOCK_TASK, id: 999, status: 'completed' as const };
    (inspectionApi.complete as jest.Mock).mockResolvedValue({ data: completedTask });
    useInspectionStore.setState({ tasks: [MOCK_TASK] });

    await act(async () => {
      await useInspectionStore.getState().completeTask(999, 'summary', 'pass');
    });

    // tasks[0] should remain unchanged (id !== 999)
    expect(useInspectionStore.getState().tasks[0].status).toBe('pending');
  });

  it('startTask: 不在tasks列表中的task → tasks不变', async () => {
    const startedTask = { ...MOCK_TASK, id: 999, status: 'in_progress' as const };
    (inspectionApi.start as jest.Mock).mockResolvedValue({ data: startedTask });
    useInspectionStore.setState({ tasks: [MOCK_TASK] });

    await act(async () => {
      await useInspectionStore.getState().startTask(999);
    });

    expect(useInspectionStore.getState().tasks[0].status).toBe('pending');
  });
});
