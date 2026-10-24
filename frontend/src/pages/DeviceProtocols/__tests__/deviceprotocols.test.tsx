import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockProtocolAPI } = vi.hoisted(() => ({
  mockProtocolAPI: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../api', () => ({ protocolAPI: mockProtocolAPI }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import DeviceProtocolsPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockProtocolAPI.list.mockResolvedValue({ data: { data: { items: [], total: 0 } } });
});

describe('DeviceProtocols 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><DeviceProtocolsPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时调用list API', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceProtocolsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockProtocolAPI.list).toHaveBeenCalled();
    });
  });

  it('渲染Table和Card', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceProtocolsPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockProtocolAPI.list).toHaveBeenCalled();
    });
    expect(document.querySelector('.ant-table')).toBeTruthy();
    expect(document.querySelector('.ant-card')).toBeTruthy();
  });
});
