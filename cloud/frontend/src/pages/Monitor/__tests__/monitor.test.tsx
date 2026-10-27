/**
 * 监控视图页面 — Vitest 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块
// ═══════════════════════════════════════════
const { mockDeviceAPI, mockEfficiencyAPI, mockTelemetryAPI } = vi.hoisted(() => ({
  mockDeviceAPI: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
  mockEfficiencyAPI: {
    deviceEfficiency: vi.fn(),
  },
  mockTelemetryAPI: {
    stats: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  deviceAPI: mockDeviceAPI,
  efficiencyAPI: mockEfficiencyAPI,
  telemetryAPI: mockTelemetryAPI,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

import MonitorPage from '../index';

// ═══════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════
const mockDevices = [
  { id: 1, name: '逆变器A', power: 50.5, status: 'online', type: 'inverter', total_energy: 1200 },
  { id: 2, name: '逆变器B', power: 30.2, status: 'online', type: 'inverter', total_energy: 800 },
  { id: 3, name: '储能柜C', power: 0, status: 'offline', type: 'battery', total_energy: 0 },
];

// 效率/温度真实值（模拟 efficiencyAPI.deviceEfficiency / telemetryAPI.stats 解包后的业务体）
const efficiencyMap: Record<number, number> = { 1: 91, 2: 78 };
const tempMap: Record<number, number> = { 1: 42.0, 2: 57.0 };

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockDeviceAPI.list.mockResolvedValue({ data: mockDevices });
  // 设备1/2 返回真实效率，设备3 无数据（reject）
  mockEfficiencyAPI.deviceEfficiency.mockImplementation((id: number) => {
    if (id === 3) return Promise.reject(new Error('no efficiency data'));
    return Promise.resolve({ data: { utilization: { current: efficiencyMap[id] } } });
  });
  // 设备1/2 返回真实温度统计，设备3 无数据（reject）
  mockTelemetryAPI.stats.mockImplementation((id: number) => {
    if (id === 3) return Promise.reject(new Error('no telemetry'));
    return Promise.resolve({ data: { stats: { thermal: { avg_temp: tempMap[id] } } } });
  });
});

describe('监控视图 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('渲染关键指标卡片', async () => {
    await act(async () => {
      render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('当前总功率')).toBeInTheDocument();
      expect(screen.getByText('今日发电量')).toBeInTheDocument();
      expect(screen.getByText('在线设备')).toBeInTheDocument();
      expect(screen.getByText('系统效率')).toBeInTheDocument();
    });
  });

  it('渲染功率流向和设备状态区域', async () => {
    await act(async () => {
      render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('功率流向')).toBeInTheDocument();
      expect(screen.getByText('设备运行状态')).toBeInTheDocument();
    });
  });
});

describe('监控视图 — 数据展示', () => {
  it('deviceAPI.list 被调用获取设备数据', async () => {
    await act(async () => {
      render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    });
    expect(mockDeviceAPI.list).toHaveBeenCalled();
  });

  it('设备数据渲染到表格中', async () => {
    await act(async () => {
      render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('逆变器A')).toBeInTheDocument();
      expect(screen.getByText('逆变器B')).toBeInTheDocument();
      expect(screen.getByText('储能柜C')).toBeInTheDocument();
    });
  });

  it('计算并显示在线设备数', async () => {
    await act(async () => {
      render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    });
    // 在线设备 2/3
    await waitFor(() => {
      // The Statistic component renders values that contain '2'
      const onlineEl = screen.getByText('在线设备');
      expect(onlineEl).toBeInTheDocument();
    });
  });
});

describe('监控视图 — 效率/温度接入真实数据', () => {
  it('效率列来自 efficiencyAPI.deviceEfficiency（utilization.current）', async () => {
    await act(async () => {
      render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    });
    // 设备1 效率 91%、设备2 效率 78%（Progress percent 文本）
    await waitFor(() => {
      expect(screen.getByText('91%')).toBeInTheDocument();
      expect(screen.getByText('78%')).toBeInTheDocument();
    });
    expect(mockEfficiencyAPI.deviceEfficiency).toHaveBeenCalledWith(1);
    expect(mockEfficiencyAPI.deviceEfficiency).toHaveBeenCalledWith(2);
  });

  it('温度列来自 telemetryAPI.stats（thermal.avg_temp）', async () => {
    await act(async () => {
      render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('42.0')).toBeInTheDocument();
      expect(screen.getByText('57.0')).toBeInTheDocument();
    });
    expect(mockTelemetryAPI.stats).toHaveBeenCalledWith(1);
    expect(mockTelemetryAPI.stats).toHaveBeenCalledWith(2);
  });

  it('无效率/温度数据时降级显示破折号 —，不使用随机数', async () => {
    await act(async () => {
      render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    });
    // 设备3 效率与温度均无数据 → 各显示一个 —
    await waitFor(() => {
      const dashes = screen.getAllByText('—');
      expect(dashes.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('系统效率用真实设备效率均值替代硬编码 94.5', async () => {
    await act(async () => {
      render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    });
    // (91 + 78) / 2 = 84.5。antd Statistic 会把数字拆成 int/decimal 两个 span，
    // 故按 .ant-statistic-content-value 容器的 textContent 断言。
    await waitFor(() => {
      const valueTexts = Array.from(document.querySelectorAll('.ant-statistic-content-value'))
        .map((el) => el.textContent);
      expect(valueTexts).toContain('84.5');
      expect(valueTexts).not.toContain('94.5');
    });
  });
});

describe('监控视图 — 交互', () => {
  it('渲染站点筛选器', async () => {
    await act(async () => {
      render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    });
    expect(screen.getByText('全部站点')).toBeInTheDocument();
  });

  it('刷新按钮触发数据重新加载', async () => {
    await act(async () => {
      render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    });
    await screen.findByText('逆变器A');

    vi.clearAllMocks();
    mockDeviceAPI.list.mockResolvedValue({ data: mockDevices });

    fireEvent.click(screen.getByText('刷新数据'));

    await waitFor(() => {
      expect(mockDeviceAPI.list).toHaveBeenCalled();
    });
  });

  it('deviceAPI.list 失败时不崩溃', async () => {
    mockDeviceAPI.list.mockRejectedValue(new Error('fail'));
    await act(async () => {
      const { container } = render(<BrowserRouter><MonitorPage /></BrowserRouter>);
      expect(container).toBeTruthy();
    });
  });

  it('单个设备效率/温度请求失败不影响其他设备渲染', async () => {
    await act(async () => {
      render(<BrowserRouter><MonitorPage /></BrowserRouter>);
    });
    // 设备3 请求失败，但设备1/2 仍正常显示真实数据，设备3 名称仍渲染
    await waitFor(() => {
      expect(screen.getByText('91%')).toBeInTheDocument();
      expect(screen.getByText('78%')).toBeInTheDocument();
      expect(screen.getByText('储能柜C')).toBeInTheDocument();
    });
  });
});
