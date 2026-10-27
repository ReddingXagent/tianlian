import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockStationAPI } = vi.hoisted(() => ({
  mockStationAPI: { businessList: vi.fn(), getDetail: vi.fn() },
}));

vi.mock('../../../api', () => ({ stationAPI: mockStationAPI }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import MapPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockStationAPI.businessList.mockResolvedValue({ data: { items: [] } });
});

describe('Map 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><MapPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时加载站点列表', async () => {
    await act(async () => {
      render(<BrowserRouter><MapPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockStationAPI.businessList).toHaveBeenCalled();
    });
  });

  it('渲染Card容器', async () => {
    await act(async () => {
      render(<BrowserRouter><MapPage /></BrowserRouter>);
    });
    expect(document.querySelector('.ant-card')).toBeTruthy();
  });
});
