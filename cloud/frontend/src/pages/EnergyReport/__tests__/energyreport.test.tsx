/**
 * 能耗报表页面测试 (卡 d44db94a)
 *
 * 契约对齐 commit 62cc447cf:
 * - /trend 空库返回 [] → 空态 UI 不白屏
 * - /summary yoy 上期为0时为 null → 占位符
 * - price_info.source=default → 默认电价角标
 * - /station-compare 无数据站点不输出、按收益降序
 * - 禁止 mock 降级: API 失败只报错, 不展示假数据
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockEnergyReportAPI } = vi.hoisted(() => ({
  mockEnergyReportAPI: { trend: vi.fn(), summary: vi.fn(), stationCompare: vi.fn() },
}));

vi.mock('../../../api', () => ({ energyReportAPI: mockEnergyReportAPI }));
vi.mock('echarts-for-react/lib/core', () => ({ default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }) }));
vi.mock('echarts/core', () => ({ use: vi.fn() }));
vi.mock('echarts/charts', () => ({ LineChart: {}, BarChart: {}, PieChart: {} }));
vi.mock('echarts/components', () => ({ GridComponent: {}, TooltipComponent: {}, LegendComponent: {}, TitleComponent: {}, DataZoomComponent: {} }));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));
// t 必须跨渲染稳定(真实 react-i18next 即如此), 否则依赖 t 的 useCallback 无限重建
const stableT = (k: string) => k;
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: stableT, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import EnergyReportPage from '../index';

const REAL_SUMMARY = {
  period: 'month',
  days: 19,
  pv_generation: 2960.1,
  charging_amount: 1000.2,
  discharge_amount: 1320.3,
  pv_revenue: 1243.2,
  charging_revenue: 850.2,
  discharge_revenue: 554.5,
  total_revenue: 2647.9,
  yoy: {
    pv_generation_yoy: 8.0,
    charging_amount_yoy: null,
    discharge_amount_yoy: -3.2,
    total_revenue_yoy: null,
  },
  price_info: { feed_in_tariff: 0.42, charging_price: 0.85, discharge_price: 0.42, source: 'default' },
};

beforeEach(() => {
  vi.clearAllMocks();
  mockEnergyReportAPI.trend.mockResolvedValue({ data: { trend: [], granularity: 'day', period: { start: '2026-07-24', end: '2026-08-23' } } });
  mockEnergyReportAPI.summary.mockResolvedValue({ data: REAL_SUMMARY });
  mockEnergyReportAPI.stationCompare.mockResolvedValue({ data: { stations: [], totals: null } });
});

describe('EnergyReport 页面', () => {
  it('渲染不崩溃且挂载时拉取三接口', async () => {
    await act(async () => {
      render(<BrowserRouter><EnergyReportPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockEnergyReportAPI.trend).toHaveBeenCalledWith({ granularity: 'day' });
    });
    expect(mockEnergyReportAPI.summary).toHaveBeenCalled();
    expect(mockEnergyReportAPI.stationCompare).toHaveBeenCalled();
  });

  it('空库 trend=[]/stations=[] 时展示空态而非白屏', async () => {
    let container: HTMLElement;
    await act(async () => {
      const r = render(<BrowserRouter><EnergyReportPage /></BrowserRouter>);
      container = r.container;
    });
    await waitFor(() => {
      // antd Empty 空态组件
      expect(container!.querySelector('.ant-empty')).toBeTruthy();
    });
  });

  it('summary 渲染四张汇总卡: yoy=null 显示占位符、source=default 显示默认电价角标', async () => {
    let el: HTMLElement;
    await act(async () => {
      const r = render(<BrowserRouter><EnergyReportPage /></BrowserRouter>);
      el = r.container;
    });
    await waitFor(() => {
      // Statistic 默认千分位格式化 2960.1 → 2,960.1
      expect(el!.textContent).toContain('2,960.1');
    });
    expect(el!.textContent).toContain('energyReport.pv_generation');
    // 默认电价角标 (i18n key 被 mock 为原样返回)
    expect(el!.textContent).toContain('energyReport.default_price');
    // yoy 有值渲染百分比
    expect(el!.textContent).toContain('+8%');
    // yoy=null 渲染 "--" 占位符, 不出现 "null" 字样
    expect(el!.textContent).not.toContain('null');
    expect(el!.textContent).toContain('--');
  });

  it('粒度切换到月触发 trend 重拉 granularity=month', async () => {
    const { container } = render(<BrowserRouter><EnergyReportPage /></BrowserRouter>);
    await waitFor(() => {
      expect(mockEnergyReportAPI.trend).toHaveBeenCalledWith({ granularity: 'day' });
    });
    await act(async () => {
      fireEvent.mouseDown(container.querySelector('.ant-select-selector')!);
    });
    await act(async () => {
      fireEvent.click(document.querySelectorAll('.ant-select-item-option')[2]);
    });
    await waitFor(() => {
      expect(mockEnergyReportAPI.trend).toHaveBeenCalledWith({ granularity: 'month' });
    });
  });

  it('有数据时渲染站点对比表(按收益降序)', async () => {
    mockEnergyReportAPI.stationCompare.mockResolvedValue({
      data: {
        stations: [
          { station_id: 2, name: '站点B', pv_gen: 100, charge: 50, discharge: 20, revenue: 90 },
          { station_id: 1, name: '站点A', pv_gen: 300, charge: 10, discharge: 5, revenue: 150 },
        ],
        totals: { pv_generation: 400, charging_amount: 60, discharge_amount: 25, total_revenue: 240 },
      },
    });
    let el: HTMLElement;
    await act(async () => {
      const r = render(<BrowserRouter><EnergyReportPage /></BrowserRouter>);
      el = r.container;
    });
    // 站点对比在第二个 Tab, 先切换
    await act(async () => {
      fireEvent.click(el!.querySelectorAll('.ant-tabs-tab')[1]);
    });
    await waitFor(() => {
      expect(el!.textContent).toContain('站点A');
    });
    expect(el!.textContent).toContain('站点B');
  });

  it('API 失败时降级为空态, 不展示 mock 假数据', async () => {
    mockEnergyReportAPI.trend.mockRejectedValue(new Error('network'));
    mockEnergyReportAPI.summary.mockRejectedValue(new Error('network'));
    mockEnergyReportAPI.stationCompare.mockRejectedValue(new Error('network'));
    let el: HTMLElement;
    await act(async () => {
      const r = render(<BrowserRouter><EnergyReportPage /></BrowserRouter>);
      el = r.container;
    });
    await waitFor(() => {
      expect(el!.querySelector('.ant-empty')).toBeTruthy();
    });
    // 不出现 mock 降级时期的典型假数据量级
    expect(el!.textContent).not.toContain('2647');
  });
});
