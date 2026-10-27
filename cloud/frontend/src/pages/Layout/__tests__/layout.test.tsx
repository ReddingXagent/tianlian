import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));
vi.mock('antd', async (orig) => {
  const actual = await orig<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import LayoutPage from '../index';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Layout 组件', () => {
  it('渲染不崩溃', () => {
    let container: ReturnType<typeof render>['container'];
    act(() => {
      const r = render(<BrowserRouter><LayoutPage /></BrowserRouter>);
      container = r.container;
    });
    expect(container!).toBeTruthy();
  });

  it('渲染antd Layout结构', () => {
    act(() => {
      render(<BrowserRouter><LayoutPage /></BrowserRouter>);
    });
    // Layout should render ant-design layout components
    const layout = document.querySelector('.ant-layout');
    expect(layout).toBeTruthy();
  });

  it('包含Outlet或导航元素', () => {
    act(() => {
      render(<BrowserRouter><LayoutPage /></BrowserRouter>);
    });
    // Should have menu or sider
    const hasMenu = document.querySelector('.ant-menu, .ant-layout-sider, .ant-layout-content');
    expect(hasMenu).toBeTruthy();
  });
});
