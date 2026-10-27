/**
 * 值班排班管理页面 — Vitest 单元测试
 *
 * 覆盖：渲染、Tab切换(值班规则/排班表/当前值班/值班日志/统计报表)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API
// ═══════════════════════════════════════════
const { mockOnCallAPI, mockTeamAPI } = vi.hoisted(() => ({
  mockOnCallAPI: {
    rules: {
      list: vi.fn(() => Promise.resolve({ data: { rules: [] } })),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      generateShifts: vi.fn(),
    },
    shifts: {
      list: vi.fn(() => Promise.resolve({ data: { items: [] } })),
      updateStatus: vi.fn(),
      getCurrent: vi.fn(() => Promise.resolve({ data: { current_shifts: [] } })),
    },
    logs: {
      list: vi.fn(() => Promise.resolve({ data: { items: [] } })),
      create: vi.fn(),
    },
    stats: {
      getStats: vi.fn(() => Promise.resolve({
        data: {
          shifts: { total: 10, completed: 8, missed: 1, completion_rate: 80 },
          handover: { completed: 7, rate: 87.5 },
          logs: { total: 5, by_event_type: { note: 3, alarm: 2 } },
          by_user: [],
        },
      })),
    },
  },
  mockTeamAPI: {
    list: vi.fn(() => Promise.resolve({ data: { items: [] } })),
  },
}));

vi.mock('../../../api', () => ({
  default: {},
  onCallAPI: mockOnCallAPI,
  teamAPI: mockTeamAPI,
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

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

import OnCallPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & Tab
// ═══════════════════════════════════════════
describe('值班排班 — 渲染 & Tab', () => {
  it('页面正常渲染，显示值班规则Tab', async () => {
    renderWithRouter(<OnCallPage />);
    await waitFor(() => {
      expect(screen.getByText('值班规则')).toBeInTheDocument();
    });
  });

  it('显示所有Tab标签', async () => {
    renderWithRouter(<OnCallPage />);
    await waitFor(() => {
      // Tabs are rendered with icons + text
      const allTabs = document.querySelectorAll('.ant-tabs-tab');
      expect(allTabs.length).toBeGreaterThanOrEqual(5);
    });
  });

  it('值班规则Tab显示新增规则按钮', async () => {
    renderWithRouter(<OnCallPage />);
    await waitFor(() => {
      expect(screen.getByText('新增规则')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// Tab 切换
// ═══════════════════════════════════════════
describe('值班排班 — Tab切换', () => {
  it('切换到当前值班Tab', async () => {
    renderWithRouter(<OnCallPage />);
    await waitFor(() => expect(screen.getByText('值班规则')).toBeInTheDocument());

    clickTab('当前值班');

    await waitFor(() => {
      expect(screen.getByText('当前值班人员')).toBeInTheDocument();
    });
  });

  it('切换到值班日志Tab', async () => {
    renderWithRouter(<OnCallPage />);
    await waitFor(() => expect(screen.getByText('值班规则')).toBeInTheDocument());

    clickTab('值班日志');

    await waitFor(() => {
      expect(screen.getByText('新增日志')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 移动端响应式布局（Phase1）
// ═══════════════════════════════════════════
describe('值班排班 — 移动端响应式布局', () => {
  it('统计报表概览卡片采用响应式 Col（移动端2列）', async () => {
    renderWithRouter(<OnCallPage />);
    await waitFor(() => expect(screen.getByText('值班规则')).toBeInTheDocument());

    clickTab('统计报表');

    await waitFor(() => {
      expect(screen.getByText('值班统计报表')).toBeInTheDocument();
    });
    // Col 由固定 span={6} 改为 xs={12} sm={6}，移动端纵向2列
    expect(document.querySelector('.ant-col-xs-12')).toBeInTheDocument();
  });

  it('当前值班卡片采用响应式 Col（移动端1列）', async () => {
    // 提供非空值班数据以触发卡片渲染分支
    mockOnCallAPI.shifts.getCurrent.mockResolvedValue({ data: { current_shifts: [
      { shift_id: 1, rule_name: '一线轮值', primary: { name: '张三' }, backup: null, remaining_hours: 4, handover_completed: false },
    ] } });

    renderWithRouter(<OnCallPage />);
    await waitFor(() => expect(screen.getByText('值班规则')).toBeInTheDocument());

    clickTab('当前值班');

    await waitFor(() => {
      expect(screen.getByText('当前值班人员')).toBeInTheDocument();
    });
    // 有数据时 CurrentTab 渲染值班卡片，Col 由固定 span={8} 改为 xs={24} sm={12} md={8}
    await waitFor(() => {
      expect(document.querySelector('.ant-col-xs-24')).toBeInTheDocument();
    });
  });
});
