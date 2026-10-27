import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockDeviceAPI, mockRemoteAPI } = vi.hoisted(() => ({
  mockDeviceAPI: { list: vi.fn() },
  mockRemoteAPI: { send: vi.fn(), getStatus: vi.fn() },
}));

vi.mock('../../../api', () => ({ deviceAPI: mockDeviceAPI, remoteAPI: mockRemoteAPI }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import RemoteControlPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockDeviceAPI.list.mockResolvedValue({ data: { items: [] } });
  mockRemoteAPI.send.mockResolvedValue({});
  mockRemoteAPI.getStatus.mockResolvedValue({ data: { data: {} } });
});

describe('RemoteControl 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><RemoteControlPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时加载设备列表', async () => {
    await act(async () => {
      render(<BrowserRouter><RemoteControlPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockDeviceAPI.list).toHaveBeenCalled();
    });
  });

  it('渲染Card容器', async () => {
    await act(async () => {
      render(<BrowserRouter><RemoteControlPage /></BrowserRouter>);
    });
    expect(document.querySelector('.ant-card')).toBeTruthy();
  });
});
