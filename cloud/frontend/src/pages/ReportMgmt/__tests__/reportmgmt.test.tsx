import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockReportAPI } = vi.hoisted(() => ({
  mockReportAPI: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../api', () => ({ reportAPI: mockReportAPI }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import ReportMgmtPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockReportAPI.list.mockResolvedValue({ data: { data: { items: [], total: 0 } } });
  mockReportAPI.create.mockResolvedValue({});
  mockReportAPI.update.mockResolvedValue({});
  mockReportAPI.delete.mockResolvedValue({});
});

describe('ReportMgmt 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><ReportMgmtPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时调用list API', async () => {
    await act(async () => {
      render(<BrowserRouter><ReportMgmtPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockReportAPI.list).toHaveBeenCalled();
    });
  });

  it('空数据渲染表格', async () => {
    await act(async () => {
      render(<BrowserRouter><ReportMgmtPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockReportAPI.list).toHaveBeenCalled();
    });
    expect(document.querySelector('.ant-table')).toBeTruthy();
  });
});
