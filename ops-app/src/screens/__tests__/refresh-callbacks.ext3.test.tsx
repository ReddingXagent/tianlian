/**
 * ext3 — refresh/retry callback coverage across screens
 * Target lines: DashboardScreen:62, InspectionDetailScreen:86+106,
 * InspectionListScreen:133, WorkOrderListScreen:109
 */
import { render, act } from '@testing-library/react-native';
import React from 'react';
import { RefreshControl } from 'react-native';

// ── Mocks ────────────────────────────────────────────────────────────
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
  useFocusEffect: jest.fn(cb => cb()),
  useRoute: () => ({ params: { taskId: 1 } }),
}));

jest.mock('../../store/dashboardStore', () => ({
  useDashboardStore: jest.fn(),
}));

jest.mock('../../store/inspectionStore', () => ({
  useInspectionStore: jest.fn(),
}));

jest.mock('../../store/workOrderStore', () => ({
  useWorkOrderStore: jest.fn(),
}));

import DashboardScreen from '../DashboardScreen';
import InspectionListScreen from '../InspectionListScreen';
import WorkOrderListScreen from '../WorkOrderListScreen';
import InspectionDetailScreen from '../InspectionDetailScreen';
import { useDashboardStore } from '../../store/dashboardStore';
import { useInspectionStore } from '../../store/inspectionStore';
import { useWorkOrderStore } from '../../store/workOrderStore';

const mockFetchDashboard = jest.fn().mockResolvedValue(undefined);
const mockSetPeriod = jest.fn();
const mockFetchTasks = jest.fn().mockResolvedValue(undefined);
const mockFetchOrders = jest.fn().mockResolvedValue(undefined);

const DASHBOARD_DATA = {
  stats: { totalStations: 10, totalDevices: 50, activeAlarms: 5, pendingOrders: 3 },
  deviceHealth: { online: 40, offline: 5, fault: 5, onlineRate: 80 },
  trends: [],
  recentOrders: [],
};

const INSPECTION_TASKS = [
  {
    id: 1, stationId: 1, stationName: '充电站A', deviceId: 1, deviceName: '充电桩01',
    type: 'daily', status: 'pending', scheduledDate: '2024-01-15T00:00:00Z',
    description: '日常巡检任务', items: [{ id: 1, name: '检查项', expected: '正常' }],
    createdAt: '', updatedAt: '',
  },
];

const WORK_ORDERS = [
  {
    id: 1, title: '工单1', description: 'desc', status: 'pending',
    priority: 'high', type: 'fault', stationId: 1, stationName: '充电站A',
    createdAt: '2024-01-15T00:00:00Z', updatedAt: '',
  },
];


