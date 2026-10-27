/**
 * 卡 604c1e16: 前端残余大 page_size 手拼点扫尾
 *
 * 背景: DataOps(tenant 200) / Teams-Engineers(200) / WorkOrderStats(500) 手拼超限 page_size,
 * 后端契约均为 Query(ge=1, le=100) → 必 422。三页已改用 fetchAllPages 循环拉全量。
 * 本测试用真实 fetchAllPages + 分页 mock api, 断言:
 *   1) list 调用 page_size 恒为 100(不再出现 200/500)
 *   2) 多页数据真实取尽(250 条 → 3 页)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import React from 'react';

// 构造 total 条数据的分页 mock (page_size=100 切片)
function makePagedFn<T>(total: number, makeItem: (i: number) => T) {
  const all = Array.from({ length: total }, (_, i) => makeItem(i + 1));
  return vi.fn((params: Record<string, unknown>) => {
    const page = Number(params.page);
    const pageSize = Number(params.page_size);
    const items = all.slice((page - 1) * pageSize, page * pageSize);
    return Promise.resolve({ data: { items, total, page, page_size: pageSize } });
  });
}

const tenantListMock = makePagedFn(250, (id) => ({ id, name: `租户${id}`, team_type: 'operations' }));
const engineerListMock = makePagedFn(250, (id) => ({
  id, name: `工程师${id}`, phone: '13800000000', level: 'junior', status: 'active', team_id: 1,
}));
const teamListMock = makePagedFn(3, (id) => ({ id, name: `团队${id}` }));
const workOrderGetMock = vi.fn((url: string, config?: { params?: Record<string, unknown> }) => {
  expect(url).toBe('/work-orders');
  const params = config?.params ?? {};
  const page = Number(params.page);
  const pageSize = Number(params.page_size);
  const all = Array.from({ length: 250 }, (_, i) => ({
    id: `WO-${i + 1}`, fault_desc: '', type: 'fault', level: 'low', status: 'completed',
    station_id: null, device_id: null, assignee_id: null, assignee_name: null, created_at: '2026-01-01',
  }));
  return Promise.resolve({ data: { items: all.slice((page - 1) * pageSize, page * pageSize), total: 250, page, page_size: pageSize } });
});

vi.mock('../../api', () => ({
  default: { get: workOrderGetMock },
  tenantAPI: { list: tenantListMock },
  teamAPI: { list: teamListMock },
  engineerAPI: { list: engineerListMock },
  dataOpsAPI: { export: vi.fn(), backup: vi.fn() },
  forgotPasswordAPI: { requests: vi.fn(() => Promise.resolve({ data: { items: [] } })) },
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

vi.mock('../../components/AutoHeightTable', () => ({
  default: (props: any) => <div data-testid="auto-height-table">{/* antd Table 行渲染走 children 快照 */}{props.dataSource?.length ?? 0}</div>,
}));

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}));

// 仅拦截 ResizeObserver 之类的 jsdom 缺口, 其余 antd 组件用真实实现
beforeEach(() => {
  (globalThis as any).ResizeObserver = (globalThis as any).ResizeObserver
    ?? class { observe() {} unobserve() {} disconnect() {} };
});

function assertAllCallsPageSize100(mock: ReturnType<typeof vi.fn>) {
  const calls = mock.mock.calls as unknown[][];
  expect(calls.length).toBeGreaterThan(0);
  for (const call of calls) {
    expect((call[0] as Record<string, unknown>).page_size).toBe(100);
  }
}

describe('卡 604c1e16: 残余大 page_size 手拼点全部走 fetchAllPages', () => {
  it('DataOps 租户下拉: tenantAPI.list 不再传 200, 250 条按 100/页翻 3 页取尽', async () => {
    const { default: DataOpsPage } = await import('../DataOps');
    render(<DataOpsPage />);
    await waitFor(() => expect(tenantListMock.mock.calls.length).toBe(3));
    assertAllCallsPageSize100(tenantListMock);
    expect((tenantListMock.mock.calls[0][0] as any).page).toBe(1);
    expect((tenantListMock.mock.calls[2][0] as any).page).toBe(3);
  });

  it('Engineers 列表: engineerAPI.list 不再传 200, 250 条按 100/页翻 3 页取尽', async () => {
    const { default: EngineersPage } = await import('../Teams/Engineers');
    render(<EngineersPage />);
    await waitFor(() => {
      expect(engineerListMock.mock.calls.length).toBe(3);
      // 表格客户端分页(每页20行), 断言分页器 total 而非 DOM 行数
      expect(document.body.textContent).toContain('250');
    });
    assertAllCallsPageSize100(engineerListMock);
  });

  it('WorkOrderStats 统计基数: /work-orders 不再传 500, 250 条按 100/页翻 3 页取尽', async () => {
    const { default: WorkOrderStatsPage } = await import('../WorkOrderStats');
    render(<WorkOrderStatsPage />);
    await waitFor(() => {
      expect(workOrderGetMock.mock.calls.length).toBe(3);
      expect(document.body.textContent).toContain('250');
    });
    const calls = workOrderGetMock.mock.calls as [string, { params?: Record<string, unknown> }][];
    for (const [, config] of calls) {
      expect(config?.params?.page_size).toBe(100);
    }
  });
});
