import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

const { mockSmartDiagnosisApi } = vi.hoisted(() => ({
  mockSmartDiagnosisApi: { getKeywords: vi.fn(), diagnose: vi.fn() },
}));

vi.mock('../../../api/smartDiagnosis', () => ({ default: mockSmartDiagnosisApi }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import SmartDiagnosisPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
  mockSmartDiagnosisApi.getKeywords.mockResolvedValue({ keywords: [] });
  mockSmartDiagnosisApi.diagnose.mockResolvedValue({ data: { data: null } });
});

describe('SmartDiagnosis 页面', () => {
  it('渲染不崩溃', async () => {
    let container: ReturnType<typeof render>['container'];
    await act(async () => {
      const r = render(<BrowserRouter><SmartDiagnosisPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('挂载时加载关键词库', async () => {
    await act(async () => {
      render(<BrowserRouter><SmartDiagnosisPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(mockSmartDiagnosisApi.getKeywords).toHaveBeenCalled();
    });
  });

  it('渲染Card和Form', async () => {
    await act(async () => {
      render(<BrowserRouter><SmartDiagnosisPage /></BrowserRouter>);
    });
    expect(document.querySelector('.ant-card')).toBeTruthy();
    expect(document.querySelector('.ant-form')).toBeTruthy();
  });
});
