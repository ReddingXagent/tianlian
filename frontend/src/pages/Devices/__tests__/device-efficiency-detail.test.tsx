/**
 * DeviceEfficiencyDetail — Vitest 单元测试
 * 覆盖：真实 API 调用（efficiencyAPI.deviceEfficiency）、数据渲染、失败降级（确定性 sin 兜底，无 Math.random）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import React from 'react';

const { mockEfficiencyAPI } = vi.hoisted(() => ({
  mockEfficiencyAPI: { deviceEfficiency: vi.fn() },
}));

vi.mock('../../../api', () => ({
  efficiencyAPI: mockEfficiencyAPI,
}));

// ReactEChartsCore mock（组件用 ReactEChartsCore + echarts.graphic.LinearGradient 构造 option）
vi.mock('echarts-for-react/lib/core', () => ({
  __esModule: true,
  default: () => null,
}));
vi.mock('echarts/core', () => ({
  __esModule: true,
  default: { use: vi.fn() },
  use: vi.fn(),
  graphic: { LinearGradient: vi.fn() },
}));
vi.mock('echarts/charts', () => ({ LineChart: {}, BarChart: {} }));
vi.mock('echarts/components', () => ({
  GridComponent: {}, TooltipComponent: {}, LegendComponent: {}, TitleComponent: {}, DataZoomComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

import DeviceEfficiencyDetail from '../DeviceEfficiencyDetail';

const detailPayload = {
  utilization: { current: 75, trend: 3.5, trend_data: [{ date: '7/24', value: 74 }] },
  charge_efficiency: { current: 90, trend: -1.2, trend_data: [{ date: '7/24', value: 89 }] },
  generation_efficiency: { current: 85, trend: 2.1, trend_data: [{ date: '7/24', value: 84 }] },
  discharge_efficiency: { current: 91, trend: 0.8, trend_data: [{ date: '7/24', value: 90 }] },
};

// 后端 GET /devices/{id}/efficiency 的真实 shape：
//   - trend 是 [{date, value}] 数组（非 number）
//   - 无 trend_data 字段
//   - 无 discharge_efficiency 字段
//   - current 可能是 null（_latest_value 无匹配日志）
const backendPayload = {
  device_id: '1',
  device_name: '测试设备',
  device_code: 'D001',
  device_type: 'PV_INVERTER',
  utilization: {
    current: 75,
    trend: [
      { date: '2026-06-26', value: 70 },
      { date: '2026-07-25', value: 75 },
    ],
  },
  charge_efficiency: {
    current: null, // 后端 _latest_value 无匹配 → null
    trend: [{ date: '2026-07-25', value: 90 }],
  },
  generation_efficiency: {
    current: 85,
    pv_pr: 0.92,
    trend: [
      { date: '2026-06-26', value: 83 },
      { date: '2026-07-25', value: 85 },
    ],
  },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('DeviceEfficiencyDetail', () => {
  it('调用 efficiencyAPI.deviceEfficiency(deviceId)', async () => {
    mockEfficiencyAPI.deviceEfficiency.mockResolvedValue({ data: detailPayload });
    await act(async () => {
      render(<DeviceEfficiencyDetail deviceId={42} deviceType="PV_INVERTER" />);
    });
    await waitFor(() => {
      expect(mockEfficiencyAPI.deviceEfficiency).toHaveBeenCalledWith(42);
    });
  });

  it('渲染真实效率指标（利用率/充电/发电）', async () => {
    mockEfficiencyAPI.deviceEfficiency.mockResolvedValue({ data: detailPayload });
    await act(async () => {
      render(<DeviceEfficiencyDetail deviceId={1} deviceType="PV_INVERTER" />);
    });
    await waitFor(() => {
      expect(screen.getByText('利用率')).toBeInTheDocument();
      expect(screen.getByText('充电效率')).toBeInTheDocument();
      expect(screen.getByText('发电效率')).toBeInTheDocument();
    });
  });

  it('API 失败时降级到确定性兜底（sin 序列）且不崩溃', async () => {
    mockEfficiencyAPI.deviceEfficiency.mockRejectedValue(new Error('fail'));
    await act(async () => {
      const { container } = render(<DeviceEfficiencyDetail deviceId={1} deviceType="PV_INVERTER" />);
      expect(container).toBeTruthy();
    });
    // 降级仍展示三类效率卡片（current 为固定基线，trend_data 为 sin 确定性序列）
    await waitFor(() => {
      expect(screen.getByText('利用率')).toBeInTheDocument();
      expect(screen.getByText('充电效率')).toBeInTheDocument();
    });
  });

  it('V2G 设备类型渲染放电效率卡片', async () => {
    mockEfficiencyAPI.deviceEfficiency.mockResolvedValue({ data: detailPayload });
    await act(async () => {
      render(<DeviceEfficiencyDetail deviceId={1} deviceType="PCS" />);
    });
    await waitFor(() => {
      expect(screen.getByText('放电效率')).toBeInTheDocument();
    });
  });

  // ==================== 后端真实 shape 适配（字段契约冲突修复）====================
  it('后端真实 shape（trend 为数组）→ 映射为 trend_data 并算出趋势百分比，无 NaN', async () => {
    mockEfficiencyAPI.deviceEfficiency.mockResolvedValue({ data: backendPayload });
    let container: HTMLElement;
    await act(async () => {
      ({ container } = render(<DeviceEfficiencyDetail deviceId={1} deviceType="PV_INVERTER" />));
    });
    await waitFor(() => {
      expect(screen.getByText('利用率')).toBeInTheDocument();
    });

    // 利用率 first=70, last=75 → (75-70)/70*100 = 7.14%
    expect(container.textContent).toContain('7.14');
    // 旧逻辑直接对 trend 数组做 Math.abs → ↓NaN%；适配后必须是有限数字
    expect(container.textContent).not.toContain('NaN');
    // trend 数组被映射成 trend_data，趋势图走图表分支而非 Empty
    expect(screen.queryByText('无趋势数据')).toBeNull();
  });

  it('trend 为空数组 → 降级显示无趋势数据且 trend=0，不崩溃', async () => {
    mockEfficiencyAPI.deviceEfficiency.mockResolvedValue({
      data: {
        utilization: { current: 60, trend: [] },
        charge_efficiency: { current: 88, trend: [] },
        generation_efficiency: { current: 80, trend: [] },
      },
    });
    let container: HTMLElement;
    await act(async () => {
      ({ container } = render(<DeviceEfficiencyDetail deviceId={1} deviceType="PV_INVERTER" />));
    });
    await waitFor(() => {
      expect(screen.getByText('利用率')).toBeInTheDocument();
    });
    // trend=0 → ↓0%，不崩、不 NaN
    expect(container.textContent).not.toContain('NaN');
    expect(container.textContent).toContain('↓0%');
    // 三个趋势图均无数据 → 显示 Empty
    expect(screen.queryAllByText('无趋势数据').length).toBeGreaterThan(0);
  });

  it('后端无 discharge_efficiency → V2G 设备不渲染放电效率卡片且不崩溃', async () => {
    mockEfficiencyAPI.deviceEfficiency.mockResolvedValue({ data: backendPayload });
    await act(async () => {
      render(<DeviceEfficiencyDetail deviceId={1} deviceType="PCS" />);
    });
    await waitFor(() => {
      expect(screen.getByText('利用率')).toBeInTheDocument();
    });
    // V2G 设备但后端未返回 discharge_efficiency → 不渲染放电效率卡片
    expect(screen.queryByText('放电效率')).toBeNull();
  });
});
