/**
 * 车队设置页面 — Vitest 单元测试
 *
 * 覆盖：渲染、Tab(企业信息/场站绑定/车辆默认配置)、企业信息表单、保存触发PUT
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

vi.mock('../../../../api', () => ({ default: mockApi }));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

// ═══════════════════════════════════════════
// Mock data
// ═══════════════════════════════════════════
const mockEnterprises = { items: [{ id: 1, name: '顺达物流', code: 'TL001', status: 'active' }] };
const mockDetail = {
  id: 1, name: '顺达物流', code: 'TL001', contact: '王经理', phone: '13800138001', status: 'active',
};
const mockBoundStations = { data: [{ id: 1, name: '东郊站', code: 'ST001', address: '东郊', status: 'normal' }] };

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url === '/teams') return Promise.resolve({ data: { items: [] } });
    if (url === '/enterprises') return Promise.resolve({ data: mockEnterprises });
    if (url.endsWith('/available-stations')) return Promise.resolve({ data: { data: [] } });
    if (url.endsWith('/stations')) return Promise.resolve({ data: mockBoundStations });
    if (/\/enterprises\/\d+$/.test(url)) return Promise.resolve({ data: mockDetail });
    return Promise.resolve({ data: { items: [] } });
  });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
});

import FleetSettingsPage from '../index';

// ═══════════════════════════════════════════
// 渲染 & Tab
// ═══════════════════════════════════════════
describe('车队设置 — 渲染', () => {
  it('页面正常渲染不崩溃', () => {
    const { container } = renderWithRouter(<FleetSettingsPage />);
    expect(container).toBeTruthy();
  }, 15000);

  it('显示标题与三个Tab', async () => {
    renderWithRouter(<FleetSettingsPage />);
    await waitFor(() => {
      expect(screen.getByText('车队设置')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getByText('企业信息')).toBeInTheDocument();
    expect(screen.getByText('场站绑定')).toBeInTheDocument();
    expect(screen.getByText('车辆默认配置')).toBeInTheDocument();
  }, 15000);

  it('企业信息表单回填字段', async () => {
    renderWithRouter(<FleetSettingsPage />);
    await waitFor(() => {
      // 名称输入框回填企业名（企业名同时出现在 Select options，用 getAllByDisplayValue 取 input）
      expect(screen.getByDisplayValue('顺达物流')).toBeInTheDocument();
    }, { timeout: 8000 });
    expect(screen.getByDisplayValue('王经理')).toBeInTheDocument();
    expect(screen.getByDisplayValue('13800138001')).toBeInTheDocument();
    expect(screen.getByText('保存企业信息')).toBeInTheDocument();
  }, 15000);
});

// ═══════════════════════════════════════════
// 保存交互
// ═══════════════════════════════════════════
describe('车队设置 — 交互', () => {
  it('点击保存企业信息触发PUT', async () => {
    renderWithRouter(<FleetSettingsPage />);
    await waitFor(() => expect(screen.getByText('保存企业信息')).toBeInTheDocument(), { timeout: 8000 });

    fireEvent.click(screen.getByText('保存企业信息'));

    await waitFor(() => {
      expect(mockApi.put).toHaveBeenCalled();
      const [url] = mockApi.put.mock.calls[0];
      expect(url).toMatch(/\/enterprises\/1$/);
    });
  }, 15000);
});
