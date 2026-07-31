/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { render, fireEvent, act } from '@testing-library/react-native';
import { Share, Animated } from 'react-native';
import RevenueScreen from '../RevenueScreen';
import { revenueApi } from '../../services/api';

jest.mock('react-native-chart-kit', () => {
  const React = require('react');
  const { Text } = require('react-native');
  return {
    LineChart: () => React.createElement(Text, { testID: 'line-chart' }, 'chart'),
  };
});

jest.mock('../../services/api', () => ({
  revenueApi: {
    getRecords: jest.fn(),
    getSummary: jest.fn(),
  },
}));

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

const MOCK_RECORDS = [
  { date: '2024-01-01', amount: 123.45, orderCount: 10 },
  { date: '2024-01-02', amount: 200, orderCount: 15 },
];

const MOCK_SUMMARY = { today: 100, week: 700, month: 3000, total: 50000 };

describe('RevenueScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Share, 'share').mockResolvedValue({ action: 'shared.action' } as any);
    // 让图表入场动画同步完成，避免 600ms 定时器泄漏到其它测试套件
    jest.spyOn(Animated, 'timing').mockReturnValue({ start: jest.fn() } as any);
    (revenueApi.getRecords as jest.Mock).mockResolvedValue({ data: MOCK_RECORDS });
    (revenueApi.getSummary as jest.Mock).mockResolvedValue({ data: MOCK_SUMMARY });
  });

  it('should render loading state initially', () => {
    (revenueApi.getRecords as jest.Mock).mockImplementation(() => new Promise(() => {}));
    (revenueApi.getSummary as jest.Mock).mockImplementation(() => new Promise(() => {}));

    const { getByText } = render(<RevenueScreen />);
    expect(getByText('加载营收数据...')).toBeTruthy();
  });

  it('should render summary cards and records after loading', async () => {
    const { findByText } = render(<RevenueScreen />);

    expect(await findByText('¥100.00')).toBeTruthy(); // 今日
    expect(await findByText('¥50000.00')).toBeTruthy(); // 累计
    expect(await findByText('2024-01-01')).toBeTruthy();
    expect(await findByText('¥123.45')).toBeTruthy();
    expect(await findByText('10笔')).toBeTruthy();
  });

  it('should render period switch buttons', async () => {
    const { findByText } = render(<RevenueScreen />);

    expect(await findByText('日')).toBeTruthy();
    expect(await findByText('周')).toBeTruthy();
    expect(await findByText('月')).toBeTruthy();
  });

  it('should refetch records with new period type when switching', async () => {
    const { findByText, getByText } = render(<RevenueScreen />);

    await findByText('2024-01-01');

    // 默认周期为 week
    expect(revenueApi.getRecords).toHaveBeenCalledWith({ type: 'week' });

    fireEvent.press(getByText('日'));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(revenueApi.getRecords).toHaveBeenCalledWith({ type: 'day' });
  });

  it('should render export button and trigger Share with CSV content', async () => {
    const { findByText } = render(<RevenueScreen />);

    const exportBtn = await findByText(/导出CSV/);
    fireEvent.press(exportBtn);

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(Share.share).toHaveBeenCalledTimes(1);
    const callArg = (Share.share as jest.Mock).mock.calls[0][0];
    expect(callArg.message).toContain('天链V3 营收统计');
    expect(callArg.message).toContain('123.45');
    expect(callArg.message).toContain('合计');
  });

  it('should render empty state when no records', async () => {
    (revenueApi.getRecords as jest.Mock).mockResolvedValue({ data: [] });

    const { findByText } = render(<RevenueScreen />);
    expect(await findByText('暂无营收明细')).toBeTruthy();
  });
});
