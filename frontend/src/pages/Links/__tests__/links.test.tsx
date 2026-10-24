import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import React from 'react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN', changeLanguage: vi.fn() } }),
}));

import LinksPage from '../index';

describe('Links 重定向页面', () => {
  it('渲染为Navigate重定向', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/links']}>
        <Routes>
          <Route path="/links" element={<LinksPage />} />
          <Route path="/operate/interconnect" element={<div data-testid="gateway-page">Gateway Page</div>} />
        </Routes>
      </MemoryRouter>
    );
    expect(container).toBeTruthy();
  });

  it('重定向到/operate/interconnect', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/links']}>
        <Routes>
          <Route path="/links" element={<LinksPage />} />
          <Route path="/operate/interconnect" element={<div data-testid="gateway-page">Gateway Page</div>} />
        </Routes>
      </MemoryRouter>
    );
    expect(container.querySelector('[data-testid="gateway-page"]')).toBeTruthy();
  });

  it('组件是函数组件', () => {
    expect(typeof LinksPage).toBe('function');
  });
});
