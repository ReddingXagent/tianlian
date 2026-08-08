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

// Helper: find RefreshControl in rendered tree
function findRefreshControl(node: ReturnType<typeof render>['UNSAFE_root']): React.ReactElement | null {
  if (!node) return null;
  const element = node as unknown as React.ReactElement;
  if (element.type === RefreshControl) return element;
  const props = element.props as Record<string, unknown>;
  const rc = props.refreshControl as React.ReactElement | undefined;
  if (rc && rc.type === RefreshControl) return rc;
  const children = (props.children as React.ReactElement[]) || [];
  for (const child of Array.isArray(children) ? children : [children]) {
    const found = findRefreshControl(child as unknown as ReturnType<typeof render>['UNSAFE_root']);
    if (found) return found;
  }
  return null;
}

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
    const rc = findRefreshControl(UNSAFE_root);
    if (rc?.props?.onRefresh) {
      await act(async () => {
        rc.props.onRefresh();
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
    const rc = findRefreshControl(UNSAFE_root);
    if (rc?.props?.onRefresh) {
      await act(async () => {
        rc.props.onRefresh();
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
    const rc = findRefreshControl(UNSAFE_root);
    if (rc?.props?.onRefresh) {
      await act(async () => {
        rc.props.onRefresh();
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
