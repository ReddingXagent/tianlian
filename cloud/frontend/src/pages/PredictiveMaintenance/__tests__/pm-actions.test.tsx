/**
 * PredictiveMaintenance 行为测试
 * 覆盖: Dashboard 设备详情导航 + History CSV 导出
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══ Mocks ═══
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn() },
}));
vi.mock('../../../api', () => ({ default: mockApi }));

const { mockExportObjectsCSV } = vi.hoisted(() => ({ mockExportObjectsCSV: vi.fn() }));
vi.mock('../../../utils/csvExport', () => ({ exportObjectsCSV: mockExportObjectsCSV }));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import Dashboard from '../Dashboard';
import History from '../History';

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockReset();
});

// ═══ Dashboard 设备详情导航 ═══
describe('PM Dashboard — 设备详情导航', () => {
  beforeEach(() => {
    mockApi.get.mockResolvedValue({
      data: {
        total_devices: 20,
        healthy_devices: 15,
        warning_devices: 4,
        critical_devices: 1,
        upcoming_failures: [
          { device_id: 'D001', device_name: '逆变器01', failure_probability: 0.85, predicted_failure_date: '2026-07-25', maintenance_recommendation: '更换电容' },
        ],
        health_trend: [{ date: '2026-07-20', avg_health: 88 }],
      },
    });
  });

  it('点击"详情"跳转到 /devices?deviceId=<id>', async () => {
    render(<BrowserRouter><Dashboard /></BrowserRouter>);

    const detailBtn = await screen.findByText('详情');
    fireEvent.click(detailBtn);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/devices?deviceId=D001');
    });
  });
});

// ═══ History CSV 导出 ═══
describe('PM History — CSV 导出', () => {
  beforeEach(() => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/predictive-maintenance')) {
        return Promise.resolve({
          data: {
            history: [
              { prediction_id: 'P1', device_id: 'D1', device_name: '设备A', prediction_time: '2026-07-20 10:00:00', failure_probability: 0.5, predicted_failure_date: '2026-08-01', health_score: 80, result: 'pending' },
            ],
          },
        });
      }
      if (url.includes('/devices')) {
        return Promise.resolve({ data: { devices: [{ id: 'D1', name: '设备A' }] } });
      }
      return Promise.resolve({ data: {} });
    });
  });

  it('点击"导出"调用 exportObjectsCSV', async () => {
    render(<BrowserRouter><History /></BrowserRouter>);

    const exportBtn = await screen.findByRole('button', { name: /导出/ });
    fireEvent.click(exportBtn);

    await waitFor(() => {
      expect(mockExportObjectsCSV).toHaveBeenCalledTimes(1);
    });
  });
});
