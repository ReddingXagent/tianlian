/**
 * Admin 入口页 — Vitest 单元测试 (更新: 互联互通/市政监管已迁移至运营平台)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

import AdminPage from '../index';

beforeEach(() => { vi.clearAllMocks(); });

describe('AdminPage 入口', () => {
  it('渲染迁移提示页面', () => {
    render(<AdminPage />);
    expect(screen.getByText('管理后台')).toBeInTheDocument();
    expect(screen.getByText('互联互通和市政监管已迁移至运营平台')).toBeInTheDocument();
  });
});
