/**
 * 数据报表页面 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  default: mockApi,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

// Mock ECharts
vi.mock('echarts-for-react/lib/core', () => ({
  default: ({ option }: any) => <div data-testid="echart" data-option={JSON.stringify(option ? option.series : [])} />,
}));

vi.mock('echarts/core', () => ({
  default: { use: vi.fn() },
  use: vi.fn(),
}));

vi.mock('echarts/charts', () => ({
  LineChart: {},
  BarChart: {},
  PieChart: {},
}));

vi.mock('echarts/components', () => ({
  GridComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
  TitleComponent: {},
}));

vi.mock('echarts/renderers', () => ({
  CanvasRenderer: {},
}));

import ReportsPage from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockStatsData = {
  stations: { total: 16 },
  devices: { total: 68, online_rate: 87.5 },
  alarms: { active: 12 },
};

const mockAlarmTrend = {
  trend: [
    { date: '05-15', critical: 2, warning: 5, info: 8 },
    { date: '05-16', critical: 1, warning: 3, info: 6 },
  ],
};

const mockWorkorderStats = {
  total: 55,
  by_status: { pending: 8, processing: 5, completed: 42 },
};

const mockDeviceHealth = {
  devices: [
    { name: '正常', value: 52 },
    { name: '警告', value: 10 },
    { name: '故障', value: 6 },
  ],
};

const mockStationRank = {
  rank: [
    { name: '北京朝阳站', score: 95 },
    { name: '深圳南山站', score: 93 },
  ],
};

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  // 默认全部成功返回
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/stats/overview')) return Promise.resolve({ data: mockStatsData });
    if (url.includes('/stats/alarms/trend')) return Promise.resolve({ data: mockAlarmTrend });
    if (url.includes('/stats/workorders/summary')) return Promise.resolve({ data: mockWorkorderStats });
    if (url.includes('/stats/devices/health')) return Promise.resolve({ data: mockDeviceHealth });
    if (url.includes('/stats/stations/rank')) return Promise.resolve({ data: mockStationRank });
    return Promise.resolve({ data: {} });
  });
});

describe('数据报表 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><ReportsPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('渲染统计卡片（站点总数、设备总数等）', async () => {
    await act(async () => {
      render(<BrowserRouter><ReportsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      const titles = screen.getAllByText('站点总数');
      expect(titles.length).toBeGreaterThan(0);
      expect(screen.getAllByText('设备总数').length).toBeGreaterThan(0);
      expect(screen.getAllByText('设备在线率').length).toBeGreaterThan(0);
      expect(screen.getAllByText('活动告警').length).toBeGreaterThan(0);
    });
  });

  it('渲染图表区域', async () => {
    await act(async () => {
      render(<BrowserRouter><ReportsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('告警趋势')).toBeInTheDocument();
      expect(screen.getByText('工单状态分布')).toBeInTheDocument();
      expect(screen.getByText('设备健康度分布')).toBeInTheDocument();
      expect(screen.getByText('站点评分排行')).toBeInTheDocument();
    });
  });
});

describe('数据报表 — 数据展示', () => {
  it('API 被调用获取各项统计数据', async () => {
    await act(async () => {
      render(<BrowserRouter><ReportsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/stats/overview');
      expect(mockApi.get).toHaveBeenCalledWith('/stats/alarms/trend');
      expect(mockApi.get).toHaveBeenCalledWith('/stats/workorders/summary');
      expect(mockApi.get).toHaveBeenCalledWith('/stats/devices/health');
      expect(mockApi.get).toHaveBeenCalledWith('/stats/stations/rank');
    });
  });

  it('API 失败时使用降级 mock 数据', async () => {
    mockApi.get.mockRejectedValue(new Error('network error'));

    await act(async () => {
      const { container } = render(<BrowserRouter><ReportsPage /></BrowserRouter>);
      expect(container).toBeTruthy();
    });

    // 即使API全失败，页面也应渲染统计卡片标题
    await waitFor(() => {
      expect(screen.getAllByText('站点总数').length).toBeGreaterThan(0);
    });
  });
});

describe('数据报表 — 交互', () => {
  it('渲染导出工具栏', async () => {
    await act(async () => {
      render(<BrowserRouter><ReportsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getAllByText('报表导出').length).toBeGreaterThan(0);
      expect(screen.getAllByText('导出').length).toBeGreaterThan(0);
    });
  });

  it('渲染 ECharts 图表组件', async () => {
    await act(async () => {
      render(<BrowserRouter><ReportsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      const charts = screen.getAllByTestId('echart');
      expect(charts.length).toBeGreaterThan(0);
    });
  });
});
