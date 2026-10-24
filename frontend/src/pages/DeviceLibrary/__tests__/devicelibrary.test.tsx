import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockDeviceLibraryAPI } = vi.hoisted(() => ({
  mockDeviceLibraryAPI: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../api', () => ({ deviceLibraryAPI: mockDeviceLibraryAPI }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import DeviceLibraryPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockDeviceLibraryAPI.list.mockResolvedValue({ data: { data: { items: [], total: 0 } } });
});

describe('DeviceLibrary 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><DeviceLibraryPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时调用list API', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceLibraryPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockDeviceLibraryAPI.list).toHaveBeenCalled();
    });
  });

  it('渲染Table和Card', async () => {
    await act(async () => {
      render(<BrowserRouter><DeviceLibraryPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockDeviceLibraryAPI.list).toHaveBeenCalled();
    });
    expect(document.querySelector('.ant-table')).toBeTruthy();
    expect(document.querySelector('.ant-card')).toBeTruthy();
  });
});
