import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../api', () => ({ default: mockApi }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import LogAnalysisPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('/devices')) return Promise.resolve({ data: [] });
    if (url.includes('model_config')) return Promise.resolve({ data: { providers: [] } });
    return Promise.resolve({ data: [] });
  });
  mockApi.post.mockResolvedValue({});
});

describe('LogAnalysis 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><LogAnalysisPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时获取诊断记录', async () => {
    await act(async () => {
      render(<BrowserRouter><LogAnalysisPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalled();
    });
  });

  it('渲染Tabs组件', async () => {
    await act(async () => {
      render(<BrowserRouter><LogAnalysisPage /></BrowserRouter>);
    });
    expect(document.querySelector('.ant-tabs')).toBeTruthy();
  });
});
