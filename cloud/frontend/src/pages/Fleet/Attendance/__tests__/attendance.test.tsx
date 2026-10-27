/**
 * 司机考勤/工时页面 — Vitest 单元测试
 *
 * 覆盖：渲染、汇总卡片、考勤列表、班次/状态标签、批量录入Modal
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

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

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockDrivers = [
  { id: 1, name: '张三', phone: '13800138001' },
  { id: 2, name: '李四', phone: '13900139002' },
];

const mockRows = [
  { id: 1, driver_id: 1, date: '2026-07-01', shift_type: 'day', hours: 8, status: 'normal', remark: '正常出车' },
  { id: 2, driver_id: 1, date: '2026-07-02', shift_type: 'night', hours: 7, status: 'late', remark: '晚到30分钟' },
  { id: 3, driver_id: 1, date: '2026-07-03', shift_type: 'rest', hours: 0, status: 'absent', remark: '请假' },
];

const mockSummary = {
  total_days: 3, total_hours: 15,
  normal_days: 1, late_days: 1, absent_days: 1, rest_days: 1,
  attendance_rate: 0.95,
};

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/fleet/drivers')) return Promise.resolve({ data: mockDrivers });
    if (url.includes('/fleet/attendance/summary')) return Promise.resolve({ data: mockSummary });
    if (url.includes('/fleet/attendance')) return Promise.resolve({ data: mockRows });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

import FleetAttendancePage from '../index';

// ═══════════════════════════════════════════
// 渲染 & 汇总
// ═══════════════════════════════════════════
describe('司机考勤 — 渲染', () => {
  it('页面正常渲染不崩溃', () => {
    const { container } = renderWithRouter(<FleetAttendancePage />);
    expect(container).toBeTruthy();
  }, 15000);

  it('显示四张汇总卡片', async () => {
    renderWithRouter(<FleetAttendancePage />);
    await waitFor(() => {
      expect(screen.getByText('出勤率')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getByText('总工时(h)')).toBeInTheDocument();
    expect(screen.getByText('日均工时(h)')).toBeInTheDocument();
    expect(screen.getByText('记录天数')).toBeInTheDocument();
  }, 15000);

  it('渲染考勤列表(班次+状态标签)', async () => {
    renderWithRouter(<FleetAttendancePage />);
    await waitFor(() => {
      expect(screen.getByText('2026-07-01')).toBeInTheDocument();
      expect(screen.getByText('2026-07-02')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getAllByText('白班').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('夜班')).toBeInTheDocument();
    expect(screen.getAllByText('正常').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('迟到')).toBeInTheDocument();
  }, 15000);
});

// ═══════════════════════════════════════════
// 批量录入 Modal
// ═══════════════════════════════════════════
describe('司机考勤 — 批量录入', () => {
  it('点击批量录入打开Modal', async () => {
    renderWithRouter(<FleetAttendancePage />);
    await waitFor(() => expect(screen.getByText('2026-07-01')).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.click(screen.getByText('批量录入'));

    await waitFor(() => {
      expect(screen.getByText('批量录入考勤')).toBeInTheDocument();
      expect(screen.getByText('日期范围')).toBeInTheDocument();
    });
  }, 15000);
});
