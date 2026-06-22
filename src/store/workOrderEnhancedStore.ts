import { create } from 'zustand';
import { WorkOrder, WorkOrderRecord } from '../types';
import { workOrderApi, workOrderRecordApi, workOrderTransferApi } from '../services/api';

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
  assignOrder: (orderId: number, assigneeId: number) => Promise<WorkOrder | null>;

  // Transfer
  transferring: boolean;
  transferError: string | null;
  transferOrder: (orderId: number, assigneeId: number, reason: string) => Promise<WorkOrder | null>;
  escalateOrder: (orderId: number, reason: string) => Promise<WorkOrder | null>;

  // Records
  records: WorkOrderRecord[];
  recordsLoading: boolean;
  fetchRecords: (orderId: number) => Promise<void>;
  addRecord: (orderId: number, action: string, note: string) => Promise<void>;

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
      const response = await workOrderApi.create(data as Partial<WorkOrder>);
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
      const response = await workOrderTransferApi.transfer(orderId, { assigneeId, reason });
      set({ transferring: false });
      return response.data;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '转派工单失败';
      set({ transferring: false, transferError: message });
      return null;
    }
  },

  escalateOrder: async (orderId, reason) => {
    set({ transferring: true, transferError: null });
    try {
      const response = await workOrderTransferApi.escalate(orderId, reason);
      set({ transferring: false });
      return response.data;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '升级工单失败';
      set({ transferring: false, transferError: message });
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
