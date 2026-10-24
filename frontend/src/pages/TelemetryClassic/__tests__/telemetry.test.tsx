/**
 * 遥测数据页面 — Vitest 单元测试
 *
 * 覆盖：
 * - 页面渲染、设备选择、数据卡片展示、趋势图Tab、详情弹窗
 * - 真实 API 接入（telemetryAPI.latest / stats / history）
 * - 确定性兜底（无 Math.random，相同入参恒等输出）
 *
 * 契约依据（后端实测，见 analytics-dashboard-panel-api-contract 记忆）：
 * - telemetryAPI.history 只返回 {count,mode}，不返回数据点 → 走确定性兜底
 * - 兜底用 telemetryAPI.stats 取真实基线 + deterministic.ts 的 sin 序列（无随机）
 * - latest 仅有 grid_power_total/battery_soc/charger_power 等少量字段
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// 捕获 ECharts option（ReactEChartsCore mock）
// ═══════════════════════════════════════════
const { echartsOptions } = vi.hoisted(() => ({ echartsOptions: [] as any[] }));
vi.mock('echarts-for-react/lib/core', () => ({
  default: (props: any) => {
    echartsOptions.push(props.option);
    return React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock');
  },
}));

vi.mock('echarts/core', () => ({ use: vi.fn() }));
vi.mock('echarts/charts', () => ({ LineChart: {} }));
vi.mock('echarts/components', () => ({
  GridComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
  TitleComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

// ═══════════════════════════════════════════
// Mock API
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

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

// 收集所有渲染过的 option 里【非空】series.data（用于确定性比对）。
// 过滤空 series：组件 loading 切换会产生 series.data=[] 的中间态，污染比对。
const allSeriesData = () =>
  JSON.stringify(
    echartsOptions.flatMap((opt: any) =>
      (opt?.series ?? [])
        .filter((s: any) => Array.isArray(s?.data) && s.data.length > 0)
        .map((s: any) => s.data)
    )
  );

// 等到至少出现一个非空 series（historyData 就绪），避免在中间态取快照
const waitForSeries = () =>
  waitFor(() => expect(JSON.parse(allSeriesData()).length).toBeGreaterThan(0));

// 找到指定名称的 series（按 name 模糊匹配）；从最新的 option 起向前找【非空 data】，
// 跳过 loading/historyData 未就绪时产生的中间态空 series。
const findSeries = (needle: string) => {
  for (let i = echartsOptions.length - 1; i >= 0; i--) {
    const opt = echartsOptions[i];
    const s = (opt?.series ?? []).find(
      (x: any) =>
        typeof x?.name === 'string' &&
        x.name.includes(needle) &&
        Array.isArray(x.data) &&
        x.data.length > 0,
    );
    if (s) return s;
  }
  return undefined;
};

beforeEach(() => {
  vi.clearAllMocks();
  echartsOptions.length = 0;
  // 默认：/devices 返回真实设备列表；latest 返回真实最新值；history 无数据点；stats 返回真实基线
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/devices')) {
      return Promise.resolve({ data: { code: 200, data: { items: [
        { id: 1, name: '储能逆变器-01', type: 'battery_inverter', sn: 'SN-01' },
        { id: 2, name: '直流充电桩-001', type: 'charger_dc', sn: 'SN-02' },
      ] } } });
    }
    return Promise.resolve({ data: { code: 200, data: {} } });
  });
  mockTelemetry.latest.mockResolvedValue({
    data: { code: 200, data: { device_id: 1, device_name: '储能逆变器-01', device_type: 'battery_inverter', grid_power_total: 6.2, battery_soc: 55 } },
  });
  mockTelemetry.history.mockResolvedValue({ data: { code: 200, data: [] } });
  mockTelemetry.stats.mockResolvedValue({
    data: { code: 200, data: { stats: { grid: { avg_voltage_a: 230, avg_power: 5 }, thermal: { avg_temp: 42 } } } },
  });
});

import TelemetryPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 基础
// ═══════════════════════════════════════════
describe('遥测数据 — 渲染 & 基础', () => {
  it('页面正常渲染，显示遥测数据监控标题', async () => {
    renderWithRouter(<TelemetryPage />);
    await waitFor(() => {
      expect(screen.getByText('遥测数据监控')).toBeInTheDocument();
    });
  });

  it('显示设备选择下拉框（来自真实 /devices API）', async () => {
    renderWithRouter(<TelemetryPage />);
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/devices');
    });
    expect(screen.getByText(/储能逆变器-01/)).toBeInTheDocument();
  });

  it('显示操作按钮（自动刷新、刷新、详情）', async () => {
    renderWithRouter(<TelemetryPage />);
    await waitFor(() => {
      expect(screen.getByText('自动刷新')).toBeInTheDocument();
      expect(screen.getByText('刷新')).toBeInTheDocument();
      expect(screen.getByText('详情')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 数据卡片
// ═══════════════════════════════════════════
describe('遥测数据 — 数据卡片', () => {
  it('默认设备(储能逆变器)显示电网侧数据卡片', async () => {
    renderWithRouter(<TelemetryPage />);
    await waitFor(() => {
      expect(screen.getByText('电网侧数据')).toBeInTheDocument();
    });
  });

  it('默认设备显示电池侧数据卡片', async () => {
    renderWithRouter(<TelemetryPage />);
    await waitFor(() => {
      expect(screen.getByText('电池侧数据')).toBeInTheDocument();
      expect(screen.getByText('SOC (电池容量)')).toBeInTheDocument();
      expect(screen.getByText('SOH (健康度)')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 趋势图 & 详情弹窗
// ═══════════════════════════════════════════
describe('遥测数据 — 趋势图 & 详情', () => {
  it('显示趋势分析区域和三个趋势Tab', async () => {
    renderWithRouter(<TelemetryPage />);
    await waitFor(() => {
      expect(screen.getByText('趋势分析')).toBeInTheDocument();
      expect(screen.getByText('功率趋势')).toBeInTheDocument();
      expect(screen.getByText('SOC趋势')).toBeInTheDocument();
      expect(screen.getByText('温度趋势')).toBeInTheDocument();
    });
  });

  it('点击详情按钮打开弹窗', async () => {
    renderWithRouter(<TelemetryPage />);
    await waitFor(() => expect(screen.getByText('遥测数据监控')).toBeInTheDocument());

    fireEvent.click(screen.getByText('详情'));

    await waitFor(() => {
      expect(screen.getByText('遥测数据详情')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 真实 API 接入
// ═══════════════════════════════════════════
describe('遥测数据 — 真实 API 接入', () => {
  it('调用 telemetryAPI.latest 取最新遥测', async () => {
    renderWithRouter(<TelemetryPage />);
    await waitFor(() => expect(mockTelemetry.latest).toHaveBeenCalledWith(1));
  });

  it('history 无数据点时调用 telemetryAPI.stats 取真实基线', async () => {
    renderWithRouter(<TelemetryPage />);
    await waitFor(() => expect(mockTelemetry.stats).toHaveBeenCalledWith(1));
  });

  it('history 返回真实数据点时直接进入图表（不走确定性兜底）', async () => {
    // 真实点：grid_power_total=12.34 在第 0 个点
    mockTelemetry.history.mockResolvedValue({
      data: { code: 200, data: [{ timestamp: '2026-07-25T10:00:00', grid_power_total: 12.34, battery_power: 2.1, internal_temperature: 41, ambient_temperature: 26, battery_soc: 60 }] },
    });
    renderWithRouter(<TelemetryPage />);
    await waitForSeries();
    const totalSeries = findSeries('总功率');
    expect(totalSeries).toBeTruthy();
    expect(totalSeries.data).toContain(12.34);
  });
});

// ═══════════════════════════════════════════
// 确定性兜底（无 Math.random）
// ═══════════════════════════════════════════
describe('遥测数据 — 确定性兜底（无 Math.random）', () => {
  it('相同入参两次渲染，趋势图 series 数值恒等', async () => {
    const renderOnce = async () => {
      echartsOptions.length = 0;
      const view = renderWithRouter(<TelemetryPage />);
      await waitForSeries();
      const snap = allSeriesData();
      view.unmount();
      return snap;
    };
    const a = await renderOnce();
    const b = await renderOnce();
    expect(b).toBe(a);
  });

  it('趋势图所有 series 数据点为有限值（无 NaN/Infinity）', async () => {
    renderWithRouter(<TelemetryPage />);
    await waitForSeries();
    const allFinite = echartsOptions.every((opt: any) =>
      (opt?.series ?? []).every((s: any) => (s?.data ?? []).every((v: any) => typeof v === 'number' && Number.isFinite(v)))
    );
    expect(allFinite).toBe(true);
  });

  it('stats 也失败时纯兜底常量仍恒等且全部有限', async () => {
    mockTelemetry.stats.mockRejectedValue(new Error('boom'));
    const renderOnce = async () => {
      echartsOptions.length = 0;
      const view = renderWithRouter(<TelemetryPage />);
      await waitForSeries();
      const snap = allSeriesData();
      view.unmount();
      return snap;
    };
    const a = await renderOnce();
    const b = await renderOnce();
    expect(b).toBe(a);
    const allFinite = echartsOptions.every((opt: any) =>
      (opt?.series ?? []).every((s: any) => (s?.data ?? []).every((v: any) => typeof v === 'number' && Number.isFinite(v)))
    );
    expect(allFinite).toBe(true);
  });
});

// ═══════════════════════════════════════════
// API失败错误态（卡afa42983：不回退假设备）
// ═══════════════════════════════════════════
describe('遥测数据 — API失败错误态', () => {
  it('/devices 失败时渲染错误提示+重试，不显示假设备', async () => {
    mockApi.get.mockRejectedValue(new Error('network down'));
    renderWithRouter(<TelemetryPage />);
    await waitFor(() => {
      expect(screen.getByText('设备列表加载失败')).toBeInTheDocument();
      expect(screen.getByText(/network down/)).toBeInTheDocument();
      expect(screen.getByText('重试')).toBeInTheDocument();
    });
    // 不回退硬编码假设备
    expect(screen.queryByText(/浦东站/)).not.toBeInTheDocument();
    expect(mockTelemetry.latest).not.toHaveBeenCalled();
  });

  it('/devices 返回空列表时为空态，不塞假设备', async () => {
    mockApi.get.mockResolvedValue({ data: { code: 200, data: { items: [] } } });
    renderWithRouter(<TelemetryPage />);
    await waitFor(() => expect(mockApi.get).toHaveBeenCalledWith('/devices'));
    expect(screen.queryByText(/浦东站/)).not.toBeInTheDocument();
    expect(screen.queryByText(/储能逆变器-01/)).not.toBeInTheDocument();
    expect(screen.getByText('选择设备')).toBeInTheDocument();
  });
});
