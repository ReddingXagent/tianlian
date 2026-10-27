/**
 * PredictiveMaintenance — Vitest 组件测试
 * 测试: 主页 Tab 渲染 + 子页面渲染 + Tab 切换
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══ Mock API ═══
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ default: mockApi }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import PredictiveMaintenancePage from '../index';

// ═══ beforeEach ═══
beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/predictive-maintenance/dashboard')) {
      return Promise.resolve({
        data: {
          total_devices: 20,
          healthy_devices: 15,
          warning_devices: 4,
          critical_devices: 1,
          upcoming_failures: [
            { device_id: 'D001', device_name: '逆变器01', failure_probability: 85, predicted_failure_date: '2026-07-25', maintenance_recommendation: '更换电容' },
          ],
          health_trend: [{ date: '2026-07-20', avg_health: 88 }],
        },
      });
    }
    if (url.includes('/devices')) {
      return Promise.resolve({
        data: [
          { id: 'D001', name: '逆变器01', type: 'inverter', station: '站点A' },
          { id: 'D002', name: '充电桩02', type: 'charger', station: '站点B' },
        ],
      });
    }
    if (url.includes('/predictive-maintenance/models')) {
      return Promise.resolve({
        data: [
          { model_id: 'M001', model_name: '故障预测模型', model_type: 'random_forest', version: '1.0', status: 'trained', accuracy: 92, last_trained: '2026-07-01', training_progress: 100 },
        ],
      });
    }
    if (url.includes('/predictive-maintenance/history')) {
      return Promise.resolve({
        data: [],
      });
    }
    return Promise.resolve({ data: {} });
  });
  mockApi.post.mockResolvedValue({});
});

// ═══ Tests ═══

describe('PredictiveMaintenance 主页', () => {
  it('渲染 4 个 Tab（仪表盘、设备预测、模型管理、预测历史）', async () => {
    await act(async () => {
      render(<BrowserRouter><PredictiveMaintenancePage /></BrowserRouter>);
    });
    expect(screen.getByText('仪表盘')).toBeInTheDocument();
    expect(screen.getByText('设备预测')).toBeInTheDocument();
    expect(screen.getByText('模型管理')).toBeInTheDocument();
    expect(screen.getByText('预测历史')).toBeInTheDocument();
  });

  it('默认选中"仪表盘" Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><PredictiveMaintenancePage /></BrowserRouter>);
    });
    const dashTab = screen.getByText('仪表盘').closest('.ant-tabs-tab');
    expect(dashTab?.classList.contains('ant-tabs-tab-active')).toBe(true);
  });

  it('切换到"设备预测" Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><PredictiveMaintenancePage /></BrowserRouter>);
    });

    const predictionTab = screen.getByText('设备预测').closest('.ant-tabs-tab');
    fireEvent.click(predictionTab!);

    await waitFor(() => {
      const activeTab = screen.getByText('设备预测').closest('.ant-tabs-tab');
      expect(activeTab?.classList.contains('ant-tabs-tab-active')).toBe(true);
    });
  });

  it('切换到"模型管理" Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><PredictiveMaintenancePage /></BrowserRouter>);
    });

    const modelTab = screen.getByText('模型管理').closest('.ant-tabs-tab');
    fireEvent.click(modelTab!);

    await waitFor(() => {
      const activeTab = screen.getByText('模型管理').closest('.ant-tabs-tab');
      expect(activeTab?.classList.contains('ant-tabs-tab-active')).toBe(true);
    });
  });

  it('切换到"预测历史" Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><PredictiveMaintenancePage /></BrowserRouter>);
    });

    const historyTab = screen.getByText('预测历史').closest('.ant-tabs-tab');
    fireEvent.click(historyTab!);

    await waitFor(() => {
      const activeTab = screen.getByText('预测历史').closest('.ant-tabs-tab');
      expect(activeTab?.classList.contains('ant-tabs-tab-active')).toBe(true);
    });
  });
});
