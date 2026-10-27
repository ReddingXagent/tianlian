import { create } from 'zustand';
import { WorkOrder, WorkOrderRecord } from '../types';
import { workOrderApi, workOrderRecordApi, workOrderTransferApi, WO_PRIORITY_TO_LEVEL } from '../services/api';

interface WorkOrderEnhancedState {
  // Create
  creating: boolean;
  createError: string | null;
  createOrder: (data: {
    title: string;
    description: string;
    stationId: number;
    type: string;
    priority: string;
  }) => Promise<WorkOrder | null>;

  // Assign
  assigning: boolean;
  assignError: string | null;
  assignOrder: (orderId: string, assigneeId: number) => Promise<WorkOrder | null>;

  // Transfer
  transferring: boolean;
  transferError: string | null;
  transferOrder: (orderId: string, assigneeId: number, reason: string) => Promise<WorkOrder | null>;
  urgeOrder: (orderId: string, message: string) => Promise<WorkOrder | null>;

  // Records
  records: WorkOrderRecord[];
  recordsLoading: boolean;
  fetchRecords: (orderId: string) => Promise<void>;
  addRecord: (orderId: string, action: string, note: string) => Promise<void>;

  // Reset
  reset: () => void;
}

export const useWorkOrderEnhancedStore = create<WorkOrderEnhancedState>((set, get) => ({
  creating: false,
  createError: null,
  assigning: false,
  assignError: null,
  transferring: false,
  transferError: null,
  records: [],
  recordsLoading: false,

  createOrder: async (data) => {
    set({ creating: true, createError: null });
    try {
      const faultDesc =
        data.description && data.description !== data.title
          ? `${data.title}: ${data.description}`
          : data.title;
      const response = await workOrderApi.create({
        faultDesc,
        type: data.type,
        level: WO_PRIORITY_TO_LEVEL[data.priority] ?? 'warning',
        stationId: data.stationId,
      });
      set({ creating: false });
      return response.data;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '创建工单失败';
      set({ creating: false, createError: message });
      return null;
    }
  },

  assignOrder: async (orderId, assigneeId) => {
    set({ assigning: true, assignError: null });
    try {
      const response = await workOrderApi.assign(orderId, assigneeId);
      set({ assigning: false });
      return response.data;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '分配工单失败';
      set({ assigning: false, assignError: message });
      return null;
    }
  },

  transferOrder: async (orderId, assigneeId, reason) => {
    set({ transferring: true, transferError: null });
    try {
      await workOrderTransferApi.transfer(orderId, { targetEngineerId: assigneeId, reason });
      const detail = await workOrderApi.getDetail(orderId);
      set({ transferring: false });
      return detail.data;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '转派工单失败';
      set({ transferring: false, transferError: message });
      return null;
    }
  },

  urgeOrder: async (orderId, message) => {
    set({ transferring: true, transferError: null });
    try {
      await workOrderTransferApi.urge(orderId, message);
      const detail = await workOrderApi.getDetail(orderId);
      set({ transferring: false });
      return detail.data;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '催单失败';
      set({ transferring: false, transferError: msg });
      return null;
    }
  },

  fetchRecords: async (orderId) => {
    set({ recordsLoading: true });
    try {
      const response = await workOrderRecordApi.getRecords(orderId);
      set({ records: response.data, recordsLoading: false });
    } catch {
      set({ recordsLoading: false });
    }
  },

  addRecord: async (orderId, action, note) => {
    try {
      await workOrderRecordApi.addRecord(orderId, { action, note });
      // Refresh records
      await get().fetchRecords(orderId);
    } catch {
      // Silently fail
    }
  },

  reset: () => {
    set({
      creating: false,
      createError: null,
      assigning: false,
      assignError: null,
      transferring: false,
      transferError: null,
      records: [],
      recordsLoading: false,
    });
  },
}));
