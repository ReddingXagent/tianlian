/**
 * HistoryTrend — 历史趋势接入真实数据测试
 *
 * 契约依据（后端实测）：
 * - telemetryAPI.history 不返回数据点（仅 {count,mode}）→ 必须降级
 * - 降级路径：telemetryAPI.stats 拿真实基线（温度/电压/功率）+ 确定性 sin 序列（无随机）
 * - 电流/电量后端 stats 无字段 → 确定性兜底常量
 *
 * 验收：
 * 1. 调用 telemetryAPI.stats 取真实基线
 * 2. 真实基线进入 ECharts series
 * 3. 两次渲染 series 数值恒等（确定性，非随机）
 * 4. 全程无 Math.random
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act, screen } from '@testing-library/react';
import React from 'react';

// ═══ 捕获 echarts.setOption 的 option ═══
const { setOptionSpy, initStub } = vi.hoisted(() => {
  const spy = vi.fn();
  return { setOptionSpy: spy, initStub: () => ({ dispose: vi.fn(), setOption: spy, resize: vi.fn() }) };
});
vi.mock('echarts', () => ({
  default: { use: vi.fn(), init: vi.fn(initStub) },
  use: vi.fn(),
  init: vi.fn(initStub),
}));
vi.mock('echarts/charts', () => ({ LineChart: {}, BarChart: {} }));
vi.mock('echarts/components', () => ({
  GridComponent: {}, TooltipComponent: {}, LegendComponent: {},
  TitleComponent: {}, DataZoomComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

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

import HistoryTrend from '../HistoryTrend';

const lastOption = () => setOptionSpy.mock.calls[setOptionSpy.mock.calls.length - 1]?.[0];

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/devices')) {
      return Promise.resolve({ data: { code: 200, data: { items: [{ id: 1, name: '逆变器01' }] } } });
    }
    return Promise.resolve({ data: { code: 200, data: {} } });
  });
  // history 不返回数据点（与后端实测一致）
  mockTelemetry.history.mockResolvedValue({ data: { code: 200, data: [] } });
});

describe('HistoryTrend — 真实数据接入', () => {
  it('history 无数据点时调用 telemetryAPI.stats 取真实基线', async () => {
    mockTelemetry.stats.mockResolvedValue({
      data: { code: 200, data: { stats: {
        grid: { avg_voltage_a: 230, avg_power: 5 },
        thermal: { avg_temp: 42 },
      } } },
    });
    await act(async () => { render(<HistoryTrend />); });
    await waitFor(() => expect(mockTelemetry.stats).toHaveBeenCalledWith(1));
  });

  it('真实温度基线进入 series（均值接近 stats.avg_temp）', async () => {
    mockTelemetry.stats.mockResolvedValue({
      data: { code: 200, data: { stats: { thermal: { avg_temp: 42 }, grid: { avg_voltage_a: 230, avg_power: 5 } } } },
    });
    await act(async () => { render(<HistoryTrend />); });
    await waitFor(() => expect(setOptionSpy).toHaveBeenCalled());
    const opt = lastOption();
    // 找到温度 series（name 含「温度」）
    const tempSeries = opt.series.find((s: any) => /温度/.test(s.name));
    expect(tempSeries).toBeTruthy();
    const avg = tempSeries.data.reduce((a: number, b: number) => a + b, 0) / tempSeries.data.length;
    // sin 微扰振幅 5 → 均值应紧贴基线 42
    expect(Math.abs(avg - 42)).toBeLessThan(1.5);
  });

  it('两次渲染 series 数值恒等（确定性兜底，非随机）', async () => {
    mockTelemetry.stats.mockResolvedValue({
      data: { code: 200, data: { stats: { thermal: { avg_temp: 42 }, grid: { avg_voltage_a: 230, avg_power: 5 } } } },
    });
    await act(async () => { render(<HistoryTrend />); });
    await waitFor(() => expect(setOptionSpy).toHaveBeenCalled());
    const first = JSON.stringify(lastOption().series.map((s: any) => s.data));

    setOptionSpy.mockClear();
    await act(async () => { render(<HistoryTrend />); });
    await waitFor(() => expect(setOptionSpy).toHaveBeenCalled());
    const second = JSON.stringify(lastOption().series.map((s: any) => s.data));
    expect(second).toBe(first);
  });

  it('stats 也失败时仍确定性兜底（两次渲染恒等，全部有限值）', async () => {
    mockTelemetry.stats.mockRejectedValue(new Error('boom'));
    await act(async () => { render(<HistoryTrend />); });
    await waitFor(() => expect(setOptionSpy).toHaveBeenCalled());
    const first = JSON.stringify(lastOption().series.map((s: any) => s.data));
    const allFinite = lastOption().series.every((s: any) => s.data.every((v: number) => Number.isFinite(v)));
    expect(allFinite).toBe(true);

    setOptionSpy.mockClear();
    await act(async () => { render(<HistoryTrend />); });
    await waitFor(() => expect(setOptionSpy).toHaveBeenCalled());
    expect(JSON.stringify(lastOption().series.map((s: any) => s.data))).toBe(first);
  });
});

// ═══ API失败/空列表错误态（卡afa42983：不塞假设备） ═══
describe('HistoryTrend — API失败错误态', () => {
  it('/devices 失败时渲染错误提示+重试，不塞假设备', async () => {
    mockApi.get.mockRejectedValue(new Error('network down'));
    await act(async () => { render(<HistoryTrend />); });
    await waitFor(() => {
      expect(screen.getByText('设备列表加载失败')).toBeInTheDocument();
      expect(screen.getByText(/network down/)).toBeInTheDocument();
      expect(screen.getByText('重试')).toBeInTheDocument();
    });
    expect(screen.queryByText(/光伏逆变器-001/)).not.toBeInTheDocument();
    expect(mockTelemetry.history).not.toHaveBeenCalled();
  });

  it('/devices 返回空列表时为空态，不塞假设备', async () => {
    mockApi.get.mockResolvedValue({ data: { code: 200, data: { items: [] } } });
    await act(async () => { render(<HistoryTrend />); });
    await waitFor(() => expect(mockApi.get).toHaveBeenCalledWith('/devices'));
    expect(screen.queryByText(/光伏逆变器-001/)).not.toBeInTheDocument();
    expect(screen.queryByText(/储能PCS-001/)).not.toBeInTheDocument();
    expect(mockTelemetry.history).not.toHaveBeenCalled();
  });
});