describe('refresh callbacks across screens', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchDashboard.mockResolvedValue(undefined);
    mockFetchTasks.mockResolvedValue(undefined);
    mockFetchOrders.mockResolvedValue(undefined);
  });

  // ── DashboardScreen: trigger onRefresh (line 62) ──
  it('DashboardScreen: pull-to-refresh triggers loadData(true)', async () => {
    (useDashboardStore as unknown as jest.Mock).mockReturnValue({
      data: DASHBOARD_DATA, loading: false, error: null,
      selectedPeriod: 'week', fetchDashboard: mockFetchDashboard, setPeriod: mockSetPeriod,
    });

    const { UNSAFE_root } = render(<DashboardScreen />);
    // F1206: walk()树遍历在FlatList/ScrollView宿主形态下找不到RefreshControl(假绿),
    // 改findAllByType直查+fail-fast断言 — 找不到时测试变红而非静默空转
    const all = (UNSAFE_root as unknown as {
      findAllByType?: (type: unknown) => { props?: { onRefresh?: () => void } }[];
    }).findAllByType?.(RefreshControl);
    const rc = all?.[0];
    expect(rc).toBeDefined(); // F1206 fail-fast: RefreshControl找不到时变红
    expect(typeof rc?.props?.onRefresh).toBe('function'); // F1206 fail-fast
    if (rc?.props?.onRefresh) {
      await act(async () => {
        rc?.props?.onRefresh?.(); // F1206: 可选链调用, TS窄化通过
        await new Promise(r => setTimeout(r, 50));
      });
      expect(mockFetchDashboard).toHaveBeenCalled();
    }
  });

  // ── InspectionListScreen: trigger onRefresh (line 133) ──
  it('InspectionListScreen: pull-to-refresh triggers loadData(true)', async () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: INSPECTION_TASKS, loading: false, error: null, total: 1,
      fetchTasks: mockFetchTasks,
    });

    const { UNSAFE_root } = render(<InspectionListScreen />);
    // F1206: walk()树遍历在FlatList/ScrollView宿主形态下找不到RefreshControl(假绿),
    // 改findAllByType直查+fail-fast断言 — 找不到时测试变红而非静默空转
    const all = (UNSAFE_root as unknown as {
      findAllByType?: (type: unknown) => { props?: { onRefresh?: () => void } }[];
    }).findAllByType?.(RefreshControl);
    const rc = all?.[0];
    expect(rc).toBeDefined(); // F1206 fail-fast: RefreshControl找不到时变红
    expect(typeof rc?.props?.onRefresh).toBe('function'); // F1206 fail-fast
    if (rc?.props?.onRefresh) {
      await act(async () => {
        rc?.props?.onRefresh?.(); // F1206: 可选链调用, TS窄化通过
        await new Promise(r => setTimeout(r, 50));
      });
      expect(mockFetchTasks).toHaveBeenCalled();
    }
  });

  // ── WorkOrderListScreen: trigger onRefresh (line 109) ──
  it('WorkOrderListScreen: pull-to-refresh triggers loadData(true)', async () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue({
      orders: WORK_ORDERS, loading: false, error: null, total: 1,
      fetchOrders: mockFetchOrders,
    });

    const { UNSAFE_root } = render(<WorkOrderListScreen />);
    // F1206: walk()树遍历在FlatList/ScrollView宿主形态下找不到RefreshControl(假绿),
    // 改findAllByType直查+fail-fast断言 — 找不到时测试变红而非静默空转
    const all = (UNSAFE_root as unknown as {
      findAllByType?: (type: unknown) => { props?: { onRefresh?: () => void } }[];
    }).findAllByType?.(RefreshControl);
    const rc = all?.[0];
    expect(rc).toBeDefined(); // F1206 fail-fast: RefreshControl找不到时变红
    expect(typeof rc?.props?.onRefresh).toBe('function'); // F1206 fail-fast
    if (rc?.props?.onRefresh) {
      await act(async () => {
        rc?.props?.onRefresh?.(); // F1206: 可选链调用, TS窄化通过
        await new Promise(r => setTimeout(r, 50));
      });
      expect(mockFetchOrders).toHaveBeenCalled();
    }
  });
});

// ── InspectionDetailScreen: getResultIcon 'na' case (line 86) ──
describe('InspectionDetailScreen getResultIcon na case', () => {
  const mockFetchDetail = jest.fn().mockResolvedValue(undefined);
  const mockStartTask = jest.fn();
  const mockUpdateItem = jest.fn();
  const mockCompleteTask = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders ➖ icon for item result "na"', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      selectedTask: {
        id: 1, stationId: 1, stationName: '充电站A', deviceId: 1, deviceName: '充电桩01',
        type: 'daily', status: 'in_progress', scheduledDate: '2024-01-15T00:00:00Z',
        completedDate: null, description: '日常巡检', items: [
          { id: 1, name: '外观检查', result: 'na' },
        ],
      },
      loading: false, error: null, submitting: false,
      fetchTaskDetail: mockFetchDetail, startTask: mockStartTask,
      updateItem: mockUpdateItem, completeTask: mockCompleteTask,
    });

    const { getByText } = render(<InspectionDetailScreen />);
    expect(getByText('➖')).toBeTruthy();
  });
});
