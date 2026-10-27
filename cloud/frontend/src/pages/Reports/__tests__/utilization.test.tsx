/**
 * 设备利用率分析 — Vitest 单元测试
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
vi.mock('echarts/components', () => ({
  GridComponent: {}, TooltipComponent: {}, LegendComponent: {}, TitleComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

import UtilizationAnalysis from '../UtilizationAnalysis';

// 对齐 8e7b5d3cb 后后端 GET /reports/utilization 真实返回结构
const utilizationPayload = {
  items: [
    { device_id: 1, device_name: '充电桩A-01', device_code: 'CG-A-01', device_type: '充电桩', station_id: 1, station_name: '光储充一体站A', utilization_rate: 78.5 },
    { device_id: 2, device_name: '充电桩C-02', device_code: 'CG-C-02', device_type: '充电桩', station_id: 2, station_name: '充电站C', utilization_rate: 92.1 },
  ],
  total: 2,
  page: 1,
  page_size: 100,
  alerts: {
    low_utilization: { count: 0, threshold: '<30%', items: [] },
    overload: {
      count: 1, threshold: '>90%',
      items: [{ device_id: 2, device_name: '充电桩C-02', device_code: 'CG-C-02', device_type: '充电桩', station_id: 2, station_name: '充电站C', utilization_rate: 92.1 }],
    },
  },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('设备利用率分析', () => {
  it('调用真实接口 /reports/utilization', async () => {
    mockApi.get.mockResolvedValue({ data: { code: 200, data: utilizationPayload } });
    await act(async () => {
      render(<UtilizationAnalysis />);
    });
    await waitFor(() => {
      // 8e7b5d3cb 后组件按 page_size:100 拉取
      expect(mockApi.get).toHaveBeenCalledWith('/reports/utilization', { params: { page: 1, page_size: 100 } });
    });
  });

  it('渲染真实数据（站点名 + 概览指标）', async () => {
    mockApi.get.mockResolvedValue({ data: { code: 200, data: utilizationPayload } });
    await act(async () => {
      render(<UtilizationAnalysis />);
    });
    await waitFor(() => {
      expect(screen.getByText('光储充一体站A')).toBeInTheDocument();
      expect(screen.getByText('平均利用率')).toBeInTheDocument();
      expect(screen.getByText('低利用率设备')).toBeInTheDocument();
    });
  });

  it('API 失败时降级到空状态且不崩溃', async () => {
    mockApi.get.mockRejectedValue(new Error('network error'));
    await act(async () => {
      const { container } = render(<UtilizationAnalysis />);
      expect(container).toBeTruthy();
    });
    await waitFor(() => {
      // 8e7b5d3cb 移除内置兜底数据：失败时降级为 Empty 空状态，不崩溃
      expect(screen.getByText('暂无利用率数据')).toBeInTheDocument();
    });
  });
});
