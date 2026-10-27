import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../api', () => ({ default: mockApi }));
vi.mock('echarts-for-react', () => ({ default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import WorkOrderStatsPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: { data: { by_status: {}, by_engineer: {}, by_level: {}, total: 0, items: [] } } });
});

describe('WorkOrderStats 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><WorkOrderStatsPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时请求数据', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrderStatsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalled();
    });
  });

  it('渲染Card/Statistic组件', async () => {
    await act(async () => {
      render(<BrowserRouter><WorkOrderStatsPage /></BrowserRouter>);
    });
    expect(document.querySelector('.ant-card')).toBeTruthy();
  });
});
