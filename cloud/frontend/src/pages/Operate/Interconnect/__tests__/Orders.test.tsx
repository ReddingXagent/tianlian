/**
 * 互联互通导流订单 — Vitest 单元测试 (迁移至运营平台)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../../api/operateExternal', () => ({
  interconnectOrderAPI: {
    list: vi.fn((params?: Record<string, unknown>) => mockApi.get('/operate/interconnect/orders', { params })),
    get: vi.fn(),
    create: vi.fn(),
  },
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import InterconnectOrders from '../Orders';
import { interconnectOrderAPI } from '../../../../api/operateExternal';

const SAMPLE = {
  id: 1,
  team_id: 0,
  platform_id: 1,
  platform_code: 'huawei',
  outer_order_id: 'OUT-20260720-001',
  outer_user_id: 'U100',
  charge_energy_kwh: 32.5,
  total_amount: 45.8,
  our_share: 32.06,
  partner_share: 13.74,
  status: 'synced',
  synced_at: '2026-07-20T10:00:00',
  created_at: '2026-07-20T10:00:00',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: { items: [SAMPLE], total: 1, page: 1, page_size: 20 } });
});

describe('InterconnectOrders (Operate)', () => {
  it('渲染订单列表', async () => {
    render(<InterconnectOrders />);
    expect(interconnectOrderAPI.list).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText('OUT-20260720-001')).toBeInTheDocument());
  });

  it('选择来源平台筛选触发带platform_code的查询', async () => {
    render(<InterconnectOrders />);
    await waitFor(() => expect(screen.getByText('OUT-20260720-001')).toBeInTheDocument());
    fireEvent.mouseDown(document.querySelector('.ant-select-selector') as HTMLElement);
    await waitFor(() => expect(screen.getByText('特来电')).toBeInTheDocument());
    fireEvent.click(screen.getByText('特来电'));
    await waitFor(() =>
      expect(interconnectOrderAPI.list).toHaveBeenCalledWith(expect.objectContaining({ platform_code: 'teld' }))
    );
  });
});
