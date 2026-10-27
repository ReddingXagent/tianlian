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

import RunbookApprovalPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: [] });
  mockApi.post.mockResolvedValue({});
});

describe('RunbookApproval 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><RunbookApprovalPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时获取审批列表', async () => {
    await act(async () => {
      render(<BrowserRouter><RunbookApprovalPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalled();
    });
  });

  it('渲染Tabs组件', async () => {
    await act(async () => {
      render(<BrowserRouter><RunbookApprovalPage /></BrowserRouter>);
    });
    expect(document.querySelector('.ant-tabs')).toBeTruthy();
  });
});
