/**
 * ext5 — isRefresh=true path coverage for loadData guards
 * Target: DashboardScreen:27,29 | InspectionListScreen:45,49
 *         WorkOrderListScreen:36,40 | InspectionDetailScreen:46,48
 *         WorkOrderDetailScreen:68,70
 */
import { render, act } from '@testing-library/react-native';
import React from 'react';
import { ScrollView, FlatList } from 'react-native';

// ── Navigation mock ──────────────────────────────────────────────────
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn(), setOptions: jest.fn() }),
  useFocusEffect: jest.fn(cb => cb()),
  useRoute: () => ({ params: { taskId: 1, orderId: 1 } }),
}));

// ── API mock (avoid expo-secure-store import chain) ──────────────────
jest.mock('../../services/api', () => ({
  workOrderRecordApi: { getRecords: jest.fn().mockResolvedValue({ data: [] }) },
  workOrderActionApi: {
    accept: jest.fn().mockResolvedValue(undefined),
    start: jest.fn().mockResolvedValue(undefined),
    complete: jest.fn().mockResolvedValue(undefined),
    transfer: jest.fn().mockResolvedValue(undefined),
    urge: jest.fn().mockResolvedValue(undefined),
  },
}));

// ── Store mocks ──────────────────────────────────────────────────────
jest.mock('../../store/dashboardStore', () => ({ useDashboardStore: jest.fn() }));
jest.mock('../../store/inspectionStore', () => ({ useInspectionStore: jest.fn() }));
jest.mock('../../store/workOrderStore', () => ({ useWorkOrderStore: jest.fn() }));

import DashboardScreen from '../DashboardScreen';
import InspectionListScreen from '../InspectionListScreen';
import WorkOrderListScreen from '../WorkOrderListScreen';
import InspectionDetailScreen from '../InspectionDetailScreen';
import WorkOrderDetailScreen from '../WorkOrderDetailScreen';
import { useDashboardStore } from '../../store/dashboardStore';
import { useInspectionStore } from '../../store/inspectionStore';
import { useWorkOrderStore } from '../../store/workOrderStore';

const mockFetchDashboard = jest.fn().mockResolvedValue(undefined);
const mockSetPeriod = jest.fn();
const mockFetchTasks = jest.fn().mockResolvedValue(undefined);
const mockFetchTaskDetail = jest.fn().mockResolvedValue(undefined);
const mockCompleteTask = jest.fn().mockResolvedValue(undefined);
const mockFetchOrders = jest.fn().mockResolvedValue(undefined);
const mockFetchOrderDetail = jest.fn().mockResolvedValue(undefined);
const mockLoadRecords = jest.fn().mockResolvedValue(undefined);

const DASHBOARD_DATA = {
  stats: { totalStations: 10, totalDevices: 50, activeAlarms: 5, pendingOrders: 3 },
  deviceHealth: { online: 40, offline: 5, fault: 5, onlineRate: 80 },
  trends: [], recentOrders: [], topFaultDevices: [],
};

const INSPECTION_TASKS = [
  { id: 1, stationId: 1, stationName: '充电站A', deviceId: 1, deviceName: '充电桩01',
    type: 'daily', status: 'pending', scheduledDate: '2024-01-15T00:00:00Z',
    description: '日常巡检', items: [{ id: 1, name: '检查项', expected: '正常' }],
    createdAt: '', updatedAt: '' },
];

const WORK_ORDERS = [
  { id: 1, title: '工单1', description: 'desc', status: 'pending',
    type: 'fault', priority: 'high', stationId: 1, stationName: '充电站A',
    createdAt: '2024-01-15T00:00:00Z', updatedAt: '' },
];

const TASK_DETAIL = {
  id: 1, stationId: 1, stationName: '充电站A', deviceId: 1, deviceName: '充电桩01',
  type: 'daily', status: 'pending', scheduledDate: '2024-01-15T00:00:00Z',
  description: '日常巡检', items: [{ id: 1, name: '检查项', expected: '正常', result: undefined, note: '' }],
  createdAt: '', updatedAt: '',
};

const ORDER_DETAIL = {
  id: 1, title: '工单1', description: 'desc', status: 'pending',
  type: 'fault', priority: 'high', stationId: 1, stationName: '充电站A',
  createdAt: '2024-01-15T00:00:00Z', updatedAt: '', creator: { name: 'test' },
  assignee: { name: 'worker' }, timeline: [],
};

