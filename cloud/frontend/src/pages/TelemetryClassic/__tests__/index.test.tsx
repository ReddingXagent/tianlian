/**
 * TelemetryClassic 页面主入口（index.tsx）— Vitest 渲染冒烟测试
 *
 * 覆盖：
 * - 页面渲染不崩、设备选择、自动刷新切换、详情弹窗（冒烟口径）
 * - 复用 telemetry.test.tsx 的 echarts/api mock 风格
 *
 * 注意：卡 f46cd59f 只测 index.tsx 本体，不重复 telemetry.test.tsx 已覆盖的深度断言。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// ECharts mock（组件内 echarts.use + ReactEChartsCore）
// ═══════════════════════════════════════════
vi.mock('echarts/core', () => ({ use: vi.fn(), init: vi.fn(() => ({ setOption: vi.fn(), dispose: vi.fn() })) }));
vi.mock('echarts/charts', () => ({ LineChart: {} }));
vi.mock('echarts/components', () => ({
  GridComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
  TitleComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

const { echartsOptions } = vi.hoisted(() => ({ echartsOptions: [] as any[] }));
vi.mock('echarts-for-react/lib/core', () => ({
  default: (props: any) => {
    echartsOptions.push(props.option);
    return React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock');
  },
}));

// ═══════════════════════════════════════════
// Mock API — useTelemetryData 依赖 api.get('/devices') + telemetryAPI
// ═══════════════════════════════════════════
const { mockApi, mockTelemetry } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
  mockTelemetry: {
    latest: vi.fn(),
    history: vi.fn(),
    stats: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  default: mockApi,
  telemetryAPI: mockTelemetry,
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import TelemetryPage from '../index';

const renderPage = () => render(<BrowserRouter><TelemetryPage /></BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  echartsOptions.length = 0;
  mockApi.get.mockResolvedValue({
    code: 200,
    data: { items: [{ id: 3, name: '储能电池-03', type: 'battery' }] },
  });
  mockTelemetry.latest.mockResolvedValue({
    data: { data: { device_type: 'battery', grid_power_total: 12.5, battery_soc: 66 } },
  });
  mockTelemetry.history.mockRejectedValue(new Error('not deployed'));
  mockTelemetry.stats.mockResolvedValue({ data: { data: {} } });
});

describe('TelemetryClassic index — 渲染冒烟', () => {
  it('挂载加载设备列表并渲染页面骨架', async () => {
    renderPage();

    expect(await screen.findByText('遥测数据监控')).toBeInTheDocument();
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/devices');
    });
    expect(screen.getByText('自动刷新')).toBeInTheDocument();
    expect(screen.getByText('刷新')).toBeInTheDocument();
    expect(screen.getByText('详情')).toBeInTheDocument();
    // loading 结束后趋势区才渲染，异步等待
    expect(await screen.findByText('趋势分析', {}, { timeout: 5000 })).toBeInTheDocument();
  });

  it('设备列表加载失败显示错误 Alert 不崩溃', async () => {
    mockApi.get.mockRejectedValue({ response: { data: { message: '服务不可用' } } });

    renderPage();

    expect(await screen.findByText('设备列表加载失败')).toBeInTheDocument();
    expect(screen.getByText('遥测数据监控')).toBeInTheDocument();
  });

  it('点击自动刷新按钮切换为停止刷新（交互状态翻转）', async () => {
    renderPage();
    await screen.findByText('遥测数据监控');

    await act(async () => {
      fireEvent.click(screen.getByText('自动刷新'));
    });
    expect(await screen.findByText('停止刷新')).toBeInTheDocument();

    // 再点一次回到自动刷新
    await act(async () => {
      fireEvent.click(screen.getByText('停止刷新'));
    });
    expect(screen.getByText('自动刷新')).toBeInTheDocument();
  });

  it('点击详情按钮打开遥测数据详情弹窗', async () => {
    renderPage();
    await screen.findByText('遥测数据监控');

    await act(async () => {
      fireEvent.click(screen.getByText('详情'));
    });

    await waitFor(() => {
      expect(screen.getByText('遥测数据详情')).toBeInTheDocument();
      expect(screen.getByText('当前数据')).toBeInTheDocument();
      expect(screen.getByText('协议信息')).toBeInTheDocument();
    });
  });
});
