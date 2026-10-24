import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockAlarmNoticeAPI } = vi.hoisted(() => ({
  mockAlarmNoticeAPI: { list: vi.fn(), markRead: vi.fn(), resolve: vi.fn(), ignore: vi.fn(), getStats: vi.fn() },
}));

vi.mock('../../../api', () => ({ alarmNoticeAPI: mockAlarmNoticeAPI }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import AlarmNoticesPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockAlarmNoticeAPI.list.mockResolvedValue({ data: { data: { items: [], total: 0 } } });
  mockAlarmNoticeAPI.getStats.mockResolvedValue({ data: { data: { total: 0, active: 0 } } });
});

describe('AlarmNotices 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><AlarmNoticesPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时获取通知列表', async () => {
    await act(async () => {
      render(<BrowserRouter><AlarmNoticesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockAlarmNoticeAPI.list).toHaveBeenCalled();
    });
  });

  it('渲染Table组件', async () => {
    await act(async () => {
      render(<BrowserRouter><AlarmNoticesPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockAlarmNoticeAPI.list).toHaveBeenCalled();
    });
    expect(document.querySelector('.ant-table')).toBeTruthy();
  });
});
