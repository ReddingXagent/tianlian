/**
 * 发电效率分析 — Vitest 单元测试
 * 覆盖：真实 API 调用、数据渲染、失败降级兜底（无 Math.random）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import React from 'react';

const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn() },
}));

vi.mock('../../../api', () => ({ default: mockApi }));

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

import GenerationEfficiencyAnalysis from '../GenerationEfficiencyAnalysis';

// 对齐后端 GET /reports/generation 返回结构 { data: { items, total, alerts } }
const generationData = {
  items: [
    { device_id: 1, device_name: 'PV_REAL_01', device_code: 'PV001', device_type: '光伏', station_id: 1, station_name: '光储充一体站A', pv_pr_ratio: 0.853, rated_power_kw: 100, runtime_hours: 2000, actual_generation_kwh: 4250, theoretical_generation_kwh: 4980, generation_ratio: 0.85 },
    { device_id: 2, device_name: 'PV_REAL_02', device_code: 'PV002', device_type: '光伏', station_id: 2, station_name: '综合站E', pv_pr_ratio: 0.715, rated_power_kw: 100, runtime_hours: 1800, actual_generation_kwh: 2860, theoretical_generation_kwh: 4000, generation_ratio: 0.715 },
  ],
  total: 2,
  page: 1,
  page_size: 100,
  alerts: {
    high_performance: { count: 1, threshold: '80', items: [] },
    low_performance: {
      count: 1,
      threshold: '65',
      items: [
        { device_id: 2, device_name: 'PV_REAL_02', device_code: 'PV002', device_type: '光伏', station_id: 2, station_name: '综合站E', pv_pr_ratio: 0.715, rated_power_kw: 100, runtime_hours: 1800, actual_generation_kwh: 2860, theoretical_generation_kwh: 4000, generation_ratio: 0.715 },
      ],
    },
  },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('发电效率分析', () => {
  it('调用真实接口 /reports/generation', async () => {
    mockApi.get.mockResolvedValue({ data: { data: generationData } });
    await act(async () => {
      render(<GenerationEfficiencyAnalysis />);
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/reports/generation', { params: { page: 1, page_size: 100 } });
    });
  });

  it('渲染真实数据（设备名 + 概览指标）', async () => {
    mockApi.get.mockResolvedValue({ data: { data: generationData } });
    await act(async () => {
      render(<GenerationEfficiencyAnalysis />);
    });
    await waitFor(() => {
      expect(screen.getByText('PV_REAL_01')).toBeInTheDocument();
      expect(screen.getByText('平均PR值')).toBeInTheDocument();
      expect(screen.getByText('低效光伏设备')).toBeInTheDocument();
    });
  });

  it('API 失败时降级到空态且不崩溃', async () => {
    mockApi.get.mockRejectedValue(new Error('network error'));
    await act(async () => {
      const { container } = render(<GenerationEfficiencyAnalysis />);
      expect(container).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.getByText('暂无发电效率数据')).toBeInTheDocument();
    });
  });
});
