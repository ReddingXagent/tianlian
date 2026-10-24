/**
 * 异常检测仪表板 — Vitest 渲染冒烟测试
 *
 * 口径：真实渲染路径不崩 + 关键交互触发预期 mock 调用（冒烟，不追求行覆盖）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';

// echarts mock：init/dispose/setOption 全部替换，避免 canvas 渲染
const { mockChart } = vi.hoisted(() => ({
  mockChart: { setOption: vi.fn(), dispose: vi.fn() },
}));
vi.mock('echarts/core', () => ({
  use: vi.fn(),
  init: vi.fn(() => mockChart),
}));
vi.mock('echarts/charts', () => ({ PieChart: {} }));
vi.mock('echarts/components', () => ({
  TitleComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ default: mockApi, __esModule: true }));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import AnomalyDetection from '../AnomalyDetection';

// 组件读 res.data?.code === 200 与 res.data.data.items —— mock 需包一层 axios 风格 data
const mockDevices = {
  data: {
    code: 200,
    data: { items: [{ id: 11, name: '充电桩-A' }, { id: 12, name: '充电桩-B' }] },
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue(mockDevices);
});

describe('异常检测 — 渲染冒烟', () => {
  it('挂载拉取设备列表并自动选中首个设备发起检测', async () => {
    mockApi.post.mockResolvedValue({
      data: {
        code: 200,
      data: {
        device_id: 11,
        device_name: '充电桩-A',
        anomaly_score: 0.42,
        detected_anomalies: [
          { type: 'temperature', timestamp: '2026-09-01 10:00', severity: 'warning', description: '温度偏高42°C' },
        ],
        severity: 'low',
        root_causes: ['散热风扇转速不足'],
        suggested_actions: ['检查风扇运行状态'],
      },
      },
    });

    render(<AnomalyDetection />);

    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/devices');
      expect(mockApi.post).toHaveBeenCalledWith('/analytics/anomaly-detection', { device_id: 11, hours: 24 });
    });
    // 关键卡片标题渲染
    expect(await screen.findByText('异常类型分布')).toBeInTheDocument();
    expect(screen.getByText('检测到的异常')).toBeInTheDocument();
    expect(screen.getByText('根因分析')).toBeInTheDocument();
    expect(screen.getByText('建议措施')).toBeInTheDocument();
    expect(screen.getByText('散热风扇转速不足')).toBeInTheDocument();
  });

  it('检测接口返回非 200 时走演示兜底数据不崩溃', async () => {
    mockApi.post.mockResolvedValue({ data: { code: 500, message: 'no data' } });

    render(<AnomalyDetection />);

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalled();
    });
    // 演示根因/措施文案出现
    expect(await screen.findByText('检查风扇运行状态')).toBeInTheDocument();
  });

  it('点击检测按钮以当前选中设备重新调用检测', async () => {
    mockApi.post.mockResolvedValue({ data: { code: 500, message: 'no data' } });

    render(<AnomalyDetection />);
    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledTimes(1);
    });

    await act(async () => {
      fireEvent.click(screen.getByText('检测'));
    });

    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledTimes(2);
      expect(mockApi.post).toHaveBeenLastCalledWith('/analytics/anomaly-detection', { device_id: 11, hours: 24 });
    });
  });

  it('设备列表加载失败不崩溃（空设备静默路径）', async () => {
    mockApi.get.mockRejectedValue(new Error('network down'));

    const { container } = render(<AnomalyDetection />);
    expect(container).toBeTruthy();
    // 无选中设备 → 检测按钮点击不应发起 post
    await act(async () => {
      fireEvent.click(screen.getByText('检测'));
    });
    expect(mockApi.post).not.toHaveBeenCalled();
  });
});
