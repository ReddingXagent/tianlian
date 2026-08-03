/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { render, act, fireEvent } from '@testing-library/react-native';
import ChargerTrendChart from '../ChargerTrendChart';
import { chargerApi } from '../../services/api';

// Mock chart-kit 避免 SVG 渲染
jest.mock('react-native-chart-kit', () => {
  const React = require('react');
  const { Text } = require('react-native');
  return {
    // 调用 chart 回调以覆盖 datasets.color / chartConfig.color / labelColor / hexToRgb 路径
    LineChart: (props: any) => {
      const datasetColor = props.data.datasets[0].color();
      const cfgColor = props.chartConfig.color(0.5);
      const cfgColorDefault = props.chartConfig.color(); // 默认参数分支(opacity=1)
      const labelColor = props.chartConfig.labelColor();
      const labels: string[] = props.data.labels;
      const emptyLabels = labels.filter((l) => l === '').length;
      return React.createElement(
        Text,
        { testID: 'line-chart' },
        `chart:${datasetColor}:${cfgColor}:${cfgColorDefault}:${labelColor}:labels=${labels.length},empty=${emptyLabels}`
      );
    },
  };
});

jest.mock('../../services/api', () => ({
  chargerApi: {
    getTrend: jest.fn(),
  },
}));

jest.mock('../LoadingSpinner', () => {
  const MockLoadingSpinner = (props: any) => {
    const React = require('react');
    const { Text } = require('react-native');
    return React.createElement(Text, null, props.text || '加载中...');
  };
  return MockLoadingSpinner;
});

jest.mock('../EmptyState', () => {
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

const MOCK_TREND = {
  deviceId: 101,
  points: [
    { timestamp: '2024-01-15T10:00:00Z', power: 10, voltage: 380, current: 30, soc: 20 },
    { timestamp: '2024-01-15T10:05:00Z', power: 30, voltage: 381, current: 80, soc: 45 },
    { timestamp: '2024-01-15T10:10:00Z', power: 45.6, voltage: 380, current: 120, soc: 60 },
  ],
};

describe('ChargerTrendChart', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (chargerApi.getTrend as jest.Mock).mockResolvedValue({ data: MOCK_TREND });
  });

  it('should fetch trend for the given deviceId', async () => {
    render(<ChargerTrendChart deviceId={101} deviceName="充电桩A-01" />);

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(chargerApi.getTrend).toHaveBeenCalledWith(101);
  });

  it('should render loading state initially', () => {
    (chargerApi.getTrend as jest.Mock).mockImplementation(() => new Promise(() => {}));

    const { getByText } = render(<ChargerTrendChart deviceId={101} />);
    expect(getByText('加载趋势数据...')).toBeTruthy();
  });

  it('should render four metric tabs after loading', async () => {
    const { findByText } = render(<ChargerTrendChart deviceId={101} />);

    expect(await findByText('功率')).toBeTruthy();
    expect(await findByText('电压')).toBeTruthy();
    expect(await findByText('电流')).toBeTruthy();
    expect(await findByText('SOC')).toBeTruthy();
  });

  it('should show current power value by default', async () => {
    const { findByText } = render(<ChargerTrendChart deviceId={101} />);

    // 最新功率 45.6
    expect(await findByText(/45\.6/)).toBeTruthy();
  });

  it('should switch to SOC metric and show percentage value', async () => {
    const { findByText, getByText } = render(<ChargerTrendChart deviceId={101} />);

    await findByText('功率');
    fireEvent.press(getByText('SOC'));

    // 切换后汇总标签变为「当前SOC」，最新值 60（值文本含单位子节点，用正则匹配）
    expect(getByText('当前SOC')).toBeTruthy();
    expect(getByText(/^60/)).toBeTruthy();
  });

  it('should show empty state when no points', async () => {
    (chargerApi.getTrend as jest.Mock).mockResolvedValue({ data: { deviceId: 101, points: [] } });

    const { findByText } = render(<ChargerTrendChart deviceId={101} />);
    expect(await findByText('暂无趋势数据')).toBeTruthy();
  });

  it('should show error state on failure', async () => {
    (chargerApi.getTrend as jest.Mock).mockRejectedValue(new Error('API Error'));

    const { findByText } = render(<ChargerTrendChart deviceId={101} />);
    expect(await findByText('加载失败')).toBeTruthy();
  });

  it('should render chart with correct metric colors via chart callbacks', async () => {
    const { findByTestId } = render(<ChargerTrendChart deviceId={101} />);

    // 功率主色 #1a73e8 → rgb(26,115,232)
    const chart = await findByTestId('line-chart');
    const text = Array.isArray(chart.props.children)
      ? chart.props.children.join('')
      : String(chart.props.children);
    expect(text).toContain('26,115,232');
  });

  it('should thin labels when more than 6 points', async () => {
    // 12 个点 → step=2, 半数标签被置空(buildLabels 抽稀分支 + Math.max 右侧)
    const manyPoints = Array.from({ length: 12 }, (_, i) => ({
      timestamp: `2024-01-15T10:${String(i * 5).padStart(2, '0')}:00Z`,
      power: i,
      voltage: 380,
      current: 30,
      soc: 20,
    }));
    (chargerApi.getTrend as jest.Mock).mockResolvedValue({
      data: { deviceId: 101, points: manyPoints },
    });

    const { findByTestId } = render(<ChargerTrendChart deviceId={101} />);
    const chart = await findByTestId('line-chart');
    const text = Array.isArray(chart.props.children)
      ? chart.props.children.join('')
      : String(chart.props.children);
    expect(text).toContain('labels=12,empty=6');
  });

  it('should fall back to empty label when timestamp formatting fails', async () => {
    const spy = jest
      .spyOn(Date.prototype, 'toLocaleTimeString')
      .mockImplementation(() => {
        throw new Error('format failed');
      });

    try {
      const { findByTestId } = render(<ChargerTrendChart deviceId={101} />);
      // formatClock catch 分支: 标签为空但图表仍渲染
      expect(await findByTestId('line-chart')).toBeTruthy();
    } finally {
      spy.mockRestore();
    }
  });
});
