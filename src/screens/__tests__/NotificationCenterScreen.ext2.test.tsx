import React from 'react';
import { FlatList } from 'react-native';
import { render, act } from '@testing-library/react-native';
import NotificationCenterScreen from '../NotificationCenterScreen';
import { notificationApi } from '../../services/api';

// F1228: coverage ext — NotificationCenterScreen L103 branch9 arm1 (handleLoadMore守卫false臂)
// 场景: 全部通知加载完毕后 onEndReached 再触发 → length<total 为 false → 不再发请求
// 手法: F1222 WorkOrderScreen onEndReached-after-all-loaded 同款 (mockClear + 计数锚定)

jest.mock('../../services/api', () => ({
  notificationApi: {
    getList: jest.fn(),
    getUnreadCount: jest.fn(),
    markAsRead: jest.fn(),
    markAllAsRead: jest.fn(),
  },
}));

jest.mock('../../components/LoadingSpinner', () => {
  const MockLoadingSpinner = (props: { text?: string }) => {
    const React = require('react');
    const { Text } = require('react-native');
    return React.createElement(Text, null, props.text || '加载中...');
  };
  return MockLoadingSpinner;
});

jest.mock('../../components/EmptyState', () => {
  const MockEmptyState = (props: {
    title?: string;
    message?: string;
    actionLabel?: string;
    onAction?: () => void;
  }) => {
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

const ALL_ITEMS = Array.from({ length: 4 }, (_, i) => ({
  id: i + 1,
  type: 'system' as const,
  title: `通知-${i + 1}`,
  message: `消息${i + 1}`,
  level: 'info' as const,
  isRead: true,
  createdAt: '2024-01-15T10:30:00Z',
}));

describe('NotificationCenterScreen L103 guard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (notificationApi.getList as jest.Mock).mockResolvedValue({
      data: { items: ALL_ITEMS, total: 4, page: 1, pageSize: 20 },
    });
    (notificationApi.getUnreadCount as jest.Mock).mockResolvedValue({ data: { count: 0 } });
  });

  it('should not fetch again when onEndReached fires after all loaded (L103 false arm)', async () => {
    const { findByText, UNSAFE_getByType } = render(<NotificationCenterScreen />);
    // 全部4条已加载(4/4), footer 显示已显示全部
    expect(await findByText('已显示全部 4 条通知')).toBeTruthy();

    // fail-fast: FlatList 实例在树中
    const flatList = UNSAFE_getByType(FlatList);
    expect(flatList).toBeDefined();

    // 锚定: mockClear 后 onEndReached 触发守卫false臂 → 零新请求
    (notificationApi.getList as jest.Mock).mockClear();
    await act(async () => {
      flatList.props.onEndReached();
      await new Promise((r) => setTimeout(r, 100));
    });

    expect(notificationApi.getList).not.toHaveBeenCalled();
  });
});
