/**
 * OpsDashboard — Vitest 组件测试
 * 测试: 运维大屏渲染 + 拓扑统计 + 事件流 + 健康度
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
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

import OpsDashboardPage from '../index';

// ═══ Canvas mock helper ═══
function mockCanvasContext() {
  const ctx: any = {};
  const noop = () => {};
  ctx.fillRect = noop;
  ctx.fillText = noop;
  ctx.arc = noop;
  ctx.beginPath = noop;
  ctx.closePath = noop;
  ctx.moveTo = noop;
  ctx.lineTo = noop;
  ctx.stroke = noop;
  ctx.fill = noop;
  ctx.scale = noop;
  ctx.setTransform = noop;
  ctx.clearRect = noop;
  ctx.save = noop;
  ctx.restore = noop;
  ctx.bezierCurveTo = noop;
  ctx.quadraticCurveTo = noop;
  ctx.setLineDash = noop;
  ctx.createLinearGradient = () => ({ addColorStop: noop });
  ctx.createRadialGradient = () => ({ addColorStop: noop });
  ctx.measureText = () => ({ width: 50 });
  ctx.fillStyle = '';
  ctx.strokeStyle = '';
  ctx.lineWidth = 1;
  ctx.font = '';
  ctx.textAlign = '';
  ctx.textBaseline = '';
  ctx.globalAlpha = 1;
  ctx.shadowColor = '';
  ctx.shadowBlur = 0;
  return ctx;
}

// ═══ beforeEach ═══
beforeEach(() => {
  vi.clearAllMocks();

  HTMLCanvasElement.prototype.getContext = vi.fn(() => mockCanvasContext()) as any;

  document.documentElement.requestFullscreen = vi.fn();
  document.exitFullscreen = vi.fn();

  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/ops-dashboard/topology')) {
      return Promise.resolve({
        data: {
          nodes: {
            stations: [
              { id: 's1', type: 'station', name: '站点北京', status: 'online', health_score: 92, device_count: 20, online_count: 18, fault_count: 2, station_id: 1 },
            ],
            gateways: [
              { id: 'g1', type: 'gateway', name: '网关01', status: 'online', health_score: 95, station_id: 1, gateway_id: 1 },
            ],
            devices: [
              { id: 'd1', type: 'device', name: '逆变器01', status: 'online', device_type: 'inverter', station_id: 1, gateway_id: 1 },
              { id: 'd2', type: 'device', name: '充电桩01', status: 'fault', device_type: 'charger', station_id: 1, gateway_id: 1 },
            ],
          },
          edges: [
            { source: 's1', target: 'g1', type: 'station_gateway' },
            { source: 'g1', target: 'd1', type: 'gateway_device' },
            { source: 'g1', target: 'd2', type: 'gateway_device' },
          ],
          summary: {
            total_stations: 1,
            total_gateways: 1,
            total_devices: 2,
            online_devices: 1,
            fault_devices: 1,
          },
        },
      });
    }
    if (url.includes('/ops-dashboard/events')) {
      return Promise.resolve({
        data: [
          { id: 'e1', type: 'alarm', title: '充电桩故障', level: 'critical', status: 'active', station_name: '站点北京', device_name: '充电桩01', timestamp: new Date().toISOString() },
          { id: 'e2', type: 'healing', title: '自愈执行完成', level: 'info', status: 'success', station_name: '站点北京', result: '成功', timestamp: new Date().toISOString() },
        ],
      });
    }
    if (url.includes('/ops-dashboard/health')) {
      return Promise.resolve({
        data: {
          overall_score: 88,
          overall_online_rate: 90,
          total_stations: 1,
          total_devices: 2,
          total_online: 1,
          total_fault: 1,
          distribution: { excellent: 1, good: 0, warning: 0, fault: 1 },
          stations: [
            { station_id: 1, station_name: '站点北京', health_score: 92, device_health_avg: 90, online_rate: 90, device_count: 2, online_count: 1, fault_count: 1, status: 'online' },
          ],
        },
      });
    }
    if (url.includes('/ops-dashboard/overview')) {
      return Promise.resolve({
        data: {
          stats: { stations: 1, devices: 2, online: 1, fault: 1, online_rate: 50 },
          alarms: { active: 1, critical: 1 },
          workorders: { pending: 2, in_progress: 1 },
          healing: { total_24h: 5, success_24h: 4, success_rate: 80 },
          timestamp: new Date().toISOString(),
        },
      });
    }
    return Promise.resolve({ data: {} });
  });
});

// ═══ Tests ═══

describe('OpsDashboard 运维大屏', () => {
  it('渲染标题"天链运维大屏"', async () => {
    await act(async () => {
      render(<BrowserRouter><OpsDashboardPage /></BrowserRouter>);
    });
    expect(screen.getByText('天链运维大屏')).toBeInTheDocument();
  });

  it('渲染"实时"标签', async () => {
    await act(async () => {
      render(<BrowserRouter><OpsDashboardPage /></BrowserRouter>);
    });
    expect(screen.getByText('实时')).toBeInTheDocument();
  });

  it('渲染拓扑统计标签（站点/网关/设备/在线/故障）', async () => {
    await act(async () => {
      render(<BrowserRouter><OpsDashboardPage /></BrowserRouter>);
    });
    await waitFor(() => {
      const labels = screen.getAllByText('站点');
      expect(labels.length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText('网关').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('设备').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('在线').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('故障').length).toBeGreaterThanOrEqual(1);
  });

  it('渲染全屏按钮', async () => {
    await act(async () => {
      render(<BrowserRouter><OpsDashboardPage /></BrowserRouter>);
    });
    const fullscreenIcon = document.querySelector('.anticon-fullscreen');
    expect(fullscreenIcon).toBeTruthy();
  });

  it('渲染最后更新时间', async () => {
    await act(async () => {
      render(<BrowserRouter><OpsDashboardPage /></BrowserRouter>);
    });
    expect(screen.getByText(/最后更新/)).toBeInTheDocument();
  });
});

// ═══ 卡 fcfd13fd: 拓扑画布尺寸处理回归测试 ═══
import { renderTopology } from '../topology';

describe('renderTopology 画布尺寸 (卡 fcfd13fd)', () => {
  const emptyData = {
    nodes: { stations: [], gateways: [], devices: [] },
    edges: [],
    summary: { total_stations: 0, total_gateways: 0, total_devices: 0, online_devices: 0, fault_devices: 0 },
  };

  function fakeCanvas(w: number, h: number): HTMLCanvasElement {
    const canvas: any = {
      clientWidth: w,
      clientHeight: h,
      width: 0,
      height: 0,
      style: {},
      getContext: () => mockCanvasContext(),
    };
    return canvas as HTMLCanvasElement;
  }

  it('重复渲染不叠乘 DPR（backing store 尺寸稳定）', () => {
    const canvas = fakeCanvas(800, 600);
    renderTopology(canvas, emptyData, null, () => {});
    renderTopology(canvas, emptyData, null, () => {});
    expect(canvas.width).toBe(800); // clientWidth * dpr(1)
    expect(canvas.height).toBe(600);
  });

  it('不再写死 style 宽高 px，保持容器 100% 布局', () => {
    const canvas = fakeCanvas(800, 600);
    renderTopology(canvas, emptyData, null, () => {});
    expect(canvas.style.width).toBeUndefined();
    expect(canvas.style.height).toBeUndefined();
  });

  it('容器尚未布局（0 尺寸）时安全跳过，不产生 NaN', () => {
    const canvas = fakeCanvas(0, 0);
    expect(() => renderTopology(canvas, emptyData, null, () => {})).not.toThrow();
  });
});
