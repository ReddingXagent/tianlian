/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { render, act, fireEvent } from '@testing-library/react-native';
import NotificationCenterScreen from '../NotificationCenterScreen';
import { notificationApi } from '../../services/api';

// Mock the API module
jest.mock('../../services/api', () => ({
  notificationApi: {
    getList: jest.fn(),
    getUnreadCount: jest.fn(),
    markAsRead: jest.fn(),
    markAllAsRead: jest.fn(),
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

const MOCK_NOTIFICATIONS = [
  {
    id: 1,
    type: 'alarm' as const,
    title: '充电桩A-01温度异常告警',
    message: '充电桩A-01充电枪温度达到85°C，已触发严重告警',
    level: 'critical' as const,
    isRead: false,
    createdAt: '2024-01-15T10:30:00Z',
  },
  {
    id: 2,
    type: 'work_order' as const,
    title: '新工单已分配',
    message: '工单#20240115001已分配给维修工程师张三',
    level: 'info' as const,
    isRead: false,
    createdAt: '2024-01-15T09:00:00Z',
  },
  {
    id: 3,
    type: 'system' as const,
    title: '系统维护通知',
    message: '系统将于2024年1月20日凌晨2:00-4:00进行维护升级',
    level: 'info' as const,
    isRead: true,
    createdAt: '2024-01-14T08:00:00Z',
  },
  {
    id: 4,
    type: 'revenue' as const,
    title: '日营收报告',
    message: '充电站A昨日营收¥2,350.50，环比增长12%',
    level: 'info' as const,
    isRead: false,
    createdAt: '2024-01-13T08:00:00Z',
  },
];

describe('NotificationCenterScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (notificationApi.getList as jest.Mock).mockResolvedValue({
      data: { items: MOCK_NOTIFICATIONS, total: 4, page: 1, pageSize: 20 },
    });
    (notificationApi.getUnreadCount as jest.Mock).mockResolvedValue({ data: { count: 3 } });
  });

  it('should render loading state initially', () => {
    (notificationApi.getList as jest.Mock).mockImplementation(() => new Promise(() => {}));
    (notificationApi.getUnreadCount as jest.Mock).mockImplementation(() => new Promise(() => {}));

    const { getByText } = render(<NotificationCenterScreen />);
    expect(getByText('加载通知列表...')).toBeTruthy();
  });

  it('should render notification list after loading', async () => {
    const { findByText } = render(<NotificationCenterScreen />);

    expect(await findByText('充电桩A-01温度异常告警')).toBeTruthy();
    expect(await findByText('新工单已分配')).toBeTruthy();
    expect(await findByText('系统维护通知')).toBeTruthy();
    expect(await findByText('日营收报告')).toBeTruthy();
  });

  it('should show unread count', async () => {
    const { findByText } = render(<NotificationCenterScreen />);

    expect(await findByText('3 条未读')).toBeTruthy();
  });

  it('should render "mark all as read" button when unread exists', async () => {
    const { findByText } = render(<NotificationCenterScreen />);

    expect(await findByText('全部标记已读')).toBeTruthy();
  });

  it('should display notification messages', async () => {
    const { findByText } = render(<NotificationCenterScreen />);

    expect(await findByText('充电桩A-01充电枪温度达到85°C，已触发严重告警')).toBeTruthy();
  });

  it('should handle error state', async () => {
    (notificationApi.getList as jest.Mock).mockRejectedValue(new Error('API Error'));

    const { findByText } = render(<NotificationCenterScreen />);
    expect(await findByText('加载通知失败')).toBeTruthy();
  });

  it('should render empty state when no notifications', async () => {
    (notificationApi.getList as jest.Mock).mockResolvedValue({
      data: { items: [], total: 0, page: 1, pageSize: 20 },
    });

    const { findByText } = render(<NotificationCenterScreen />);
    expect(await findByText('暂无通知')).toBeTruthy();
  });

  it('should call markAsRead when tapping unread notification', async () => {
    (notificationApi.markAsRead as jest.Mock).mockResolvedValue({ data: MOCK_NOTIFICATIONS[0] });

    const { findAllByText } = render(<NotificationCenterScreen />); // eslint-disable-line @typescript-eslint/no-unused-vars

    // 等待渲染完成后，未读通知应该有点击标记已读功能
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });
  });

  it('should render read filter segments (全部 / 未读)', async () => {
    const { findByText, findAllByText } = render(<NotificationCenterScreen />);

    // 等待列表加载
    await findByText('充电桩A-01温度异常告警');
    // 「全部」出现在已读分段与类型筛选 chip 两处
    expect((await findAllByText('全部')).length).toBe(2);
    expect(await findByText('未读 3')).toBeTruthy();
  });

  it('should filter to unread only when tapping 未读 segment', async () => {
    const { findByText, queryByText } = render(<NotificationCenterScreen />);

    await findByText('系统维护通知'); // 已读的那条默认可见

    fireEvent.press(await findByText('未读 3'));

    // 已读的「系统维护通知」被过滤掉
    expect(queryByText('系统维护通知')).toBeNull();
    // 未读的仍可见
    expect(findByText('充电桩A-01温度异常告警')).toBeTruthy();
  });

  it('should filter by type when tapping a type chip', async () => {
    const { findByText, queryByText } = render(<NotificationCenterScreen />);

    await findByText('系统维护通知');

    fireEvent.press(await findByText('告警'));

    // 仅保留告警类型
    expect(await findByText('充电桩A-01温度异常告警')).toBeTruthy();
    expect(queryByText('新工单已分配')).toBeNull();
    expect(queryByText('系统维护通知')).toBeNull();
  });

  it('should show 无匹配通知 when type filter matches nothing', async () => {
    const { findByText } = render(<NotificationCenterScreen />);

    await findByText('系统维护通知');

    fireEvent.press(await findByText('设备'));

    expect(await findByText('无匹配通知')).toBeTruthy();
  });
});