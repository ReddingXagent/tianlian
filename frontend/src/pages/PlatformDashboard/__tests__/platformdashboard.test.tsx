import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockStatsAPI, mockTenantAPI, mockPlatformMonitorAPI } = vi.hoisted(() => ({
  mockStatsAPI: { overview: vi.fn() },
  mockTenantAPI: { list: vi.fn(), stats: vi.fn() },
  mockPlatformMonitorAPI: { topology: vi.fn(), deviceAccessStats: vi.fn() },
}));

vi.mock('../../../api', () => ({
  statsAPI: mockStatsAPI,
  tenantAPI: mockTenantAPI,
  platformMonitorAPI: mockPlatformMonitorAPI,
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import PlatformDashboardPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockStatsAPI.overview.mockResolvedValue({ data: { station_count: 0, device_count: 0 } });
  mockTenantAPI.list.mockResolvedValue({ data: { items: [] } });
  mockTenantAPI.stats.mockResolvedValue({ data: { total_tenants: 0 } });
  mockPlatformMonitorAPI.topology.mockResolvedValue({
    data: {
      nodes: [
        { id: 'api-gateway', name: 'API Gateway', type: 'gateway', status: 'healthy', response_time_ms: 15, dependencies: [] },
        { id: 'auth-service', name: '认证服务', type: 'backend', status: 'healthy', response_time_ms: 30, dependencies: [] },
        { id: 'postgres', name: 'PostgreSQL', type: 'db', status: 'healthy', response_time_ms: 8, dependencies: [] },
      ],
      status_summary: { healthy: 3, degraded: 0, down: 0 },
      type_summary: { gateway: 1, backend: 1, db: 1 },
      device_online_rate: 100,
      timestamp: 1719000000,
    },
  });
  mockPlatformMonitorAPI.deviceAccessStats.mockResolvedValue({
    data: {
      total_devices: 0,
      total_online: 0,
      total_offline: 0,
      total_fault: 0,
      online_rate: 0,
      device_categories: [],
      protocol_distribution: [],
      timestamp: 1719000000,
    },
  });
});

describe('PlatformDashboard 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><PlatformDashboardPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时获取统计数据', async () => {
    await act(async () => {
      render(<BrowserRouter><PlatformDashboardPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockStatsAPI.overview).toHaveBeenCalled();
    });
    expect(mockTenantAPI.list).toHaveBeenCalled();
  });

  it('挂载时获取拓扑数据', async () => {
    await act(async () => {
      render(<BrowserRouter><PlatformDashboardPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockPlatformMonitorAPI.topology).toHaveBeenCalled();
    });
  });

  it('挂载时获取设备接入统计', async () => {
    await act(async () => {
      render(<BrowserRouter><PlatformDashboardPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockPlatformMonitorAPI.deviceAccessStats).toHaveBeenCalled();
    });
  });

  it('渲染Card/Row组件', async () => {
    await act(async () => {
      render(<BrowserRouter><PlatformDashboardPage /></BrowserRouter>);
    });
    expect(document.querySelector('.ant-card, .ant-row')).toBeTruthy();
  });

  it('渲染SVG拓扑图', async () => {
    await act(async () => {
      render(<BrowserRouter><PlatformDashboardPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(document.querySelector('svg')).toBeTruthy();
    });
  });
});
