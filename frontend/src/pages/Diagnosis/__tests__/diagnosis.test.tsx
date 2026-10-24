/**
 * 智能诊断页面 — Vitest 单元测试
 *
 * 覆盖：渲染、批量诊断概览、设备诊断Tab、站点诊断Tab、统计卡片
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API
// ═══════════════════════════════════════════
const { mockApi, mockDiagnosisAPI } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  mockDiagnosisAPI: {
    diagnoseDevice: vi.fn(),
    diagnoseBatch: vi.fn(),
    getHealthTrend: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ default: mockApi }));
vi.mock('../../../api/diagnosis', () => ({
  diagnosisAPI: mockDiagnosisAPI,
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

vi.mock('echarts-for-react/lib/core', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock'),
}));

vi.mock('echarts/core', () => ({ use: vi.fn() }));
vi.mock('echarts/charts', () => ({ RadarChart: {}, LineChart: {}, PieChart: {} }));
vi.mock('echarts/components', () => ({
  GridComponent: {}, TooltipComponent: {}, LegendComponent: {},
  TitleComponent: {}, RadarComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockBatchResult = {
  total_devices: 50,
  healthy_devices: 40,
  warning_devices: 7,
  fault_devices: 2,
  critical_devices: 1,
  avg_health_score: 88.5,
  summary: { risk_devices: 3, health_rate: 80.0 },
  top_issues: [
    { device_name: 'PV-001', health_score: 55, alarm_count: 3, status: 'fault' },
  ],
};

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/devices')) return Promise.resolve({ data: { items: [{ id: 1, name: '设备1', sn: 'SN001' }] } });
    if (url.includes('/stations')) return Promise.resolve({ data: { items: [{ id: 1, name: '浦东站' }] } });
    return Promise.resolve({ data: { items: [] } });
  });
  mockDiagnosisAPI.diagnoseBatch.mockResolvedValue(mockBatchResult);
  mockDiagnosisAPI.diagnoseDevice.mockResolvedValue({
    device_id: 1,
    device_name: '设备1',
    device_sn: 'SN001',
    device_type: 'battery_inverter',
    station_name: '浦东站',
    overall_health: 85,
    diagnosis_time: new Date().toISOString(),
    risk_level: 'medium',
    scores: { electrical_safe: 90, thermal: 80, communication: 85, power_quality: 88, mechanical: 82 },
    analysis: [{ category: '电气安全', issue: '电压偏高', severity: 'medium', score: 90, action: '持续监控' }],
    recommendations: [{ priority: 'medium', category: '电气安全', action: '定期检查', reason: '电压偏高' }],
    alarm_stats: { active: 1, total: 3 },
    workorder_stats: { pending: 0, total: 2 },
    estimated_cost: { min: 500, max: 2000 },
    predicted_failures: [],
  });
  mockDiagnosisAPI.getHealthTrend.mockResolvedValue({ trend_data: [] });
});

import DiagnosisPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 概览
// ═══════════════════════════════════════════
describe('智能诊断 — 渲染 & 概览', () => {
  it('页面正常渲染，显示标题', async () => {
    renderWithRouter(<DiagnosisPage />);
    await waitFor(() => {
      expect(screen.getByText('智能诊断中心')).toBeInTheDocument();
    });
  });

  it('显示批量诊断统计卡片', async () => {
    renderWithRouter(<DiagnosisPage />);
    await waitFor(() => {
      expect(screen.getByText('设备总数')).toBeInTheDocument();
      expect(screen.getByText('平均健康度')).toBeInTheDocument();
      expect(screen.getByText('风险设备')).toBeInTheDocument();
      expect(screen.getByText('健康率')).toBeInTheDocument();
    });
  });

  it('显示设备诊断Tab和站点诊断Tab', async () => {
    renderWithRouter(<DiagnosisPage />);
    await waitFor(() => {
      expect(screen.getByText('设备诊断')).toBeInTheDocument();
      expect(screen.getByText('站点诊断')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 交互
// ═══════════════════════════════════════════
describe('智能诊断 — 交互', () => {
  it('显示开始诊断按钮', async () => {
    renderWithRouter(<DiagnosisPage />);
    await waitFor(() => {
      expect(screen.getByText('开始诊断')).toBeInTheDocument();
    });
  });

  it('显示需关注设备表格', async () => {
    renderWithRouter(<DiagnosisPage />);
    await waitFor(() => {
      // Station diagnosis tab content should have '需关注设备'
      const stationTab = screen.getByText('站点诊断');
      fireEvent.click(stationTab);
    });
    await waitFor(() => {
      expect(screen.getByText('需关注设备')).toBeInTheDocument();
    });
  });
});
