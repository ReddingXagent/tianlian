/**
 * 虚拟电厂(VPP)页面 — Vitest 单元测试
 *
 * 覆盖：渲染、总览仪表盘、调度面板、站点状态、调度历史
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  // VPP 页通过 api(config) 函数式调用（axios 实例风格），mock 需可调用且带方法
  mockApi: Object.assign(vi.fn(), {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  }),
}));

vi.mock('../../../api', () => ({ default: mockApi }));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

vi.mock('echarts-for-react/lib/core', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock'),
}));

vi.mock('echarts/core', () => ({ use: vi.fn() }));
vi.mock('echarts/charts', () => ({ LineChart: {}, BarChart: {} }));
vi.mock('echarts/components', () => ({
  GridComponent: {}, TooltipComponent: {}, LegendComponent: {},
  TitleComponent: {}, DataZoomComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  // All API calls fail → component renders error states (no mock fallback)
  mockApi.mockImplementation((config: any) => {
    const url: string = config?.url || '';
    if (url.includes('/stations')) return mockApi.get(url);
    return Promise.resolve({ data: { code: 200, data: [] } });
  });
  mockApi.get.mockRejectedValue(new Error('use fallback'));
  mockApi.post.mockRejectedValue(new Error('use fallback'));
  mockApi.delete.mockRejectedValue(new Error('use fallback'));
});

import VPPPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 总览
// ═══════════════════════════════════════════
describe('VPP — 渲染 & 总览', () => {
  it('页面正常渲染，显示标题', async () => {
    renderWithRouter(<VPPPage />);
    await waitFor(() => {
      expect(screen.getByText('虚拟电厂(VPP)调度优化')).toBeInTheDocument();
    });
  });

  it('显示总览统计卡片', async () => {
    renderWithRouter(<VPPPage />);
    await waitFor(() => {
      expect(screen.getByText('在线站点')).toBeInTheDocument();
      expect(screen.getByText('光伏装机')).toBeInTheDocument();
      expect(screen.getByText('储能容量')).toBeInTheDocument();
      expect(screen.getByText('可调度功率')).toBeInTheDocument();
    });
  });

  it('显示操作按钮', async () => {
    renderWithRouter(<VPPPage />);
    await waitFor(() => {
      expect(screen.getByText('刷新')).toBeInTheDocument();
      expect(screen.getByText('重载模拟数据')).toBeInTheDocument();
      expect(screen.getByText('注册站点')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 站点状态 & 调度
// ═══════════════════════════════════════════
describe('VPP — 站点状态 & 调度', () => {
  it('显示调度执行面板', async () => {
    renderWithRouter(<VPPPage />);
    await waitFor(() => {
      expect(screen.getByText('调度模式：')).toBeInTheDocument();
      expect(screen.getByText('执行调度')).toBeInTheDocument();
    });
  });

  it('显示调度历史', async () => {
    renderWithRouter(<VPPPage />);
    await waitFor(() => {
      expect(screen.getByText('调度历史')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// API失败错误态（卡afa42983：不回退mock假数据）
// ═══════════════════════════════════════════
describe('VPP — API失败错误态', () => {
  it('API 全部失败时渲染错误提示+重试，不显示假站点/假历史', async () => {
    renderWithRouter(<VPPPage />);
    await waitFor(() => {
      expect(screen.getByText('部分数据加载失败')).toBeInTheDocument();
      expect(screen.getAllByText('重试').length).toBeGreaterThan(0);
    });
    // 不回退 mock 假数据
    expect(screen.queryByText('华东-上海虹桥站')).not.toBeInTheDocument();
    expect(screen.queryByText('华东-杭州西站')).not.toBeInTheDocument();
    expect(screen.queryByText(/峰谷套利/)).not.toBeInTheDocument();
  });

  it('stations 失败时站点区显示错误 Alert', async () => {
    mockApi.mockImplementation(() => Promise.reject(new Error('stations down')));
    renderWithRouter(<VPPPage />);
    await waitFor(() => {
      expect(screen.getByText('站点状态加载失败')).toBeInTheDocument();
    });
  });

  it('正常返回时显示真实站点卡片', async () => {
    mockApi.mockImplementation((config: any) => {
      const url: string = config?.url || '';
      if (url.includes('/stations')) {
        return Promise.resolve({ data: { code: 200, data: [
          { station_id: 'ST-101', station_name: '真实站点A', total_pv_kw: 100, total_battery_kwh: 200, total_ev_chargers: 10, current_load_kw: 50, current_pv_output_kw: 60, current_battery_soc: 0.7, available_dispatch_kw: 80, online: true },
        ] } });
      }
      return Promise.resolve({ data: { code: 200, data: [] } });
    });
    renderWithRouter(<VPPPage />);
    await waitFor(() => {
      expect(screen.getByText('真实站点A')).toBeInTheDocument();
    });
  });
});
