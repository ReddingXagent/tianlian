/**
 * 充电效率分析 — Vitest 单元测试
 * 覆盖：真实 API 调用、数据渲染、失败降级兜底（无 Math.random）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import React from 'react';

const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn() },
}));

vi.mock('../../../api', () => ({ default: mockApi }));

// 组件用命令式 echarts.init，mock init 返回带 setOption/dispose 的实例
vi.mock('echarts/core', () => ({
  __esModule: true,
  default: {},
  init: vi.fn(() => ({ setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn() })),
  use: vi.fn(),
}));
vi.mock('echarts/charts', () => ({ BarChart: {}, LineChart: {} }));
// 对齐源码 import：TitleComponent, TooltipComponent, GridComponent, MarkLineComponent
vi.mock('echarts/components', () => ({
  GridComponent: {}, TooltipComponent: {}, LegendComponent: {}, TitleComponent: {},
  MarkLineComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

import ChargeEfficiencyAnalysis from '../ChargeEfficiencyAnalysis';

// 对齐后端 GET /reports/efficiency 返回结构 { data: { items, total, alerts } }
const efficiencyData = {
  items: [
    { device_id: 1, device_name: 'CHG_REAL_01', device_code: 'CHG001', device_type: '充电桩', station_id: 1, station_name: '光储充一体站A', charge_efficiency: 94.2 },
    { device_id: 2, device_name: 'BAT_REAL_01', device_code: 'BAT001', device_type: '储能', station_id: 2, station_name: '储能站D', charge_efficiency: 95.8 },
  ],
  total: 2,
  page: 1,
  page_size: 100,
  alerts: {
    abnormal_low_efficiency: {
      count: 1,
      threshold: '70',
      items: [
        { device_id: 3, device_name: 'CHG_REAL_LOW', device_code: 'CHG002', device_type: '充电桩', station_id: 3, station_name: '充电站C', charge_efficiency: 72.1 },
      ],
    },
  },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('充电效率分析', () => {
  it('调用真实接口 /reports/efficiency', async () => {
    mockApi.get.mockResolvedValue({ data: { data: efficiencyData } });
    await act(async () => {
      render(<ChargeEfficiencyAnalysis />);
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/reports/efficiency', { params: { page: 1, page_size: 100 } });
    });
  });

  it('渲染真实数据（设备名 + 概览指标）', async () => {
    mockApi.get.mockResolvedValue({ data: { data: efficiencyData } });
    await act(async () => {
      render(<ChargeEfficiencyAnalysis />);
    });
    await waitFor(() => {
      expect(screen.getByText('CHG_REAL_01')).toBeInTheDocument();
      expect(screen.getByText('平均充电效率')).toBeInTheDocument();
      expect(screen.getByText('异常低效设备')).toBeInTheDocument();
    });
  });

  it('API 失败时降级到空态且不崩溃', async () => {
    mockApi.get.mockRejectedValue(new Error('network error'));
    await act(async () => {
      const { container } = render(<ChargeEfficiencyAnalysis />);
      expect(container).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.getByText('暂无充电效率数据')).toBeInTheDocument();
    });
  });
});
