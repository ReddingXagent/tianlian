import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import React from 'react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));

import GatewayPage from '../index';

describe('Gateway 重定向页面', () => {
  it('渲染为Navigate组件不崩溃', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/GatewayStub']}>
        <Routes>
          <Route path="/GatewayStub" element={<GatewayPage />} />
          <Route path="/gateway" element={<div data-testid="gateway-target">Target</div>} />
        </Routes>
      </MemoryRouter>
    );
    expect(container).toBeTruthy();
  });

  it('重定向到/gateway路径', () => {
    const { getByTestId } = render(
      <MemoryRouter initialEntries={['/GatewayStub']}>
        <Routes>
          <Route path="/GatewayStub" element={<GatewayPage />} />
          <Route path="/gateway" element={<div data-testid="gateway-target">Target</div>} />
        </Routes>
      </MemoryRouter>
    );
    expect(getByTestId('gateway-target')).toBeTruthy();
  });

  it('组件是函数组件', () => {
    expect(typeof GatewayPage).toBe('function');
  });
});
