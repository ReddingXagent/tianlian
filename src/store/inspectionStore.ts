import { create } from 'zustand';
import { InspectionTask, PaginatedData } from '../types';
import { inspectionApi } from '../services/api';

interface InspectionState {
  tasks: InspectionTask[];
  selectedTask: InspectionTask | null;
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  error: string | null;
  submitting: boolean;
  submitError: string | null;

  fetchTasks: (params?: {
    stationId?: number;
    status?: string;
    type?: string;
    page?: number;
    pageSize?: number;
  }) => Promise<void>;
  fetchTaskDetail: (id: number) => Promise<void>;
  startTask: (id: number) => Promise<void>;
  updateItem: (taskId: number, itemId: number, result: string, note?: string) => Promise<void>;
  completeTask: (id: number, summary: string, overall: string) => Promise<void>;
  setSelectedTask: (task: InspectionTask | null) => void;
  reset: () => void;
}

export const useInspectionStore = create<InspectionState>((set, get) => ({
  tasks: [],
  selectedTask: null,
  total: 0,
  page: 1,
  pageSize: 20,
  loading: false,
  error: null,
  submitting: false,
  submitError: null,

  fetchTasks: async (params) => {
    set({ loading: true, error: null });
    try {
      const response = await inspectionApi.getList(params);
      const data: PaginatedData<InspectionTask> = response.data;
      set({
        tasks: data.items,
        total: data.total,
        page: data.page,
        pageSize: data.pageSize,
        loading: false,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取巡检任务失败';
      set({ loading: false, error: message });
    }
  },

  fetchTaskDetail: async (id) => {
    set({ loading: true, error: null });
    try {
      const response = await inspectionApi.getDetail(id);
      set({ selectedTask: response.data, loading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取巡检详情失败';
      set({ loading: false, error: message });
    }
  },

  startTask: async (id) => {
    set({ submitting: true, submitError: null });
    try {
      const response = await inspectionApi.start(id);
      set({ selectedTask: response.data, submitting: false });
      const { tasks } = get();
      set({
        tasks: tasks.map((t) => (t.id === id ? response.data : t)),
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '启动巡检失败';
      set({ submitting: false, submitError: message });
    }
  },

  updateItem: async (taskId, itemId, result, note) => {
    set({ submitting: true, submitError: null });
    try {
      const response = await inspectionApi.updateItem(taskId, itemId, { result, note });
      set({ selectedTask: response.data, submitting: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '更新检查项失败';
      set({ submitting: false, submitError: message });
    }
  },

  completeTask: async (id, summary, overall) => {
    set({ submitting: true, submitError: null });
    try {
      const response = await inspectionApi.complete(id, { summary, overall });
      set({ selectedTask: response.data, submitting: false });
      const { tasks } = get();
      set({
        tasks: tasks.map((t) => (t.id === id ? response.data : t)),
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '完成巡检失败';
      set({ submitting: false, submitError: message });
    }
  },

  setSelectedTask: (task) => {
    set({ selectedTask: task });
  },

  reset: () => {
    set({
      tasks: [],
      selectedTask: null,
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      error: null,
      submitting: false,
      submitError: null,
    });
  },
}));
