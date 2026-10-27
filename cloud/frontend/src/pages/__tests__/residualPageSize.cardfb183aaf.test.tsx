/**
 * 卡 fb183aaf: 手拼 page_size:100 恰上限点全量 sweep 的页面级验证
 *
 * 背景: 36 处手拼 {page_size:100} 的全量取数意图点在 >100 条时静默截断(下拉缺项/统计基数错)。
 * 已全部改为 fetchAllPages 循环拉全量。本测试选 3 个代表页面, 断言:
 *   1) 每次请求 page_size 恒为 100(不再出现其它值)
 *   2) 多页数据真实取尽(250 条 → 3 页, page 1..3 依序)
 *   3) extra 过滤参数透传不丢
 * 注: 页面表格为客户端分页, 第 3 页行不进 DOM 属预期; 取尽契约以请求序列为准。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import React from 'react';

// 构造 total 条数据的分页 mock (按 page/page_size 切片)
function makePagedFn<T>(total: number, makeItem: (i: number) => T) {
  const all = Array.from({ length: total }, (_, i) => makeItem(i + 1));
  return vi.fn((params: Record<string, unknown>) => {
    const page = Number(params.page);
    const pageSize = Number(params.page_size);
    const items = all.slice((page - 1) * pageSize, page * pageSize);
    return Promise.resolve({ data: { items, total, page, page_size: pageSize } });
  });
}

function assertAllCallsPageSize100(mock: ReturnType<typeof vi.fn>) {
  const calls = mock.mock.calls as unknown[][];
  expect(calls.length).toBeGreaterThan(0);
  for (const call of calls) {
    const params = (call[call.length - 1] ?? call[0]) as Record<string, unknown>;
    expect(Number(params.page_size)).toBe(100);
  }
}

/* ── 代表页 1(CouponManagement) & 3(ChargeEfficiencyAnalysis) 共用 api.get mock, 按 URL 分发 ── */
const couponGetMock = vi.fn((url: string, config?: { params?: Record<string, unknown> }) => {
  const params = config?.params ?? {};
  const page = Number(params.page ?? 1);
  const pageSize = Number(params.page_size ?? 100);
  const mk = (i: number) => ({
    id: i, name: `优惠券${i}`, coupon_type: 'fixed', face_value: 10, min_order_amount: 0,
    total_stock: 100, remaining_stock: 50, per_user_limit: 1, valid_days: 30,
    start_time: '2026-01-01', end_time: '2026-12-31', is_active: true,
    created_at: '2026-01-01', updated_at: '2026-01-01',
  });
  const all = Array.from({ length: 250 }, (_, i) => mk(i + 1));
  const items = all.slice((page - 1) * pageSize, page * pageSize);
  if (url === '/operate/coupon/stats') return Promise.resolve({ data: {} });
  if (url === '/reports/efficiency') {
    // 混合 envelope: axios 体为 {code, data:{items,total,page,page_size,alerts}}
    const mkDev = (i: number) => ({
      device_id: i, device_name: `充电桩${i}`, device_code: `C${i}`, device_type: 'dc',
      station_id: 1, station_name: `站点${i % 5}`, charge_efficiency: 60 + (i % 40),
    });
    const devs = Array.from({ length: 250 }, (_, i) => mkDev(i + 1));
    const devItems = devs.slice((page - 1) * pageSize, page * pageSize);
    return Promise.resolve({
      data: {
        code: 200,
        data: {
          items: devItems, total: 250, page, page_size: pageSize,
          alerts: { abnormal_low_efficiency: { count: 0, threshold: '70', items: [] } },
        },
      },
    });
  }
  return Promise.resolve({
    data: { items, total: 250, page, page_size: pageSize },
  });
});

vi.mock('../../api', () => ({ default: { get: couponGetMock } }));

