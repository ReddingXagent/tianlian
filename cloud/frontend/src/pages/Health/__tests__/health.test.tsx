/**
 * 健康度管理页面 — Vitest 单元测试
 *
 * 覆盖：渲染、概览统计卡片、Tab切换(设备健康榜/健康评估/异常设备)、详情弹窗
 * 数据来源: mock healthAPI.list() 返回聚合结构
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock antd message (避免 jsdom 下报错)
// ═══════════════════════════════════════════
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

// ═══════════════════════════════════════════
// Mock healthAPI.list 返回聚合数据
// ═══════════════════════════════════════════
vi.mock('../../../api', () => ({
  healthAPI: {
    list: vi.fn().mockResolvedValue({
      data: {
        overall: {
          totalDevices: 156,
          healthyCount: 128,
          warningCount: 21,
          criticalCount: 7,
          pendingEval: 12,
          overallScore: 87.5,
        },
        rankings: {
          best: [
            { id: 1, deviceName: '光伏逆变器#1', code: 'PV001', type: 'pv_inverter', stationName: '浦东光伏电站', score: 95, status: 'normal' },
          ],
          worst: [
            { id: 2, deviceName: '储能设备#1', code: 'BAT001', type: 'battery', stationName: '浦西储能站', score: 55, status: 'critical' },
          ],
        },
        evaluations: [
          { id: 1, deviceId: 1, deviceName: 'PV-Inverter-001', stationName: '浦东光伏电站', score: 92, evaluator: '张工', evalDate: '2026-05-31 14:30', issues: ['轻微灰尘积聚'], status: 'normal' },
          { id: 2, deviceId: 2, deviceName: 'Battery-Pack-A03', stationName: '浦西储能站', score: 78, evaluator: '李工', evalDate: '2026-05-31 10:15', issues: ['电池容量衰减'], status: 'warning' },
        ],
        abnormal: [
          { id: 1, deviceName: 'Charger-C12', stationName: '虹桥充电站', score: 65, abnormalIndicators: ['充电模块故障', '通信中断'], suggestion: '立即检修充电模块' },
        ],
      },
    }),
    trend: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

function clickTab(label: string) {
  const tabs = document.querySelectorAll('.ant-tabs-tab');
  for (let i = 0; i < tabs.length; i++) {
    if (tabs[i].textContent?.includes(label)) {
      fireEvent.click(tabs[i]);
      return;
    }
  }
}

beforeEach(() => {
  vi.clearAllMocks();
});

import HealthPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 概览
// ═══════════════════════════════════════════
describe('健康度 — 渲染 & 概览', () => {
  it('页面正常渲染，显示总设备数', async () => {
    renderWithRouter(<HealthPage />);
    await waitFor(() => {
      expect(screen.getByText('总设备数')).toBeInTheDocument();
    });
  });

  it('显示健康设备统计', async () => {
    renderWithRouter(<HealthPage />);
    await waitFor(() => {
      expect(screen.getByText('健康设备')).toBeInTheDocument();
      expect(screen.getByText('告警设备')).toBeInTheDocument();
      expect(screen.getByText('严重异常')).toBeInTheDocument();
    });
  });

  it('显示整体健康分', async () => {
    renderWithRouter(<HealthPage />);
    await waitFor(() => {
      expect(screen.getByText('整体健康分')).toBeInTheDocument();
    });
  });

  it('挂载时调用 healthAPI.list', async () => {
    const { healthAPI } = await import('../../../api');
    renderWithRouter(<HealthPage />);
    await waitFor(() => {
      expect(healthAPI.list).toHaveBeenCalled();
    });
  });
});

// ═══════════════════════════════════════════
// Tab 切换
// ═══════════════════════════════════════════
describe('健康度 — Tab切换', () => {
  it('默认显示设备健康榜Tab(最佳/最差排名)', async () => {
    renderWithRouter(<HealthPage />);
    await waitFor(() => {
      expect(screen.getByText('浦东光伏电站')).toBeInTheDocument();
      expect(screen.getByText('浦西储能站')).toBeInTheDocument();
    });
  });

  it('切换到健康评估Tab', async () => {
    renderWithRouter(<HealthPage />);
    await waitFor(() => expect(screen.getByText('浦东光伏电站')).toBeInTheDocument());

    clickTab('健康评估');

    await waitFor(() => {
      expect(screen.getByText('PV-Inverter-001')).toBeInTheDocument();
      expect(screen.getByText('Battery-Pack-A03')).toBeInTheDocument();
    });
  });

  it('切换到异常设备Tab', async () => {
    renderWithRouter(<HealthPage />);
    await waitFor(() => expect(screen.getByText('浦东光伏电站')).toBeInTheDocument());

    clickTab('异常设备');

    await waitFor(() => {
      expect(screen.getByText('Charger-C12')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 详情弹窗
// ═══════════════════════════════════════════
describe('健康度 — 详情弹窗', () => {
  it('点击查看详情打开弹窗', async () => {
    renderWithRouter(<HealthPage />);
    await waitFor(() => expect(screen.getByText('浦东光伏电站')).toBeInTheDocument());
    clickTab('健康评估');
    await waitFor(() => expect(screen.getByText('PV-Inverter-001')).toBeInTheDocument());

    const detailBtns = screen.getAllByText('查看详情');
    expect(detailBtns.length).toBeGreaterThan(0);
    fireEvent.click(detailBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('健康评估详情')).toBeInTheDocument();
    });
  });
});
