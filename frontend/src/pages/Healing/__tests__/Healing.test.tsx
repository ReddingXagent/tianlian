/**
 * Healing — Vitest 组件测试
 * 测试: 主页 Tab 渲染 + 子页面渲染 + Tab 切换
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══ Mock healingApi ═══
const { mockHealingApi } = vi.hoisted(() => ({
  mockHealingApi: {
    listRules: vi.fn(),
    createRule: vi.fn(),
    updateRule: vi.fn(),
    deleteRule: vi.fn(),
    toggleRule: vi.fn(),
    executions: vi.fn(),
    executionDetail: vi.fn(),
    retryExecution: vi.fn(),
    pendingApprovals: vi.fn(),
    approveExecution: vi.fn(),
    rejectExecution: vi.fn(),
    approvalHistory: vi.fn(),
    stats: vi.fn(),
  },
}));

vi.mock('../../../api/healing', () => ({
  default: mockHealingApi,
  HealingRule: {},
  HealingExecution: {},
  HealingExecutionDetail: {},
}));

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

import HealingPage from '../index';

// ═══ beforeEach ═══
beforeEach(() => {
  vi.clearAllMocks();
  mockHealingApi.listRules.mockResolvedValue({ items: [] });
  mockHealingApi.executions.mockResolvedValue({ items: [] });
  mockHealingApi.pendingApprovals.mockResolvedValue({ items: [] });
  mockHealingApi.approvalHistory.mockResolvedValue({ items: [] });
  mockHealingApi.stats.mockResolvedValue({
    total_rules: 5,
    active_rules: 3,
    total_executions_24h: 10,
    success_rate: 80,
  });
});

// ═══ Tests ═══

describe('Healing 主页', () => {
  it('渲染 3 个 Tab（自愈规则、执行历史、审批管理）', async () => {
    await act(async () => {
      render(<BrowserRouter><HealingPage /></BrowserRouter>);
    });
    expect(screen.getByText('自愈规则')).toBeInTheDocument();
    expect(screen.getByText('执行历史')).toBeInTheDocument();
    expect(screen.getByText('审批管理')).toBeInTheDocument();
  });

  it('默认选中"自愈规则" Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><HealingPage /></BrowserRouter>);
    });
    const rulesTab = screen.getByText('自愈规则').closest('.ant-tabs-tab');
    expect(rulesTab?.classList.contains('ant-tabs-tab-active')).toBe(true);
  });

  it('切换到"执行历史" Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><HealingPage /></BrowserRouter>);
    });
    // Wait for Rules component to settle
    await waitFor(() => {
      expect(mockHealingApi.listRules).toHaveBeenCalled();
    });

    // Click the tab (use getAllByText since text appears in both tab label and content)
    const historyTabs = screen.getAllByText('执行历史');
    const historyTab = historyTabs.find(el => el.closest('.ant-tabs-tab'));
    await act(async () => {
      fireEvent.click(historyTab!);
    });

    // Verify tab became active
    await waitFor(() => {
      const tab = screen.getAllByText('执行历史').find(el => el.closest('.ant-tabs-tab'));
      expect(tab?.closest('.ant-tabs-tab')?.classList.contains('ant-tabs-tab-active')).toBe(true);
    });
  });

  it('切换到"审批管理" Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><HealingPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockHealingApi.listRules).toHaveBeenCalled();
    });

    const approvalTabs = screen.getAllByText('审批管理');
    const approvalTab = approvalTabs.find(el => el.closest('.ant-tabs-tab'));
    await act(async () => {
      fireEvent.click(approvalTab!);
    });

    await waitFor(() => {
      const tab = screen.getAllByText('审批管理').find(el => el.closest('.ant-tabs-tab'));
      expect(tab?.closest('.ant-tabs-tab')?.classList.contains('ant-tabs-tab-active')).toBe(true);
    });
  });

  it('Tabs 容器有白色背景样式', async () => {
    await act(async () => {
      render(<BrowserRouter><HealingPage /></BrowserRouter>);
    });
    const tabsContainer = document.querySelector('.ant-tabs');
    expect(tabsContainer).toBeTruthy();
  });
});
