import { create } from 'zustand';
import { DeviceControlLog } from '../types';

const MAX_LOGS = 50;

interface DeviceControlLogState {
  logs: DeviceControlLog[];
  addLog: (entry: Omit<DeviceControlLog, 'id' | 'createdAt'>) => void;
  clearLogs: () => void;
  removeLog: (id: number) => void;
  reset: () => void;
}

// 本地自增 id（仅用于列表 key，不持久化）
let _seq = 0;
const nextId = (): number => {
  _seq += 1;
  return _seq;
};

/**
 * 设备远程控制操作日志 store（本地）。
 * 每次远程控制（启动/停止/重启/复位）记录一条日志，保留最近 MAX_LOGS 条。
 */
export const useDeviceControlLogStore = create<DeviceControlLogState>((set) => ({
  logs: [],

  addLog: (entry) =>
    set((state) => ({
      logs: [
        { ...entry, id: nextId(), createdAt: new Date().toISOString() },
        ...state.logs,
      ].slice(0, MAX_LOGS),
    })),

  clearLogs: () => set({ logs: [] }),

  removeLog: (id) => set((state) => ({ logs: state.logs.filter((l) => l.id !== id) })),

  reset: () => set({ logs: [] }),
}));