/** Traverse rendered tree to find RefreshControl via refreshControl prop */
// F1205: any收窄 — ReactTestInstance鸭子分支仅判能力, 容器类型用ComponentType具体化
function getOnRefresh(
  root: ({ findAllByType?: (type: unknown) => unknown[] } & { props?: { refreshControl?: { props?: { onRefresh?: () => void } }; children?: unknown } }) | null,
  containerType: React.ComponentType<Record<string, never>> | (typeof ScrollView | typeof FlatList),
): (() => void) | null {
  const all = root && typeof root.findAllByType === 'function' ? root.findAllByType(containerType) : [];
  for (const node of all as { props?: { refreshControl?: { props?: { onRefresh?: () => void } } } }[]) {
    const rc = node.props?.refreshControl;
    if (rc?.props?.onRefresh) return rc.props.onRefresh;
  }
  // Also try UNSAFE_allChildren traversal
  function walk(node: { props?: { refreshControl?: { props?: { onRefresh?: () => void } }; children?: unknown } } | null): (() => void) | null {
    if (!node) return null;
    const rc = node.props?.refreshControl;
    if (rc?.props?.onRefresh) return rc.props.onRefresh;
    if (node.props?.children) {
      const arr = Array.isArray(node.props.children) ? node.props.children : [node.props.children];
      for (const c of arr) {
        if (c && typeof c === 'object') {
          const r = walk(c);
          if (r) return r;
        }
      }
    }
    return null;
  }
  return walk(root);
}

beforeEach(() => {
  jest.clearAllMocks();
});

// ── DashboardScreen: isRefresh=true ──
it('DashboardScreen: loadData(true) covers isRefresh setRefreshing guards', async () => {
  (useDashboardStore as unknown as jest.Mock).mockReturnValue({
    data: DASHBOARD_DATA, loading: false, error: null,
    selectedPeriod: 'week', fetchDashboard: mockFetchDashboard, setPeriod: mockSetPeriod,
  });

  const { UNSAFE_root } = render(<DashboardScreen />);

  const onRefresh = getOnRefresh(UNSAFE_root, ScrollView);
  if (onRefresh) {
    await act(async () => {
      onRefresh();
      await new Promise(r => setTimeout(r, 50));
    });
  }

  // fetchDashboard is called on focus AND on refresh; verify at least 2 calls (initial + refresh)
  expect(mockFetchDashboard.mock.calls.length).toBeGreaterThanOrEqual(2);
});

// ── InspectionListScreen: isRefresh=true ──
it('InspectionListScreen: loadData(true) covers isRefresh guards', async () => {
  (useInspectionStore as unknown as jest.Mock).mockReturnValue({
    tasks: INSPECTION_TASKS, loading: false, error: null, total: 1,
    fetchTasks: mockFetchTasks,
  });

  const { UNSAFE_root } = render(<InspectionListScreen />);

  const onRefresh = getOnRefresh(UNSAFE_root, FlatList);
  if (onRefresh) {
    await act(async () => {
      onRefresh();
      await new Promise(r => setTimeout(r, 50));
    });
  }

  // fetchTasks is called on focus AND on refresh; verify at least 2 calls
  expect(mockFetchTasks.mock.calls.length).toBeGreaterThanOrEqual(2);
});

// ── WorkOrderListScreen: isRefresh=true ──
it('WorkOrderListScreen: loadData(true) covers isRefresh guards', async () => {
  (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
    orders: WORK_ORDERS, loading: false, error: null, total: 1,
    fetchOrders: mockFetchOrders,
  });

  const { UNSAFE_root } = render(<WorkOrderListScreen />);

  const onRefresh = getOnRefresh(UNSAFE_root, FlatList);
  if (onRefresh) {
    await act(async () => {
      onRefresh();
      await new Promise(r => setTimeout(r, 50));
    });
  }

  // fetchOrders is called on focus AND on refresh; verify at least 2 calls
  expect(mockFetchOrders.mock.calls.length).toBeGreaterThanOrEqual(2);
});

// ── InspectionDetailScreen: isRefresh=true ──
it('InspectionDetailScreen: loadData(true) covers isRefresh guards', async () => {
  (useInspectionStore as unknown as jest.Mock).mockReturnValue({
    task: TASK_DETAIL, loading: false, error: null,
    fetchTaskDetail: mockFetchTaskDetail, completeTask: mockCompleteTask,
  });

  const { UNSAFE_root } = render(<InspectionDetailScreen />);

  const onRefresh = getOnRefresh(UNSAFE_root, ScrollView);
  if (onRefresh) {
    await act(async () => {
      onRefresh();
      await new Promise(r => setTimeout(r, 50));
    });
  }

  // fetchTaskDetail is called on focus AND on refresh; verify at least 2 calls
  expect(mockFetchTaskDetail.mock.calls.length).toBeGreaterThanOrEqual(2);
});

// ── WorkOrderDetailScreen: isRefresh=true ──
it('WorkOrderDetailScreen: loadData(true) covers isRefresh guards', async () => {
  (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
    order: ORDER_DETAIL, loading: false, error: null,
    records: [], fetchOrderDetail: mockFetchOrderDetail, loadRecords: mockLoadRecords,
  });

  const { UNSAFE_root } = render(<WorkOrderDetailScreen />);

  const onRefresh = getOnRefresh(UNSAFE_root, ScrollView);
  if (onRefresh) {
    await act(async () => {
      onRefresh();
      await new Promise(r => setTimeout(r, 50));
    });
  }

  // fetchOrderDetail is called on focus AND on refresh; verify at least 2 calls
  expect(mockFetchOrderDetail.mock.calls.length).toBeGreaterThanOrEqual(2);
});
