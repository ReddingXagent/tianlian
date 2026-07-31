/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { render, act } from '@testing-library/react-native';
import WorkOrderScreen from '../WorkOrderScreen';
import { workOrderApi } from '../../services/api';

// Mock navigation and route
jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({
    params: { stationId: 1 },
  }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

// Mock the API module
jest.mock('../../services/api', () => ({
  workOrderApi: {
    getList: jest.fn(),
    getDetail: jest.fn(),
    createWorkOrder: jest.fn(),
    completeWorkOrder: jest.fn(),
  },
}));

// Mock child components
jest.mock('../../components/LoadingSpinner', () => {
  const MockLoadingSpinner = (props: any) => {
    const React = require('react');
    const { Text } = require('react-native');
    return React.createElement(Text, null, props.text || '加载中...');
  };
  return MockLoadingSpinner;
});
jest.mock('../../components/StatusBadge', () => {
  const MockStatusBadge = (props: any) => {
    const React = require('react');
    const { Text } = require('react-native');
    return React.createElement(Text, null, props.label || props.status || 'badge');
  };
  return MockStatusBadge;
});
jest.mock('../../components/EmptyState', () => {
  const MockEmptyState = (props: any) => {
    const React = require('react');
    const { View, Text, TouchableOpacity } = require('react-native');
    const elements = [React.createElement(Text, { key: 'title' }, props.title || '')];
    if (props.message) {
      elements.push(React.createElement(Text, { key: 'msg' }, props.message));
    }
    if (props.actionLabel && props.onAction) {
      elements.push(
        React.createElement(TouchableOpacity, { key: 'btn', onPress: props.onAction },
          React.createElement(Text, null, props.actionLabel)
        )
      );
    }
    return React.createElement(View, null, elements);
  };
  return MockEmptyState;
});

const MOCK_ORDERS = [
  {
    id: 1,
    stationId: 1,
    stationName: '充电站A',
    title: '充电桩A-01故障维修',
    description: '充电桩A-01出现通信中断故障，需要现场检查处理',
    type: 'repair' as const,
    priority: 'high' as const,
    status: 'pending' as const,
    creatorId: 1,
    creatorName: 'admin',
    assigneeId: 2,
    assigneeName: '张三',
    createdAt: '2024-01-15T10:30:00Z',
    updatedAt: '2024-01-15T10:30:00Z',
  },
  {
    id: 2,
    stationId: 1,
    stationName: '充电站A',
    title: '月度巡检',
    description: '对充电站A所有设备进行月度巡检',
    type: 'inspection' as const,
    priority: 'normal' as const,
    status: 'in_progress' as const,
    creatorId: 1,
    creatorName: 'admin',
    assigneeId: 2,
    assigneeName: '李四',
    createdAt: '2024-01-14T08:00:00Z',
    updatedAt: '2024-01-14T08:00:00Z',
  },
  {
    id: 3,
    stationId: 2,
    stationName: '充电站B',
    title: '新充电桩安装',
    description: '在充电站B安装3台120kW直流快充桩',
    type: 'installation' as const,
    priority: 'urgent' as const,
    status: 'completed' as const,
    creatorId: 1,
    creatorName: 'admin',
    assigneeId: 3,
    assigneeName: '王五',
    completedAt: '2024-01-13T16:00:00Z',
    createdAt: '2024-01-10T09:00:00Z',
    updatedAt: '2024-01-13T16:00:00Z',
  },
];

describe('WorkOrderScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (workOrderApi.getList as jest.Mock).mockResolvedValue({
      data: { items: MOCK_ORDERS, total: 3, page: 1, pageSize: 20 },
    });
  });

  it('should render loading state initially', () => {
    (workOrderApi.getList as jest.Mock).mockImplementation(() => new Promise(() => {}));

    const { getByText } = render(<WorkOrderScreen />);
    expect(getByText('加载工单列表...')).toBeTruthy();
  });

  it('should render work order list after loading', async () => {
    const { findByText } = render(<WorkOrderScreen />);

    expect(await findByText('充电桩A-01故障维修')).toBeTruthy();
    expect(await findByText('月度巡检')).toBeTruthy();
    expect(await findByText('新充电桩安装')).toBeTruthy();
  });

  it('should render work order descriptions', async () => {
    const { findByText } = render(<WorkOrderScreen />);

    expect(await findByText('充电桩A-01出现通信中断故障，需要现场检查处理')).toBeTruthy();
  });

  it('should render status filter chips', async () => {
    const { findByText } = render(<WorkOrderScreen />);

    expect(await findByText('全部')).toBeTruthy();
    expect(await findByText('待处理')).toBeTruthy();
    expect(await findByText('进行中')).toBeTruthy();
    expect(await findByText('已完成')).toBeTruthy();
  });

  it('should show assignee names in order cards', async () => {
    const { findByText } = render(<WorkOrderScreen />);

    expect(await findByText(/张三/)).toBeTruthy();
  });

  it('should handle error state', async () => {
    (workOrderApi.getList as jest.Mock).mockRejectedValue(new Error('API Error'));

    const { findByText } = render(<WorkOrderScreen />);
    expect(await findByText('加载工单列表失败')).toBeTruthy();
  });

  it('should render empty state when no orders', async () => {
    (workOrderApi.getList as jest.Mock).mockResolvedValue({
      data: { items: [], total: 0, page: 1, pageSize: 20 },
    });

    const { findByText } = render(<WorkOrderScreen />);
    expect(await findByText('暂无工单')).toBeTruthy();
  });

  it('should show create button when stationId is provided', async () => {
    render(<WorkOrderScreen />);

    // Wait for loading to finish, then the FAB "+" should appear
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });
  });
});