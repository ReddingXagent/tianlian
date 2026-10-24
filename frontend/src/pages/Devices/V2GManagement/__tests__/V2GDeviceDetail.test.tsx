/**
 * V2G 设备详情页 — Vitest 渲染冒烟测试
 *
 * 口径：真实渲染路径不崩 + 关键交互触发预期 mock 调用（冒烟，不追求行覆盖）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import React from 'react';

const { mockDeviceAPI, mockV2gAPI, mockEfficiencyAPI } = vi.hoisted(() => ({
  mockDeviceAPI: { get: vi.fn() },
  mockV2gAPI: { dispatchHistory: vi.fn(), dispatch: vi.fn() },
  mockEfficiencyAPI: { deviceEfficiency: vi.fn() },
}));

vi.mock('../../../../api', () => ({
  deviceAPI: mockDeviceAPI,
  v2gAPI: mockV2gAPI,
  efficiencyAPI: mockEfficiencyAPI,
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import V2GDeviceDetail from '../V2GDeviceDetail';

const mockDevice = {
  id: 7,
  name: 'V2G-桩-07',
  sn: 'SN-V2G-007',
  type: 'v2g_charger',
  status: 'ONLINE',
  health_score: 92,
  station_id: 1,
  station_name: '一号站',
  current_mode: 'charging',
  charge_power_kw: 45.5,
  discharge_power_kw: 0,
  rated_power_kw: 150,
  charge_efficiency: 93.2,
  discharge_efficiency: 91.1,
  conversion_efficiency: 88.4,
};

const renderDetail = () =>
  render(
    <BrowserRouter>
      <Routes>
        <Route path="/devices/v2g/:id" element={<V2GDeviceDetail />} />
      </Routes>
    </BrowserRouter>,
    { wrapper: undefined },
  );

// 直接用 window.history 压入目标路由再渲染
const renderAtRoute = () => {
  window.history.pushState({}, '', '/devices/v2g/7');
  return renderDetail();
};

beforeEach(() => {
  vi.clearAllMocks();
  mockDeviceAPI.get.mockResolvedValue({ data: mockDevice });
  mockV2gAPI.dispatchHistory.mockResolvedValue({ data: { items: [] } });
  mockEfficiencyAPI.deviceEfficiency.mockResolvedValue({ data: {} });
});

describe('V2G设备详情 — 渲染冒烟', () => {
  it('正常数据渲染设备信息与调度控制面板', async () => {
    renderAtRoute();

    expect(await screen.findByText(/V2G-桩-07/)).toBeInTheDocument();
    expect(screen.getByText('SN-V2G-007')).toBeInTheDocument();
    expect(screen.getByText('在线')).toBeInTheDocument();
    expect(screen.getByText('V2G调度控制')).toBeInTheDocument();
    expect(screen.getByText('下发调度指令')).toBeInTheDocument();
    expect(mockDeviceAPI.get).toHaveBeenCalledWith(7);
    expect(mockV2gAPI.dispatchHistory).toHaveBeenCalledWith(7);
  });

  it('设备加载失败不崩溃（空数据兜底路径）', async () => {
    mockDeviceAPI.get.mockRejectedValue(new Error('network down'));
    renderAtRoute();

    await waitFor(() => {
      expect(screen.getByText(/设备详情 - 加载中/)).toBeInTheDocument();
    });
  });

  it('点击下发调度指令调用 v2gAPI.dispatch 并刷新数据', async () => {
    mockV2gAPI.dispatch.mockResolvedValue({});
    renderAtRoute();
    await screen.findByText(/V2G-桩-07/);

    await act(async () => {
      fireEvent.click(screen.getByText('下发调度指令'));
    });

    await waitFor(() => {
      expect(mockV2gAPI.dispatch).toHaveBeenCalledWith(7, {
        dispatch_type: 'standby',
        target_power_kw: 30,
      });
    });
    // 成功后刷新设备与历史
    await waitFor(() => {
      expect(mockDeviceAPI.get.mock.calls.length).toBeGreaterThanOrEqual(2);
      expect(mockV2gAPI.dispatchHistory.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('调度历史空数据显示空态文案', async () => {
    renderAtRoute();
    expect(await screen.findByText('暂无调度记录')).toBeInTheDocument();
  });
});
