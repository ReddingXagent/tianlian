import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockDeviceAPI, mockTelemetryAPI } = vi.hoisted(() => ({
  mockDeviceAPI: { list: vi.fn() },
  mockTelemetryAPI: { list: vi.fn(), getLatest: vi.fn() },
}));

vi.mock('../../../api', () => ({ deviceAPI: mockDeviceAPI, telemetryAPI: mockTelemetryAPI }));
vi.mock('echarts-for-react/lib/core', () => ({ default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }) }));
vi.mock('echarts/core', () => ({ use: vi.fn() }));
vi.mock('echarts/charts', () => ({ LineChart: {} }));
vi.mock('echarts/components', () => ({ GridComponent: {}, TooltipComponent: {}, LegendComponent: {}, TitleComponent: {} }));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import TelemetryPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockDeviceAPI.list.mockResolvedValue({ data: { data: { items: [] } } });
  mockTelemetryAPI.list.mockResolvedValue({ data: { data: { items: [] } } });
  mockTelemetryAPI.getLatest.mockResolvedValue({ data: { data: [] } });
});

describe('Telemetry 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><TelemetryPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时获取设备列表', async () => {
    await act(async () => {
      render(<BrowserRouter><TelemetryPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockDeviceAPI.list).toHaveBeenCalled();
    });
  });

  it('渲染Card容器', async () => {
    await act(async () => {
      render(<BrowserRouter><TelemetryPage /></BrowserRouter>);
    });
    expect(document.querySelector('.ant-card')).toBeTruthy();
  });
});
