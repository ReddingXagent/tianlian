import { act } from '@testing-library/react-native';
import { useDeviceControlLogStore } from '../deviceControlLogStore';

const baseEntry = {
  deviceId: 101,
  deviceName: '充电桩A-01',
  command: 'start' as const,
  commandLabel: '启动',
  status: 'success' as const,
  message: '启动指令已发送',
  operator: '当前用户',
};

describe('useDeviceControlLogStore', () => {
  beforeEach(() => {
    useDeviceControlLogStore.getState().reset();
  });

  it('should start with empty logs', () => {
    expect(useDeviceControlLogStore.getState().logs).toEqual([]);
  });

  it('should prepend a log entry with generated id and createdAt', () => {
    act(() => {
      useDeviceControlLogStore.getState().addLog(baseEntry);
    });

    const logs = useDeviceControlLogStore.getState().logs;
    expect(logs).toHaveLength(1);
    expect(logs[0]).toMatchObject(baseEntry);
    expect(typeof logs[0].id).toBe('number');
    expect(typeof logs[0].createdAt).toBe('string');
  });

  it('should keep the newest entry at the top', () => {
    act(() => {
      useDeviceControlLogStore.getState().addLog(baseEntry);
      useDeviceControlLogStore.getState().addLog({ ...baseEntry, commandLabel: '停止', command: 'stop' });
    });

    const logs = useDeviceControlLogStore.getState().logs;
    expect(logs).toHaveLength(2);
    expect(logs[0].commandLabel).toBe('停止');
    expect(logs[1].commandLabel).toBe('启动');
  });

  it('should record both success and failed statuses', () => {
    act(() => {
      useDeviceControlLogStore.getState().addLog(baseEntry);
      useDeviceControlLogStore.getState().addLog({ ...baseEntry, status: 'failed', message: '失败' });
    });

    const logs = useDeviceControlLogStore.getState().logs;
    expect(logs[0].status).toBe('failed');
    expect(logs[1].status).toBe('success');
  });

  it('should cap logs at 50 entries', () => {
    act(() => {
      for (let i = 0; i < 60; i++) {
        useDeviceControlLogStore.getState().addLog({ ...baseEntry, message: `op-${i}` });
      }
    });

    const logs = useDeviceControlLogStore.getState().logs;
    expect(logs).toHaveLength(50);
    // 最新的是 op-59，最旧保留的是 op-10
    expect(logs[0].message).toBe('op-59');
    expect(logs[49].message).toBe('op-10');
  });

  it('should remove a single log by id', () => {
    act(() => {
      useDeviceControlLogStore.getState().addLog(baseEntry);
      useDeviceControlLogStore.getState().addLog({ ...baseEntry, commandLabel: '重启' });
    });

    const targetId = useDeviceControlLogStore.getState().logs[0].id;
    act(() => {
      useDeviceControlLogStore.getState().removeLog(targetId);
    });

    const logs = useDeviceControlLogStore.getState().logs;
    expect(logs).toHaveLength(1);
    expect(logs.find((l) => l.id === targetId)).toBeUndefined();
  });

  it('should clear all logs', () => {
    act(() => {
      useDeviceControlLogStore.getState().addLog(baseEntry);
      useDeviceControlLogStore.getState().addLog(baseEntry);
      useDeviceControlLogStore.getState().clearLogs();
    });

    expect(useDeviceControlLogStore.getState().logs).toEqual([]);
  });
});
