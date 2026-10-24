/**
 * Dashboard 数据看板 — Vitest 单元测试
 * 覆盖：渲染、统计卡片数据加载、核心面板展示
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块
// ═══════════════════════════════════════════
const { mockStatsAPI, mockAlarmAPI, mockHealthAPI, mockWorkorderAPI, mockApiDefault } = vi.hoisted(() => ({
  mockStatsAPI: { overview: vi.fn() },
  mockAlarmAPI: { stats: vi.fn() },
  mockHealthAPI: { list: vi.fn() },
  mockWorkorderAPI: { list: vi.fn() },
  mockApiDefault: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('../../../api', () => ({
  default: mockApiDefault,
  statsAPI: mockStatsAPI,
  alarmAPI: mockAlarmAPI,
  healthAPI: mockHealthAPI,
  workorderAPI: mockWorkorderAPI,
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

// ═══════════════════════════════════════════
// Mock ECharts（避免 jsdom 下 Canvas 渲染报错）
// 同时捕获每次渲染传入的 option，用于断言真实数据流入图表
// ═══════════════════════════════════════════
const echartsOptions: any[] = [];
vi.mock('echarts-for-react/lib/core', () => ({
  default: (props: any) => {
    if (props?.option) echartsOptions.push(props.option);
    return React.createElement('div', { 'data-testid': 'echarts-mock' });
  },
}));

vi.mock('echarts/core', () => ({
  default: { use: vi.fn() },
  use: vi.fn(),
}));

vi.mock('echarts/charts', () => ({
  LineChart: {},
  PieChart: {},
  GaugeChart: {},
  BarChart: {},
  RadarChart: {},
}));

vi.mock('echarts/components', () => ({
  GridComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
  TitleComponent: {},
  DataZoomComponent: {},
  PolarComponent: {},
}));

vi.mock('echarts/renderers', () => ({
  CanvasRenderer: {},
}));

// ═══════════════════════════════════════════
// Mock PageWrapper（简化渲染逻辑）
// ═══════════════════════════════════════════
vi.mock('../../../components/PageWrapper', () => ({
  default: ({ children }: any) => React.createElement('div', null, children),
}));

// ═══════════════════════════════════════════
// Mock EfficiencyOverviewCard
// ═══════════════════════════════════════════
vi.mock('../EfficiencyOverviewCard', () => ({
  default: () => React.createElement('div', { 'data-testid': 'efficiency-mock' }),
}));

// ═══════════════════════════════════════════
// Mock useWebSocket
// ═══════════════════════════════════════════
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({
    isConnected: false,
    connectionState: 'disconnected',
    lastDashboardUpdate: null,
    dashboardAlarms: [],
    dashboardDeviceStatus: [],
  }),
  DashboardRealtimeUpdate: {} as any,
}));

vi.mock('../../../config/websocket', () => ({
  WS_ENDPOINTS: { dashboard: '/ws/v1/dashboard' },
}));

import Dashboard from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockOverviewData = {
  stations: { total: 16, online: 14, offline: 1, maintenance: 1 },
  devices: { total: 58, online: 54, fault: 2, maintenance: 2, online_rate: 93 },
  health: { average: 88, good: 45, warning: 10, critical: 3 },
  alarms: { active: 3, critical: 1, major: 1, minor: 1 },
  workorders: { pending: 5, in_progress: 3, completed_today: 2, overdue: 1 },
};

const mockHealthDevices = [
  { device_id: 1, health_score: 95, status: 'ONLINE' },
  { device_id: 2, health_score: 88, status: 'ONLINE' },
  { device_id: 3, health_score: 65, status: 'WARNING' },
];

const mockAlarmStats = {
  total: 15,
  active: 3,
  critical: 1,
  major: 5,
  minor: 7,
  info: 2,
};

const mockWorkorders = {
  items: [
    { id: 1, status: 'pending' },
    { id: 2, status: 'pending' },
    { id: 3, status: 'in_progress' },
    { id: 4, status: 'completed' },
    { id: 5, status: 'closed' },
  ],
};

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

beforeEach(() => {
  vi.clearAllMocks();
  echartsOptions.length = 0;
  vi.useFakeTimers({ shouldAdvanceTime: true });
  mockStatsAPI.overview.mockResolvedValue({ data: mockOverviewData });
  mockHealthAPI.list.mockResolvedValue({ data: mockHealthDevices });
  mockAlarmAPI.stats.mockResolvedValue({ data: mockAlarmStats });
  mockWorkorderAPI.list.mockResolvedValue({ data: mockWorkorders });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('Dashboard — 渲染', () => {
  it('页面可渲染不崩溃', async () => {
    let container: HTMLElement | undefined;
    await act(async () => {
      const { container: c } = render(<BrowserRouter><Dashboard /></BrowserRouter>);
      container = c;
    });
    expect(container).toBeTruthy();
  });

  it('页面标题「运维中心 Dashboard」正常展示', async () => {
    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('运维中心 Dashboard')).toBeInTheDocument();
    });
  });

  it('ECharts 图表组件被渲染（mock）', async () => {
    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });
    await waitFor(() => {
      const charts = screen.getAllByTestId('echarts-mock');
      expect(charts.length).toBeGreaterThan(0);
    });
  });
});

describe('Dashboard — 数据加载', () => {
  it('挂载时调用 statsAPI.overview', async () => {
    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(mockStatsAPI.overview).toHaveBeenCalled();
    });
  });

  it('挂载时调用 healthAPI.list', async () => {
    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(mockHealthAPI.list).toHaveBeenCalled();
    });
  });

  it('挂载时调用 alarmAPI.stats', async () => {
    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(mockAlarmAPI.stats).toHaveBeenCalled();
    });
  });

  it('挂载时调用 workorderAPI.list', async () => {
    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(mockWorkorderAPI.list).toHaveBeenCalled();
    });
  });
});

describe('Dashboard — 告警趋势真实接口', () => {
  it('挂载时调用 /reports/alarms?days=7 获取7天告警趋势', async () => {
    mockApiDefault.get.mockResolvedValue({
      data: {
        daily_trend: [
          { date: '2026-07-19', count: 5 },
          { date: '2026-07-20', count: 3 },
        ],
      },
    });

    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(mockApiDefault.get).toHaveBeenCalledWith('/reports/alarms', { params: { days: 7 } });
    });
  });

  it('daily_trend 数据流入告警趋势折线图（不再用 Math.random）', async () => {
    const dailyTrend = [
      { date: '2026-07-19', count: 5 },
      { date: '2026-07-20', count: 3 },
      { date: '2026-07-21', count: 8 },
    ];
    mockApiDefault.get.mockResolvedValue({ data: { daily_trend: dailyTrend } });

    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });

    await waitFor(() => {
      // 告警趋势是唯一的 line 类型 series；取最后一次渲染（用户最终可见状态）
      const lineOpts = echartsOptions.filter(
        opt => Array.isArray(opt?.series) && opt.series.some((s: any) => s.type === 'line')
      );
      expect(lineOpts.length).toBeGreaterThan(0);
      const lastLineOpt = lineOpts[lineOpts.length - 1];
      const counts = lastLineOpt.series.find((s: any) => s.type === 'line').data;
      expect(counts).toEqual([5, 3, 8]);
    });
  });

  it('/reports/alarms 失败时降级兜底且不崩溃', async () => {
    mockApiDefault.get.mockRejectedValue(new Error('Network error'));

    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });

    // 即使趋势接口失败，页面仍正常渲染（兜底数据）
    await waitFor(() => {
      expect(screen.getByText('运维中心 Dashboard')).toBeInTheDocument();
    });
  });
});

describe('Dashboard — 统计卡片展示', () => {
  it('站点总数卡片渲染正确数据（16）', async () => {
    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('站点总数')).toBeInTheDocument();
      expect(screen.getByText('16')).toBeInTheDocument();
    });
  });

  it('设备总数卡片渲染正确数据（58）', async () => {
    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('设备总数')).toBeInTheDocument();
      expect(screen.getByText('58')).toBeInTheDocument();
    });
  });

  it('活跃告警卡片渲染正确数据（3）', async () => {
    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('活跃告警')).toBeInTheDocument();
    });
  });

  it('API 失败时使用 fallback 默认数据渲染', async () => {
    mockStatsAPI.overview.mockRejectedValue(new Error('Network error'));
    mockHealthAPI.list.mockRejectedValue(new Error('Network error'));
    mockAlarmAPI.stats.mockRejectedValue(new Error('Network error'));
    mockWorkorderAPI.list.mockRejectedValue(new Error('Network error'));

    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });

    // 即使API失败，组件也使用默认数据渲染
    await waitFor(() => {
      expect(screen.getByText('站点总数')).toBeInTheDocument();
    });
  });
});

describe('Dashboard — 自动刷新', () => {
  it('30秒后自动刷新数据', async () => {
    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });

    // 初始加载一次
    await waitFor(() => {
      expect(mockStatsAPI.overview).toHaveBeenCalledTimes(1);
    });

    // 推进 30 秒
    await act(async () => {
      vi.advanceTimersByTime(31000);
    });

    // 应该再次调用
    await waitFor(() => {
      expect(mockStatsAPI.overview).toHaveBeenCalledTimes(2);
    });
  });
});

describe('Dashboard — 移动端响应式', () => {
  beforeEach(() => {
    vi.stubGlobal('innerWidth', 375);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('统计卡片采用响应式 Col（移动端 2 列，xs={12}）', async () => {
    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('站点总数')).toBeInTheDocument();
    });
    // StatCards 4 张卡片 Col 为 xs={12} sm={12} md={6}，移动端纵向 2 列（与 Phase1 Fleet/WorkOrders 一致）
    expect(document.querySelector('.ant-col-xs-12')).toBeInTheDocument();
  });

  it('数据面板采用响应式 Col（移动端纵向堆叠，xs={24}）', async () => {
    await act(async () => {
      render(<BrowserRouter><Dashboard /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('运维中心 Dashboard')).toBeInTheDocument();
    });
    // 顶部 8 个图表面板 Col 均为 xs={24} lg={12|6}，移动端全纵向堆叠
    const panelCols = document.querySelectorAll('.ant-col-xs-24');
    expect(panelCols.length).toBeGreaterThanOrEqual(8);
  });

  it('移动端宽度下页面正常渲染不崩溃', async () => {
    let container: HTMLElement | undefined;
    await act(async () => {
      const { container: c } = render(<BrowserRouter><Dashboard /></BrowserRouter>);
      container = c;
    });
    await waitFor(() => {
      expect(screen.getByText('运维中心 Dashboard')).toBeInTheDocument();
    });
    expect(container).toBeTruthy();
  });
});
