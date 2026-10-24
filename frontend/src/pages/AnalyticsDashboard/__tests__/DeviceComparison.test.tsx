/**
 * DeviceComparison — 多设备对比接入真实数据测试
 *
 * 契约依据（参考 Monitor/index.tsx + 后端实测）：
 * - efficiencyAPI.deviceEfficiency(id) → {utilization:{current}} 用作健康度
 * - telemetryAPI.stats(id) → 温度/电压/功率均值；电流后端无 → 确定性降级
 * - 设备状态来自 /devices 列表的 status（非随机）
 * - /analytics/compare 后端无可用字段 → 直接用 efficiency+stats
 *
 * 验收：
 * 1. 对比时调用 efficiencyAPI.deviceEfficiency + telemetryAPI.stats（每设备）
 * 2. 真实 utilization.current 进入雷达图健康度
 * 3. 状态来自设备列表（非 Math.random）
 * 4. 两次对比雷达数据恒等（确定性，非随机）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';

// ═══ 捕获 ECharts option ═══
const { echartsOptions } = vi.hoisted(() => ({ echartsOptions: [] as any[] }));
vi.mock('echarts/core', () => ({ default: { use: vi.fn() }, use: vi.fn() }));
vi.mock('echarts/charts', () => ({ RadarChart: {}, BarChart: {} }));
vi.mock('echarts/components', () => ({
  GridComponent: {}, TooltipComponent: {}, LegendComponent: {},
  TitleComponent: {}, PolarComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));
vi.mock('echarts-for-react/lib/core', () => ({
  default: (props: any) => {
    echartsOptions.push(props.option);
    return React.createElement('div', { 'data-testid': 'echarts-mock' });
  },
}));

// ═══ Mock API ═══
const { mockApi, mockEfficiency, mockTelemetry } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  mockEfficiency: { deviceEfficiency: vi.fn() },
  mockTelemetry: { stats: vi.fn(), history: vi.fn(), latest: vi.fn() },
}));
vi.mock('../../../api', () => ({
  default: mockApi, efficiencyAPI: mockEfficiency, telemetryAPI: mockTelemetry,
}));

vi.mock('antd', async (importOriginal) => {
  const actual: any = await importOriginal();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import DeviceComparison from '../DeviceComparison';

const lastOption = () => echartsOptions[echartsOptions.length - 1];

beforeEach(() => {
  vi.clearAllMocks();
  echartsOptions.length = 0;
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/devices')) {
      return Promise.resolve({ data: { code: 200, data: { items: [
        { id: 1, name: '逆变器01', status: 'online' },
        { id: 2, name: '储能01', status: 'offline' },
      ] } } });
    }
    return Promise.resolve({ data: { code: 200, data: {} } });
  });
  mockEfficiency.deviceEfficiency.mockImplementation((id: number) =>
    Promise.resolve({ data: { code: 200, data: { utilization: { current: id === 1 ? 92 : 78 } } } }));
  mockTelemetry.stats.mockImplementation((id: number) =>
    Promise.resolve({ data: { code: 200, data: { stats: {
      thermal: { avg_temp: id === 1 ? 40 : 45 },
      grid: { avg_voltage_a: id === 1 ? 230 : 225, avg_power: id === 1 ? 5 : 3 },
    } } } }));
});

// 多选 Select 选两个设备
const pickTwoDevices = async () => {
  const selector = document.querySelector('.ant-select-selector') as Element;
  await act(async () => { fireEvent.mouseDown(selector); });
  await waitFor(() => expect(screen.getByText('逆变器01')).toBeInTheDocument());
  await act(async () => { fireEvent.click(screen.getByText('逆变器01')); });
  await act(async () => { fireEvent.mouseDown(selector); });
  await act(async () => { fireEvent.click(screen.getByText('储能01')); });
  await act(async () => { fireEvent.mouseDown(selector); }); // 关闭下拉
};

const runCompare = async () => {
  const btn = screen.getByRole('button', { name: /开始对比/ });
  await act(async () => { fireEvent.click(btn); });
};

describe('DeviceComparison — 真实数据接入', () => {
  it('对比时调用 efficiencyAPI.deviceEfficiency + telemetryAPI.stats（每设备）', async () => {
    await act(async () => { render(<DeviceComparison />); });
    await pickTwoDevices();
    await runCompare();
    await waitFor(() => expect(mockEfficiency.deviceEfficiency).toHaveBeenCalledWith(1));
    expect(mockEfficiency.deviceEfficiency).toHaveBeenCalledWith(2);
    expect(mockTelemetry.stats).toHaveBeenCalledWith(1);
    expect(mockTelemetry.stats).toHaveBeenCalledWith(2);
  });

  it('真实 utilization.current 进入雷达健康度', async () => {
    await act(async () => { render(<DeviceComparison />); });
    await pickTwoDevices();
    await runCompare();
    await waitFor(() => expect(echartsOptions.length).toBeGreaterThan(0));
    const radar = lastOption();
    const seriesVals = radar.series[0].data;
    const dev1 = seriesVals.find((d: any) => d.name === '逆变器01');
    // metrics 顺序：温度/电压/电流/功率/健康度 → 第 5 个 = 健康度
    expect(dev1.value[4]).toBe(92);
    const dev2 = seriesVals.find((d: any) => d.name === '储能01');
    expect(dev2.value[4]).toBe(78);
  });

  it('状态来自设备列表（online/offline），非随机', async () => {
    const { container } = await act(async () => { return render(<DeviceComparison />); });
    await pickTwoDevices();
    await runCompare();
    await waitFor(() => expect(echartsOptions.length).toBeGreaterThan(0));
    // 表格 Tag：逆变器01 在线，储能01 离线
    expect(container.textContent).toMatch(/逆变器01[\s\S]*在线/);
    expect(container.textContent).toMatch(/储能01[\s\S]*离线/);
  });

  it('两次对比雷达数据恒等（确定性，非随机）', async () => {
    const runOnce = async () => {
      echartsOptions.length = 0;
      mockEfficiency.deviceEfficiency.mockClear();
      mockTelemetry.stats.mockClear();
      const view = await act(async () => { return render(<DeviceComparison />); });
      await pickTwoDevices();
      await runCompare();
      await waitFor(() => expect(echartsOptions.length).toBeGreaterThan(0));
      const snap = JSON.stringify(lastOption().series[0].data);
      view.unmount();
      return snap;
    };
    const a = await runOnce();
    const b = await runOnce();
    expect(b).toBe(a);
  });
});
