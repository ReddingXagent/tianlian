import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockRunbookApi } = vi.hoisted(() => ({
  mockRunbookApi: {
    listTemplates: vi.fn(),
    listExecutions: vi.fn(),
    getStats: vi.fn(),
    execute: vi.fn(),
    getExecutionDetail: vi.fn(),
  },
}));

vi.mock('../../../api/runbook', () => ({ default: mockRunbookApi }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import RunbookPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockRunbookApi.listTemplates.mockResolvedValue({ data: { data: { items: [], total: 0 } } });
  mockRunbookApi.listExecutions.mockResolvedValue({ data: { data: { items: [], total: 0 } } });
  mockRunbookApi.getStats.mockResolvedValue({ data: { data: { total: 0, completed: 0, failed: 0, running: 0 } } });
  mockRunbookApi.getExecutionDetail.mockResolvedValue({ data: { data: null } });
});

describe('Runbook 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><RunbookPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时调用获取模板/执行/统计API', async () => {
    await act(async () => {
      render(<BrowserRouter><RunbookPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockRunbookApi.getStats).toHaveBeenCalled();
    });
    expect(mockRunbookApi.listTemplates).toHaveBeenCalled();
    expect(mockRunbookApi.listExecutions).toHaveBeenCalled();
  });

  it('空数据不崩溃且页面有内容', async () => {
    await act(async () => {
      render(<BrowserRouter><RunbookPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockRunbookApi.getStats).toHaveBeenCalled();
    });
    expect(document.querySelector('.ant-tabs')).toBeTruthy();
  });
});
