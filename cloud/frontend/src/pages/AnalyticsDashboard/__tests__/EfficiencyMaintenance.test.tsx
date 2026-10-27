/**
 * 卡 980f4d94 — EfficiencyAnalysis / MaintenanceOptimizer 真实后端接线测试
 * 覆盖: 端点映射(GET /reports/efficiency, GET /predictive-maintenance/dashboard)、
 * 真实数据渲染、请求失败不展示 mock 假数据
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

import EfficiencyAnalysis from '../EfficiencyAnalysis';
import MaintenanceOptimizer from '../MaintenanceOptimizer';

// ═══ Mock API (拦截器已解包, res.data 即业务数据) ═══
const { mockApi, mockStationAPI } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  mockStationAPI: {
    businessList: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ default: mockApi, stationAPI: mockStationAPI }));

vi.mock('echarts/core', () => ({
  default: { use: vi.fn(), init: vi.fn(() => ({ dispose: vi.fn(), setOption: vi.fn(), resize: vi.fn() })) },
  use: vi.fn(),
  init: vi.fn(() => ({ dispose: vi.fn(), setOption: vi.fn(), resize: vi.fn() })),
}));
vi.mock('echarts/charts', () => ({ PieChart: {}, BarChart: {}, LineChart: {} }));
vi.mock('echarts/components', () => ({
  TitleComponent: {}, TooltipComponent: {}, LegendComponent: {}, GridComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

const efficiencyReport = {
  items: [
    { device_id: 1, device_name: '充电桩A', device_code: 'CHG001', device_type: 'charger', station_id: 1, station_name: '测试站点A', charge_efficiency: 92.5 },
    { device_id: 2, device_name: '充电桩B', device_code: 'CHG002', device_type: 'charger', station_id: 1, station_name: '测试站点A', charge_efficiency: 55.0 },
  ],
  total: 2,
  page: 1,
  page_size: 100,
  alerts: {
    abnormal_low_efficiency: {
      count: 1,
      threshold: '<70.0%',
      items: [
        { device_id: 2, device_name: '充电桩B', device_code: 'CHG002', device_type: 'charger', station_id: 1, station_name: '测试站点A', charge_efficiency: 55.0 },
      ],
    },
  },
};

const maintenanceDashboard = {
  total_devices: 5,
  predicted_devices: 3,
  risk_summary: { low: 1, medium: 1, high: 1, critical: 0 },
  predictions: [
    {
      device_id: 1, device_name: '电池柜01', prediction_time: '2026-10-08T00:00:00Z',
      failure_probability: 0.8, failure_probability_display: '80%', risk_level: 'high',
      risk_emoji: '🔴', health_trend: 'declining', trend_emoji: '📉', rul_hours: 48,
      rul_display: '约48小时', anomaly_score: 0.9, key_indicators: [],
      recommended_actions: ['检查散热风扇', '更换温度传感器'], confidence: 0.85,
    },
    {
      device_id: 2, device_name: '逆变器01', prediction_time: '2026-10-08T00:00:00Z',
      failure_probability: 0.1, failure_probability_display: '10%', risk_level: 'low',
      risk_emoji: '🟢', health_trend: 'stable', trend_emoji: '➡️', rul_hours: 720,
      rul_display: '约720小时', anomaly_score: 0.1, key_indicators: [],
      recommended_actions: [], confidence: 0.9,
    },
  ],
  model_status: { '1': { trained: true } },
};

describe('EfficiencyAnalysis (GET /reports/efficiency)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStationAPI.businessList.mockResolvedValue({
      data: { items: [{ id: 1, name: '测试站点A' }] },
    });
  });

  it('调用真实端点并渲染效率排名与异常预警', async () => {
    mockApi.get.mockResolvedValue({ data: efficiencyReport });
    render(<EfficiencyAnalysis />);

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/reports/efficiency', {
        params: expect.objectContaining({ station_id: 1, min_efficiency: 70, page_size: 100 }),
      });
    });
    await waitFor(() => {
      // 设备同时出现在预警列表和排名表格 → 用 AllBy
      expect(screen.getAllByText('充电桩A').length).toBeGreaterThan(0);
      expect(screen.getAllByText('充电桩B').length).toBeGreaterThan(0);
    });
    // 不再调用不存在的 POST /analytics/efficiency
    expect(mockApi.post).not.toHaveBeenCalledWith('/analytics/efficiency', expect.anything());
  });

  it('请求失败时不展示 mock 假数据', async () => {
    mockApi.get.mockRejectedValue(new Error('network error'));
    render(<EfficiencyAnalysis />);
    await waitFor(() => expect(mockApi.get).toHaveBeenCalled());
    // mock 假数据设备名不应出现
    await waitFor(() => {
      expect(screen.queryByText('BAT001')).not.toBeInTheDocument();
      expect(screen.queryByText('INV001')).not.toBeInTheDocument();
    });
  });
});

describe('MaintenanceOptimizer (GET /predictive-maintenance/dashboard)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('调用真实端点并渲染风险汇总与预测明细', async () => {
    mockApi.get.mockResolvedValue({ data: maintenanceDashboard });
    render(<MaintenanceOptimizer />);

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/predictive-maintenance/dashboard');
    });
    await waitFor(() => {
      // 设备同时出现在建议列表和预测表格 → 用 AllBy
      expect(screen.getAllByText('电池柜01').length).toBeGreaterThan(0);
      expect(screen.getAllByText('逆变器01').length).toBeGreaterThan(0);
      expect(screen.getAllByText('约48小时').length).toBeGreaterThan(0);
    });
    expect(mockApi.post).not.toHaveBeenCalledWith('/analytics/maintenance-optimization', expect.anything());
  });

  it('请求失败时不展示 mock 假数据', async () => {
    mockApi.get.mockRejectedValue(new Error('network error'));
    render(<MaintenanceOptimizer />);
    await waitFor(() => expect(mockApi.get).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.queryByText('光伏板清洁')).not.toBeInTheDocument();
      expect(screen.queryByText('风扇电机')).not.toBeInTheDocument();
    });
  });
});
