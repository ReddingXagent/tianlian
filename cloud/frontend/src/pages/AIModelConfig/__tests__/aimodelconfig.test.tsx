import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockAiModelConfigAPI } = vi.hoisted(() => ({
  mockAiModelConfigAPI: { getConfig: vi.fn(), saveConfig: vi.fn(), testProvider: vi.fn() },
}));
const { mockGetTaskLabel } = vi.hoisted(() => ({ mockGetTaskLabel: (k: string) => k }));

vi.mock('../../../api/aiModelConfig', () => ({
  aiModelConfigAPI: mockAiModelConfigAPI,
  getTaskLabel: mockGetTaskLabel,
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import AIModelConfigPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockAiModelConfigAPI.getConfig.mockResolvedValue({
    providers: [],
    task_mappings: {},
    fallback_strategy: 'next_available',
  });
  mockAiModelConfigAPI.saveConfig.mockResolvedValue({});
  mockAiModelConfigAPI.testProvider.mockResolvedValue({});
});

describe('AIModelConfig 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><AIModelConfigPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时获取配置', async () => {
    await act(async () => {
      render(<BrowserRouter><AIModelConfigPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockAiModelConfigAPI.getConfig).toHaveBeenCalled();
    });
  });

  it('渲染Card组件', async () => {
    await act(async () => {
      render(<BrowserRouter><AIModelConfigPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockAiModelConfigAPI.getConfig).toHaveBeenCalled();
    });
    expect(document.querySelector('.ant-card')).toBeTruthy();
  });
});
