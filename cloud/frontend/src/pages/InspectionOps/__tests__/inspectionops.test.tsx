import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockInspectionAPI } = vi.hoisted(() => ({
  mockInspectionAPI: {
    tasks: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
    plans: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn(), toggleStatus: vi.fn() },
    stats: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ inspectionAPI: mockInspectionAPI }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import InspectionOpsPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockInspectionAPI.tasks.list.mockResolvedValue({ data: { items: [], total: 0 } });
  mockInspectionAPI.plans.list.mockResolvedValue({ data: { items: [], total: 0 } });
  mockInspectionAPI.stats.mockResolvedValue({ data: { total: 0, total_tasks: 0, in_progress: 0, completed: 0 } });
});

describe('InspectionOps 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><InspectionOpsPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时获取巡检数据', async () => {
    await act(async () => {
      render(<BrowserRouter><InspectionOpsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockInspectionAPI.stats).toHaveBeenCalled();
    });
  });

  it('渲染Tab组件', async () => {
    await act(async () => {
      render(<BrowserRouter><InspectionOpsPage /></BrowserRouter>);
    });
    expect(document.querySelector('.ant-tabs')).toBeTruthy();
  });
});
