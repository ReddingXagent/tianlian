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

import SSLCertificatesPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url.includes('health-check')) return Promise.resolve({ data: { status: 'ok' } });
    return Promise.resolve({ data: [] });
  });
  mockApi.post.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
});

describe('SSLCertificates 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><SSLCertificatesPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时获取证书列表', async () => {
    await act(async () => {
      render(<BrowserRouter><SSLCertificatesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalled();
    });
  });

  it('渲染Table/Tabs组件', async () => {
    await act(async () => {
      render(<BrowserRouter><SSLCertificatesPage /></BrowserRouter>);
    });
    expect(document.querySelector('.ant-tabs, .ant-table')).toBeTruthy();
  });
});
