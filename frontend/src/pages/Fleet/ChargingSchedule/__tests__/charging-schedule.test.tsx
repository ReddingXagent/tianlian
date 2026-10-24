/**
 * 智能充电调度 — Vitest 单元测试
 *
 * 覆盖：列表页渲染/筛选、生成计划Modal、甘特图组件、动态调整面板
 * 对接后端 Phase45: /api/v1/fleet/charging/schedule/*
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';
import type { ScheduleEntry } from '../types';

// ═══════════════════════════════════════════
// Mock API
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

vi.mock('../../../../api', () => ({ default: mockApi }));

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

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockEntries: ScheduleEntry[] = [
  { id: 11, plan_id: 1, vehicle_id: 101, assigned_power_kw: 7, start_time: '2026-07-22T00:00:00', end_time: '2026-07-22T06:00:00', priority: 1, soc_start: 0.3, soc_target: 0.9, charge_mode: 'charge', period_type: 'valley' },
  { id: 12, plan_id: 1, vehicle_id: 102, assigned_power_kw: 3, start_time: '2026-07-22T14:00:00', end_time: '2026-07-22T16:00:00', priority: 2, soc_start: 0.5, soc_target: 0.8, charge_mode: 'discharge', period_type: 'peak' },
  { id: 13, plan_id: 1, vehicle_id: 103, assigned_power_kw: 0, start_time: '2026-07-22T08:00:00', end_time: '2026-07-22T10:00:00', priority: 3, soc_start: 0.6, soc_target: 0.6, charge_mode: 'idle', period_type: 'flat' },
];

const mockPlans = [
  { id: 1, enterprise_id: 1, plan_date: '2026-07-22T00:00:00', time_window_start: '2026-07-22T00:00:00', time_window_end: '2026-07-22T23:59:00', total_available_power_kw: 100, status: 'planned', rule_json: null, created_at: null, updated_at: null },
  { id: 2, enterprise_id: 1, plan_date: '2026-07-21T00:00:00', time_window_start: '2026-07-21T00:00:00', time_window_end: '2026-07-21T23:59:00', total_available_power_kw: 80, status: 'active', rule_json: null, created_at: null, updated_at: null },
];

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/current')) return Promise.resolve({ data: { plan: mockPlans[0], entries: mockEntries } });
    if (/\/schedule\/\d+/.test(url)) return Promise.resolve({ data: { plan: mockPlans[0], entries: mockEntries } });
    if (url.includes('/schedule')) return Promise.resolve({ data: { items: mockPlans, total: mockPlans.length, page: 1, page_size: 10 } });
    return Promise.resolve({ data: [] });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: { plan_id: 1, status: 'planned', entries: mockEntries } });
});

// ═══════════════════════════════════════════
// 列表页
// ═══════════════════════════════════════════
describe('智能充电调度 — 列表页', () => {
  it('渲染表格列头（计划日期/企业/车辆数/总功率/时间窗口/状态/操作）', async () => {
    const { default: FleetChargingSchedulePage } = await import('../index');
    renderWithRouter(<FleetChargingSchedulePage />);
    await waitFor(() => {
      expect(screen.getByText('计划日期')).toBeInTheDocument();
      expect(screen.getByText('车辆数')).toBeInTheDocument();
      expect(screen.getByText('总功率')).toBeInTheDocument();
      expect(screen.getByText('时间窗口')).toBeInTheDocument();
    }, { timeout: 8000 });
  }, 15000);

  it('首次加载调用 GET /fleet/charging/schedule', async () => {
    const { default: FleetChargingSchedulePage } = await import('../index');
    renderWithRouter(<FleetChargingSchedulePage />);
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/fleet/charging/schedule', expect.objectContaining({
        params: expect.objectContaining({ enterprise_id: 1 }),
      }));
    }, { timeout: 8000 });
  }, 15000);

  it('状态筛选切换到"已完成"后带 status=completed 重新请求', async () => {
    const { default: FleetChargingSchedulePage } = await import('../index');
    renderWithRouter(<FleetChargingSchedulePage />);
    await waitFor(() => expect(screen.getByText('计划日期')).toBeInTheDocument(), { timeout: 8000 });
    const filter = screen.getByTestId('status-filter');
    const completed = [...filter.querySelectorAll('label')].find(el => el.textContent === '已完成') as HTMLElement;
    expect(completed).toBeTruthy();
    fireEvent.click(completed);
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/fleet/charging/schedule', expect.objectContaining({
        params: expect.objectContaining({ status: 'completed' }),
      }));
    }, { timeout: 8000 });
  }, 15000);

  it('点击"新建调度计划"打开生成表单', async () => {
    const { default: FleetChargingSchedulePage } = await import('../index');
    renderWithRouter(<FleetChargingSchedulePage />);
    await waitFor(() => expect(screen.getByText('计划日期')).toBeInTheDocument(), { timeout: 8000 });
    fireEvent.click(screen.getByText('新建调度计划'));
    await waitFor(() => {
      expect(screen.getByText('可用总功率', { exact: false })).toBeInTheDocument();
      expect(screen.getByText('参与车辆')).toBeInTheDocument();
    }, { timeout: 8000 });
  }, 15000);

  it('提交生成表单调用 POST /generate 且 payload 含 vehicle_states/功率/时间窗', async () => {
    const { default: GeneratePlanModal } = await import('../GeneratePlanModal');
    renderWithRouter(<GeneratePlanModal open={true} enterpriseId={1} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('可用总功率', { exact: false })).toBeInTheDocument(), { timeout: 8000 });
    // 默认表单已含2辆启用车辆 + 默认功率/时间窗，直接提交
    // (zhCN locale 对2字按钮自动加字间距, 渲染为"确 定", 用正则容忍)
    const okBtn = await screen.findByRole('button', { name: /确\s*定/ });
    fireEvent.click(okBtn);
    await waitFor(() => {
      const call = mockApi.post.mock.calls.find(c => typeof c[0] === 'string' && c[0].includes('/schedule/generate'));
      expect(call).toBeTruthy();
      const body = call![1];
      expect(Array.isArray(body.vehicle_states)).toBe(true);
      expect(body.vehicle_states.length).toBeGreaterThan(0);
      expect(body.available_power_kw).toBe(100);
      expect(body.time_window_start).toBeTruthy();
      expect(body.time_window_end).toBeTruthy();
    }, { timeout: 8000 });
  }, 15000);
});

// ═══════════════════════════════════════════
// 甘特图组件
// ═══════════════════════════════════════════
describe('智能充电调度 — 甘特图组件', () => {
  it('渲染车辆行(纵轴)与充电时段色块', async () => {
    const { default: ScheduleGantt } = await import('../ScheduleGantt');
    renderWithRouter(<ScheduleGantt entries={mockEntries} availablePowerKw={100} />);
    expect(screen.getByTestId('schedule-gantt')).toBeInTheDocument();
    expect(screen.getByText('车辆 101')).toBeInTheDocument();
    expect(screen.getByText('车辆 102')).toBeInTheDocument();
    // 色块(充电/放电/待机)
    const blocks = screen.getAllByTestId('gantt-block');
    expect(blocks.length).toBeGreaterThanOrEqual(3);
  }, 15000);

  it('渲染尖峰平谷时段图例', async () => {
    const { default: ScheduleGantt } = await import('../ScheduleGantt');
    renderWithRouter(<ScheduleGantt entries={mockEntries} availablePowerKw={100} />);
    expect(screen.getByText('谷')).toBeInTheDocument();
    expect(screen.getByText('平')).toBeInTheDocument();
    expect(screen.getByText('峰')).toBeInTheDocument();
    expect(screen.getByText('尖')).toBeInTheDocument();
  }, 15000);
});

// ═══════════════════════════════════════════
// 动态调整面板
// ═══════════════════════════════════════════
describe('智能充电调度 — 动态调整面板', () => {
  it('打开后加载详情，提交调整调用 PATCH /adjust 且带 new_distribution', async () => {
    const { default: AdjustPanel } = await import('../AdjustPanel');
    renderWithRouter(<AdjustPanel open={true} plan={mockPlans[0] as any} onClose={vi.fn()} onSuccess={vi.fn()} />);
    // 等待详情条目加载
    await waitFor(() => {
      expect(screen.getByText('提交调整')).toBeInTheDocument();
    }, { timeout: 8000 });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith(expect.stringMatching(/\/schedule\/1$/));
    }, { timeout: 8000 });
    fireEvent.click(screen.getByText('提交调整'));
    await waitFor(() => {
      const call = mockApi.patch.mock.calls.find(c => typeof c[0] === 'string' && c[0].includes('/schedule/1/adjust'));
      expect(call).toBeTruthy();
      const body = call![1];
      expect(Array.isArray(body.new_distribution)).toBe(true);
      expect(body.new_distribution.length).toBeGreaterThan(0);
      expect(body.new_distribution[0]).toHaveProperty('entry_id');
      expect(body.new_distribution[0]).toHaveProperty('new_power_kw');
    }, { timeout: 8000 });
  }, 15000);
});