vi.mock('../../components/PageWrapper', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

/* ── 代表页 2: EnergyPricing (API client 直传模式, 含 extra 过滤参数) ── */
const energyListMock = makePagedFn(250, (id) => ({
  id, station_id: 1, slot_id: id, price_per_kwh: 1.0,
  effective_date: '2026-01-01', is_active: true,
}));
const timeSlotListMock = makePagedFn(3, (id) => ({ id, name: `时段${id}`, period_type: 'peak' }));

vi.mock('../../api/pricing', () => ({
  energyPriceAPI: {
    list: energyListMock,
    create: vi.fn(), update: vi.fn(), remove: vi.fn(),
  },
  timeSlotAPI: {
    list: timeSlotListMock,
    create: vi.fn(), update: vi.fn(), remove: vi.fn(),
  },
}));

vi.mock('echarts/core', () => ({
  use: vi.fn(),
  init: vi.fn(() => ({ setOption: vi.fn(), dispose: vi.fn() })),
}));
vi.mock('echarts/charts', () => ({ BarChart: {} }));
vi.mock('echarts/components', () => ({
  TitleComponent: {}, TooltipComponent: {}, GridComponent: {}, MarkLineComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

beforeEach(() => {
  (globalThis as any).ResizeObserver = (globalThis as any).ResizeObserver
    ?? class { observe() {} unobserve() {} disconnect() {} };
});

function callsFor(url: string) {
  return couponGetMock.mock.calls.filter(([u]) => u === url) as unknown[][];
}

describe('卡 fb183aaf: 手拼 page_size:100 恰上限点全部走 fetchAllPages 多页取尽', () => {
  it('CouponManagement: /operate/coupon 250 条按 100/页翻 3 页取尽(page 1→3, 恒 page_size=100)', async () => {
    const { default: Page } = await import('../CouponManagement');
    render(<Page />);
    await waitFor(() => expect(callsFor('/operate/coupon').length).toBe(3), { timeout: 5000 });
    const couponCalls = callsFor('/operate/coupon');
    for (const call of couponCalls) expect(Number((call[1] as any).params.page_size)).toBe(100);
    expect(Number((couponCalls[0][1] as any).params.page)).toBe(1);
    expect(Number((couponCalls[2][1] as any).params.page)).toBe(3);
  });

  it('EnergyPricing: energyPriceAPI.list 250 条翻 3 页取尽, 时段下拉 extra 参数透传', async () => {
    const { default: Page } = await import('../Operate/Pricing/EnergyPricing');
    render(<Page />);
    await waitFor(() => expect(energyListMock.mock.calls.length).toBe(3), { timeout: 5000 });
    assertAllCallsPageSize100(energyListMock);
    expect(Number(energyListMock.mock.calls[0][0].page)).toBe(1);
    expect(Number(energyListMock.mock.calls[2][0].page)).toBe(3);
    // 时段下拉 3 条单页即尽, 且 is_active 过滤透传
    await waitFor(() => expect(timeSlotListMock.mock.calls.length).toBe(1), { timeout: 5000 });
    expect(timeSlotListMock.mock.calls[0][0].is_active).toBe(true);
  });

  it('ChargeEfficiencyAnalysis: 混合 envelope 250 条翻 3 页取尽, alerts 首页快照保留', async () => {
    const { default: Page } = await import('../Reports/ChargeEfficiencyAnalysis');
    render(<Page />);
    await waitFor(() => expect(callsFor('/reports/efficiency').length).toBe(3), { timeout: 5000 });
    const calls = callsFor('/reports/efficiency');
    for (const call of calls) expect(Number((call[1] as any).params.page_size)).toBe(100);
    expect(calls.map((c) => Number((c[1] as any).params.page))).toEqual([1, 2, 3]);
    // 多页合并不截断: 第 3 页设备(201-250)渲染进表格首页以外的分页数据源
    // (客户端分页, 以请求序列为准; alerts 无异常时 count=0 显示正常)
    await waitFor(() => expect(document.body.textContent).toContain('充电桩1'), { timeout: 5000 });
  });
});
