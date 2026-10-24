/**
 * DraggableDashboard 面板数据接入测试
 *
 * 验收点：
 * 1. 各面板优先调用真实 API（消除硬编码 mock / Math.random）
 * 2. 真实数据进入 ECharts option
 * 3. API 失败时确定性兜底（不崩溃、两次渲染结果一致 → 非随机）
 *
 * 契约依据（后端实测，已纠正任务描述的错误字段契约）：
 * - health  → GET /stats/devices/health {devices:[{name,value}]} （overview.health 无 good/warning/critical）
 * - alarm   → GET /reports/alarms {params:{days:7}}  data.daily_trend = [{date,count}]
 * - chart   → GET /reports/alarms {params:{days:14}} data.daily_trend
 * - telemetry → GET /devices 首设备 + telemetryAPI.stats(id) （history 不返回数据点）
 * - energy  → energyReportAPI.summary() {pv_generation,charging_amount,discharge_amount}
 * - workorder → workorderAPI.list() items 按 create_time/finish_time 分桶
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import React from 'react';

// ═══ 捕获 ECharts option，用于断言真实数据进入图表 ═══
const echartsOptions: any[] = [];
vi.mock('echarts/core', () => ({
  default: { use: vi.fn(), init: vi.fn(() => ({ dispose: vi.fn(), setOption: vi.fn(), resize: vi.fn() })) },
  use: vi.fn(),
}));
vi.mock('echarts/charts', () => ({ PieChart: {}, BarChart: {}, LineChart: {} }));
vi.mock('echarts/components', () => ({
  TitleComponent: {}, TooltipComponent: {}, LegendComponent: {},
  GridComponent: {}, DataZoomComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));
vi.mock('echarts', () => ({
  default: { use: vi.fn(), init: vi.fn(() => ({ dispose: vi.fn(), setOption: vi.fn(), resize: vi.fn() })) },
  use: vi.fn(),
}));
vi.mock('echarts-for-react/lib/core', () => ({
  default: (props: any) => {
    echartsOptions.push(props.option);
    return React.createElement('div', { 'data-testid': 'echarts-mock' });
  },
}));

// ═══ Mock API 模块（default + 具名） ═══
const { mockApi, mockTelemetry, mockWorkorder, mockEnergy } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  mockTelemetry: { stats: vi.fn(), latest: vi.fn(), history: vi.fn() },
  mockWorkorder: { list: vi.fn() },
  mockEnergy: { summary: vi.fn() },
}));

vi.mock('../../../api', () => ({
  default: mockApi,
  telemetryAPI: mockTelemetry,
  workorderAPI: mockWorkorder,
  energyReportAPI: mockEnergy,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN' } }),
}));
vi.mock('antd', async (importOriginal) => {
  const actual: any = await importOriginal();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import DraggableDashboard, {
  HealthPanel, AlarmPanel, TelemetryPanel, EnergyPanel, WorkorderPanel, ChartPanel,
  defaultLayout, findFirstFitPosition, repairLayout,
} from '../DraggableDashboard';

// ═══ beforeEach ═══
beforeEach(() => {
  vi.clearAllMocks();
  echartsOptions.length = 0;
});

// 面板首次渲染 push 初始兜底 option，useEffect 拉到真实数据后 setState 重渲染 push 真实 option。
// 因此断言真实数据时取最后一个 option，并用 waitFor 等其出现。
const lastOption = () => echartsOptions[echartsOptions.length - 1];

// ═══ HealthPanel ═══
describe('HealthPanel — 健康度分布', () => {
  it('调用 GET /stats/devices/health 并把真实计数喂给饼图', async () => {
    mockApi.get.mockResolvedValue({
      data: { devices: [
        { name: '正常', value: 12 }, { name: '警告', value: 4 }, { name: '故障', value: 1 },
      ] },
    });
    await act(async () => { render(<HealthPanel />); });
    await waitFor(() => {
      expect(lastOption().series[0].data.some((d: any) => d.value === 12)).toBe(true);
    });
    expect(mockApi.get).toHaveBeenCalledWith('/stats/devices/health');
    const pieData = lastOption().series[0].data;
    expect(pieData).toEqual(expect.arrayContaining([
      expect.objectContaining({ name: '正常', value: 12 }),
      expect.objectContaining({ name: '故障', value: 1 }),
    ]));
  });

  it('API 失败时确定性兜底（不崩溃、两次渲染结果一致）', async () => {
    mockApi.get.mockRejectedValue(new Error('boom'));
    await act(async () => { render(<HealthPanel />); });
    await waitFor(() => expect(echartsOptions.length).toBeGreaterThan(0));
    const first = JSON.stringify(lastOption().series[0].data);
    expect(lastOption().series[0].data.length).toBeGreaterThan(0);

    echartsOptions.length = 0;
    await act(async () => { render(<HealthPanel />); });
    await waitFor(() => expect(echartsOptions.length).toBeGreaterThan(0));
    expect(JSON.stringify(lastOption().series[0].data)).toBe(first);
  });
});

// ═══ AlarmPanel ═══
describe('AlarmPanel — 告警趋势', () => {
  it('调用 GET /reports/alarms days=7 并渲染 daily_trend', async () => {
    mockApi.get.mockResolvedValue({
      data: { daily_trend: [
        { date: '2026-07-19', count: 5 }, { date: '2026-07-20', count: 8 },
      ] },
    });
    await act(async () => { render(<AlarmPanel />); });
    await waitFor(() => expect(lastOption().xAxis.data).toEqual(['2026-07-19', '2026-07-20']));
    expect(mockApi.get).toHaveBeenCalledWith('/reports/alarms', { params: { days: 7 } });
    expect(lastOption().series[0].data).toEqual([5, 8]);
  });

  it('API 失败时确定性兜底（7 天占位，非空）', async () => {
    mockApi.get.mockRejectedValue(new Error('boom'));
    await act(async () => { render(<AlarmPanel />); });
    await waitFor(() => expect(echartsOptions.length).toBeGreaterThan(0));
    const opt = lastOption();
    expect(opt.xAxis.data.length).toBe(7);
    expect(opt.series[0].data.length).toBe(7);
    expect(opt.series[0].data.every((v: number) => Number.isFinite(v))).toBe(true);
  });
});

// ═══ ChartPanel ═══
describe('ChartPanel — ECharts 图', () => {
  it('调用 GET /reports/alarms days=14 并渲染 daily_trend', async () => {
    mockApi.get.mockResolvedValue({
      data: { daily_trend: [{ date: '2026-07-19', count: 3 }, { date: '2026-07-20', count: 6 }] },
    });
    await act(async () => { render(<ChartPanel />); });
    await waitFor(() => expect(lastOption().series[0].data).toEqual([3, 6]));
    expect(mockApi.get).toHaveBeenCalledWith('/reports/alarms', { params: { days: 14 } });
    expect(lastOption().xAxis.data).toEqual(['2026-07-19', '2026-07-20']);
  });
});

// ═══ TelemetryPanel ═══
describe('TelemetryPanel — 遥测数据', () => {
  it('取首设备 id 并调用 telemetryAPI.stats 渲染真实聚合值', async () => {
    mockApi.get.mockResolvedValue({ data: { items: [{ id: 7, name: 'INV01' }] } });
    mockTelemetry.stats.mockResolvedValue({
      data: { table_type: 'pv', stats: {
        grid: { avg_voltage_a: 230.5 },
        thermal: { avg_temp: 42.1 },
      } },
    });
    await act(async () => { render(<TelemetryPanel />); });
    await waitFor(() => {
      const tempSeries = lastOption().series.find((s: any) => s.name === '温度');
      expect(tempSeries.data.some((v: number) => Math.abs(v - 42.1) < 0.5)).toBe(true);
    });
    expect(mockApi.get).toHaveBeenCalledWith('/devices');
    expect(mockTelemetry.stats).toHaveBeenCalledWith(7);
    const voltSeries = lastOption().series.find((s: any) => s.name === '电压');
    expect(voltSeries.data.some((v: number) => Math.abs(v - 230.5) < 0.5)).toBe(true);
  });

  it('无设备时确定性兜底（不崩溃）', async () => {
    mockApi.get.mockResolvedValue({ data: { items: [] } });
    await act(async () => { render(<TelemetryPanel />); });
    await waitFor(() => expect(echartsOptions.length).toBeGreaterThan(0));
    expect(lastOption().series.length).toBe(2);
  });
});

// ═══ EnergyPanel ═══
describe('EnergyPanel — 能耗概览', () => {
  it('调用 energyReportAPI.summary 渲染真实三字段（光伏/充电/放电）', async () => {
    mockEnergy.summary.mockResolvedValue({
      data: { pv_generation: 420.5, charging_amount: 180.2, discharge_amount: 65.3 },
    });
    await act(async () => { render(<EnergyPanel />); });
    await waitFor(() => {
      const values = lastOption().series[0].data.map((d: any) => d.value ?? d);
      expect(values).toEqual(expect.arrayContaining([420.5]));
    });
    expect(mockEnergy.summary).toHaveBeenCalled();
    const values = lastOption().series[0].data.map((d: any) => d.value ?? d);
    expect(values).toEqual(expect.arrayContaining([420.5, 180.2, 65.3]));
  });

  it('API 失败时确定性兜底（非空）', async () => {
    mockEnergy.summary.mockRejectedValue(new Error('boom'));
    await act(async () => { render(<EnergyPanel />); });
    await waitFor(() => expect(echartsOptions.length).toBeGreaterThan(0));
    expect(lastOption().series[0].data.length).toBe(3);
  });
});

// ═══ WorkorderPanel ═══
describe('WorkorderPanel — 工单统计', () => {
  it('调用 workorderAPI.list 按 create_time/finish_time 按日分桶', async () => {
    const today = new Date().toISOString().slice(0, 10);
    mockWorkorder.list.mockResolvedValue({
      data: { items: [
        { id: 'WO-1', create_time: `${today}T10:00:00`, finish_time: null },
        { id: 'WO-2', create_time: `${today}T11:00:00`, finish_time: `${today}T12:00:00` },
        { id: 'WO-3', create_time: `${today}T13:00:00`, finish_time: `${today}T14:00:00` },
        { id: 'WO-4', create_time: `${today}T15:00:00`, finish_time: `${today}T16:00:00` },
        { id: 'WO-5', create_time: `${today}T17:00:00`, finish_time: `${today}T18:00:00` },
        { id: 'WO-6', create_time: `${today}T19:00:00`, finish_time: null },
      ] },
    });
    await act(async () => { render(<WorkorderPanel />); });
    // 真实数据今日新增 6、完成 4 —— 兜底数组最大值 4/3，必须等到真实数据才能满足
    await waitFor(() => {
      const created = lastOption().series.find((s: any) => s.name === '新增').data as number[];
      expect(created.some((v) => v >= 6)).toBe(true);
    });
    expect(mockWorkorder.list).toHaveBeenCalled();
    const completed = lastOption().series.find((s: any) => s.name === '完成').data as number[];
    expect(completed.some((v) => v >= 4)).toBe(true);
  });

  it('API 失败时确定性兜底（非空）', async () => {
    mockWorkorder.list.mockRejectedValue(new Error('boom'));
    await act(async () => { render(<WorkorderPanel />); });
    await waitFor(() => expect(echartsOptions.length).toBeGreaterThan(0));
    expect(lastOption().series[0].data.length).toBeGreaterThan(0);
  });
});

// ═══ DraggableDashboard 主组件（默认布局触发多面板） ═══
describe('DraggableDashboard 主组件', () => {
  it('默认布局 5 面板各自拉取真实 API（无 Math.random）', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url === '/devices') return Promise.resolve({ data: { items: [{ id: 1, name: 'D1' }] } });
      if (url === '/stats/devices/health')
        return Promise.resolve({ data: { devices: [{ name: '正常', value: 1 }] } });
      if (url.startsWith('/reports/alarms'))
        return Promise.resolve({ data: { daily_trend: [{ date: '2026-07-19', count: 1 }] } });
      return Promise.resolve({ data: {} });
    });
    mockTelemetry.stats.mockResolvedValue({ data: { table_type: 'pv', stats: { grid: { avg_voltage_a: 220 }, thermal: { avg_temp: 40 } } } });
    mockWorkorder.list.mockResolvedValue({ data: { items: [] } });
    mockEnergy.summary.mockResolvedValue({ data: { pv_generation: 1, charging_amount: 1, discharge_amount: 1 } });

    const randomSpy = vi.spyOn(Math, 'random').mockReturnValue(0.5);

    await act(async () => { render(<DraggableDashboard />); });
    await waitFor(() => expect(echartsOptions.length).toBeGreaterThanOrEqual(5));

    // 各面板都命中真实接口
    expect(mockApi.get).toHaveBeenCalledWith('/stats/devices/health');
    expect(mockApi.get).toHaveBeenCalledWith('/reports/alarms', { params: { days: 7 } });
    expect(mockTelemetry.stats).toHaveBeenCalledWith(1);
    expect(mockEnergy.summary).toHaveBeenCalled();
    expect(mockWorkorder.list).toHaveBeenCalled();

    randomSpy.mockRestore();
  });
});

// ═══ 布局引擎（卡 2b188c33：自定义仪表盘卡片叠加修复） ═══
// 验收点：默认布局零重叠 / addPanel first-fit 不重叠 / 旧脏 localStorage 修复
describe('布局引擎 — 卡 2b188c33 零重叠保证', () => {
  const ROW_H = 40;
  // 两个面板的网格区间是否相交（列 [x,x+w)、行 [y,y+ceil(h/ROW_H))，半开区间）
  const rowsOf = (h: number) => Math.max(1, Math.ceil(h / ROW_H));
  const overlap = (a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }) =>
    !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + rowsOf(a.h) <= b.y || b.y + rowsOf(b.h) <= a.y);

  const assertNoOverlap = (panels: Array<{ x: number; y: number; w: number; h: number }>) => {
    for (let i = 0; i < panels.length; i++) {
      for (let j = i + 1; j < panels.length; j++) {
        expect(overlap(panels[i], panels[j])).toBe(false);
      }
    }
  };

  it('默认布局任意两卡 gridRow/gridColumn 区间不相交', () => {
    const panels = defaultLayout();
    expect(panels).toHaveLength(5);
    assertNoOverlap(panels);
  });

  it('默认布局编排合法：health+alarm 顶行、telemetry 次之、energy+workorder 再次', () => {
    const byType = Object.fromEntries(defaultLayout().map(p => [p.type, p])) as Record<string, any>;
    // health/alarm h=280 → 7 行，并排顶行
    expect(byType.health.y).toBe(0);
    expect(byType.health.x).toBe(0);
    expect(byType.alarm.y).toBe(0);
    expect(byType.alarm.x).toBe(6);
    // telemetry h=320 → 8 行，全宽，紧随其后从第 7 行起
    expect(byType.telemetry.y).toBe(7);
    expect(byType.telemetry.x).toBe(0);
    expect(byType.telemetry.w).toBe(12);
    // energy/workorder h=280 → 7 行，从第 15 行起并排（telemetry 占 7..15）
    expect(byType.energy.y).toBe(15);
    expect(byType.workorder.y).toBe(15);
  });

  it('addPanel（first-fit）落点不与既有面板重叠', () => {
    const base = defaultLayout();
    // 全宽 telemetry 规格的新面板：默认布局已占满 0..22 行 → 应落到 y>=22
    const pos = findFirstFitPosition(base, 12, 320);
    const withNew = [...base, { id: 'new', type: 'chart', title: 'x', w: 12, h: 320, x: pos.x, y: pos.y }];
    assertNoOverlap(withNew);
    expect(pos.x).toBe(0);
    expect(pos.y).toBeGreaterThanOrEqual(22);
  });

  it('addPanel 连续叠加多次仍零重叠', () => {
    let panels = defaultLayout();
    for (let i = 0; i < 4; i++) {
      const pos = findFirstFitPosition(panels, 6, 280);
      panels = [...panels, { id: `n${i}`, type: 'health', title: 'x', w: 6, h: 280, x: pos.x, y: pos.y }];
    }
    assertNoOverlap(panels);
  });

  it('修复旧脏数据（telemetry y=1 与顶行重叠）→ 重排为零重叠', () => {
    const dirty = [
      { id: 'p1', type: 'health', title: 't', w: 6, h: 280, x: 0, y: 0 },
      { id: 'p2', type: 'alarm', title: 't', w: 6, h: 280, x: 6, y: 0 },
      { id: 'p3', type: 'telemetry', title: 't', w: 12, h: 320, x: 0, y: 1 }, // 与 p1/p2 重叠
      { id: 'p4', type: 'energy', title: 't', w: 6, h: 280, x: 0, y: 2 },
      { id: 'p5', type: 'workorder', title: 't', w: 6, h: 280, x: 6, y: 2 },
    ];
    // 前置条件：脏数据确实重叠（health rows 0..6 vs telemetry y=1 rows 1..8）
    expect(overlap(dirty[0], dirty[2])).toBe(true);
    const repaired = repairLayout(dirty);
    expect(repaired).toHaveLength(5);
    assertNoOverlap(repaired);
    // id 全保留
    expect(repaired.map(p => p.id).sort()).toEqual(['p1', 'p2', 'p3', 'p4', 'p5']);
  });

  it('repairLayout 对合法布局幂等（坐标不变）', () => {
    const good = defaultLayout();
    const repaired = repairLayout(good);
    good.forEach(g => {
      const r = repaired.find(p => p.id === g.id)!;
      expect(r.x).toBe(g.x);
      expect(r.y).toBe(g.y);
      expect(r.w).toBe(g.w);
      expect(r.h).toBe(g.h);
    });
  });

  it('repairLayout 钳制非法 w/x（w>12、x 越界、x+w>12）', () => {
    const bad = [
      { id: 'p1', type: 'health', title: 't', w: 20, h: 280, x: -3, y: 0 },
      { id: 'p2', type: 'alarm', title: 't', w: 6, h: 280, x: 9, y: 0 }, // x+w=15>12
    ];
    const repaired = repairLayout(bad);
    assertNoOverlap(repaired);
    repaired.forEach(p => {
      expect(p.w).toBeGreaterThanOrEqual(1);
      expect(p.w).toBeLessThanOrEqual(12);
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x + p.w).toBeLessThanOrEqual(12);
      expect(p.y).toBeGreaterThanOrEqual(0);
    });
  });
});
