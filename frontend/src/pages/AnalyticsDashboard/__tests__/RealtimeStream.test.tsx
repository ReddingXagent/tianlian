/**
 * RealtimeStream — 实时数据流接入真实数据测试
 *
 * 契约依据（后端实测）：
 * - WS dashboard 频道只推 alarm/device_status/workorder/health，无温度/电压/电流/功率数值流
 * - telemetryAPI.latest 只有 grid_power_total/battery_soc/charger_power（无温度/电压/电流）
 * - telemetryAPI.stats 有温度/电压/功率均值（真实基线）；电流后端无 → 确定性兜底
 *
 * 验收：
 * 1. 调用 telemetryAPI.stats 取基线 + telemetryAPI.latest 轮询最新值
 * 2. WS lastMessage 含遥测数值时更新当前值
 * 3. 数据点全部有限、两次渲染（固定时间）series 数值恒等（确定性，非随机）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor, act, screen } from '@testing-library/react';
import React from 'react';

// ═══ 捕获 ECharts option ═══
const { echartsOptions } = vi.hoisted(() => ({ echartsOptions: [] as any[] }));
vi.mock('echarts/core', () => ({
  default: { use: vi.fn(), graphic: { LinearGradient: vi.fn() } },
  use: vi.fn(),
  graphic: { LinearGradient: vi.fn() },
}));
vi.mock('echarts/charts', () => ({ LineChart: {}, BarChart: {} }));
vi.mock('echarts/components', () => ({
  GridComponent: {}, TooltipComponent: {}, LegendComponent: {},
  TitleComponent: {}, DataZoomComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));
vi.mock('echarts-for-react/lib/core', () => ({
  default: (props: any) => {
    echartsOptions.push(props.option);
    return React.createElement('div', { 'data-testid': 'echarts-mock' });
  },
}));

// ═══ Mock useWebSocket ═══
const { wsHook } = vi.hoisted(() => ({
  wsHook: { isConnected: false, lastMessage: null as any },
}));
vi.mock('../../../hooks/useWebSocket', () => ({ useWebSocket: () => wsHook }));

// ═══ Mock API ═══
const { mockApi, mockTelemetry } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  mockTelemetry: { stats: vi.fn(), history: vi.fn(), latest: vi.fn() },
}));
vi.mock('../../../api', () => ({ default: mockApi, telemetryAPI: mockTelemetry }));

vi.mock('antd', async (importOriginal) => {
  const actual: any = await importOriginal();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import RealtimeStream from '../RealtimeStream';

const lastOption = () => echartsOptions[echartsOptions.length - 1];

beforeEach(() => {
  vi.clearAllMocks();
  echartsOptions.length = 0;
  wsHook.isConnected = false;
  wsHook.lastMessage = null;
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-07-25T10:00:00Z'));
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/devices')) {
      return Promise.resolve({ data: { code: 200, data: { items: [{ id: 1, name: '逆变器01' }] } } });
    }
    return Promise.resolve({ data: { code: 200, data: {} } });
  });
  mockTelemetry.stats.mockResolvedValue({
    data: { code: 200, data: { stats: { thermal: { avg_temp: 42 }, grid: { avg_voltage_a: 230, avg_power: 5 } } } },
  });
  mockTelemetry.latest.mockResolvedValue({
    data: { code: 200, data: { timestamp: '2026-07-25T10:00:00', grid_power_total: 6.2 } },
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('RealtimeStream — 真实数据接入', () => {
  it('调用 telemetryAPI.stats 取基线', async () => {
    await act(async () => {
      render(<RealtimeStream />);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mockTelemetry.stats).toHaveBeenCalledWith(1);
  });

  it('轮询 telemetryAPI.latest 取最新值', async () => {
    await act(async () => {
      render(<RealtimeStream />);
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(mockTelemetry.latest).toHaveBeenCalledWith(1);
  });

  it('series 数据点全部为有限值（无 NaN/Infinity）', async () => {
    await act(async () => {
      render(<RealtimeStream />);
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(echartsOptions.length).toBeGreaterThan(0);
    const opt = lastOption();
    const allFinite = opt.series.every((s: any) => s.data.every((v: number) => Number.isFinite(v)));
    expect(allFinite).toBe(true);
  });

  it('相同时间起点两次渲染 series 数值恒等（确定性，非随机）', async () => {
    const renderOnce = async () => {
      echartsOptions.length = 0;
      vi.setSystemTime(new Date('2026-07-25T10:00:00Z'));
      mockTelemetry.stats.mockClear();
      mockTelemetry.latest.mockClear();
      const view = render(<RealtimeStream />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
        await vi.advanceTimersByTimeAsync(3000);
      });
      const snapshot = JSON.stringify(lastOption()?.series?.map((s: any) => s.data));
      view.unmount();
      return snapshot;
    };
    const a = await renderOnce();
    const b = await renderOnce();
    expect(b).toBe(a);
  });
});

// ═══ API失败错误态（卡afa42983：不回退mock设备） ═══
describe('RealtimeStream — API失败错误态', () => {
  it('/devices 失败时渲染错误提示+重试，不塞假设备', async () => {
    mockApi.get.mockRejectedValue(new Error('network down'));
    await act(async () => {
      render(<RealtimeStream />);
      await vi.advanceTimersByTimeAsync(100);
    });
    // fake timers 下不用 waitFor，直接断言（错误态已在 mount 后渲染）
    expect(screen.getByText('设备列表加载失败')).toBeInTheDocument();
    expect(screen.getByText(/network down/)).toBeInTheDocument();
    expect(screen.getByText('重试')).toBeInTheDocument();
    expect(screen.queryByText(/光伏逆变器-001/)).not.toBeInTheDocument();
    // 无设备选中时不轮询遥测
    expect(mockTelemetry.stats).not.toHaveBeenCalled();
  });
});
