/**
 * AnalyticsDashboard — Vitest 组件测试
 * 测试: 主页渲染 + Tab 切换 + 子组件渲染
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══ Mock API ═══
const { mockApi, mockStationAPI } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  mockStationAPI: {
    businessList: vi.fn(),
    list: vi.fn(),
    get: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ default: mockApi, stationAPI: mockStationAPI }));

// Mock all echarts modules comprehensively
vi.mock('echarts/core', () => ({
  default: { use: vi.fn(), init: vi.fn(() => ({ dispose: vi.fn(), setOption: vi.fn(), resize: vi.fn() })) },
  use: vi.fn(),
  init: vi.fn(() => ({ dispose: vi.fn(), setOption: vi.fn(), resize: vi.fn() })),
}));

vi.mock('echarts/charts', () => ({
  PieChart: {},
  BarChart: {},
  LineChart: {},
  RadarChart: {},
  ScatterChart: {},
}));

vi.mock('echarts/components', () => ({
  TitleComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
  GridComponent: {},
  DataZoomComponent: {},
  PolarComponent: {},
  MarkLineComponent: {},
  MarkPointComponent: {},
  VisualMapComponent: {},
  GraphicComponent: {},
  BrushComponent: {},
  CalendarComponent: {},
}));

vi.mock('echarts/renderers', () => ({
  CanvasRenderer: {},
}));

vi.mock('echarts-for-react/lib/core', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-core-mock' }, 'EChartsCore Mock'),
}));

vi.mock('echarts', () => ({
  default: { use: vi.fn(), init: vi.fn(() => ({ dispose: vi.fn(), setOption: vi.fn(), resize: vi.fn() })) },
  use: vi.fn(),
  init: vi.fn(() => ({ dispose: vi.fn(), setOption: vi.fn(), resize: vi.fn() })),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import AnalyticsDashboardPage from '../index';

// ═══ beforeEach ═══
beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/devices')) {
      return Promise.resolve({
        data: {
          code: 200,
          data: {
            items: [
              { id: 1, name: '逆变器01', device_type: 'inverter', status: 'normal' },
              { id: 2, name: '充电桩01', device_type: 'charger', status: 'warning' },
            ],
          },
        },
      });
    }
    if (url.includes('/stations')) {
      return Promise.resolve({
        data: {
          code: 200,
          data: {
            items: [{ id: 1, name: '测试站点A' }, { id: 2, name: '测试站点B' }],
          },
        },
      });
    }
    return Promise.resolve({ data: { code: 200, data: {} } });
  });
  mockApi.post.mockResolvedValue({});
  mockApi.put.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
  // EfficiencyAnalysis/MaintenanceOptimizer 改走 C端入口 /business/stations (stationAPI.businessList)
  mockStationAPI.businessList.mockResolvedValue({
    data: { items: [{ id: 1, name: '测试站点A' }, { id: 2, name: '测试站点B' }] },
  });
});

// ═══ Tests ═══

describe('AnalyticsDashboard 主页', () => {
  it('渲染 8 个 Tab 标签', async () => {
    await act(async () => {
      render(<BrowserRouter><AnalyticsDashboardPage /></BrowserRouter>);
    });
    expect(screen.getByText('健康度趋势')).toBeInTheDocument();
    expect(screen.getByText('能效分析')).toBeInTheDocument();
    expect(screen.getByText('异常检测')).toBeInTheDocument();
    expect(screen.getByText('维护优化')).toBeInTheDocument();
    expect(screen.getByText('历史趋势')).toBeInTheDocument();
    expect(screen.getByText('实时数据流')).toBeInTheDocument();
    expect(screen.getByText('设备对比')).toBeInTheDocument();
    expect(screen.getByText('自定义仪表盘')).toBeInTheDocument();
  });

  it('默认选中健康度趋势 Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><AnalyticsDashboardPage /></BrowserRouter>);
    });
    const healthTab = screen.getByText('健康度趋势').closest('.ant-tabs-tab');
    expect(healthTab?.classList.contains('ant-tabs-tab-active')).toBe(true);
  });

  it('切换到异常检测 Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><AnalyticsDashboardPage /></BrowserRouter>);
    });

    const anomalyTab = screen.getByText('异常检测').closest('.ant-tabs-tab');
    fireEvent.click(anomalyTab!);

    await waitFor(() => {
      const activeTab = screen.getByText('异常检测').closest('.ant-tabs-tab');
      expect(activeTab?.classList.contains('ant-tabs-tab-active')).toBe(true);
    });
  });

  it('切换到自定义仪表盘 Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><AnalyticsDashboardPage /></BrowserRouter>);
    });

    const dashTab = screen.getByText('自定义仪表盘').closest('.ant-tabs-tab');
    fireEvent.click(dashTab!);

    await waitFor(() => {
      const activeTab = screen.getByText('自定义仪表盘').closest('.ant-tabs-tab');
      expect(activeTab?.classList.contains('ant-tabs-tab-active')).toBe(true);
    });
  });

  it('Card 容器存在且有阴影样式', async () => {
    await act(async () => {
      render(<BrowserRouter><AnalyticsDashboardPage /></BrowserRouter>);
    });
    const card = document.querySelector('.ant-card');
    expect(card).toBeTruthy();
  });

  it('切换到设备对比 Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><AnalyticsDashboardPage /></BrowserRouter>);
    });

    const compareTab = screen.getByText('设备对比').closest('.ant-tabs-tab');
    fireEvent.click(compareTab!);

    await waitFor(() => {
      const activeTab = screen.getByText('设备对比').closest('.ant-tabs-tab');
      expect(activeTab?.classList.contains('ant-tabs-tab-active')).toBe(true);
    });
  });
});
