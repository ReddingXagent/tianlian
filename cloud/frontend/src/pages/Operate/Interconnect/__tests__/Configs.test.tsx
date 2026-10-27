/**
 * 互联互通平台配置 — Vitest 单元测试 (迁移至运营平台)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';

const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../../api/operateExternal', () => ({
  interconnectAPI: {
    list: vi.fn(() => mockApi.get('/operate/interconnect/configs')),
    get: vi.fn(),
    create: vi.fn((d: Record<string, unknown>) => mockApi.post('/operate/interconnect/configs', d)),
    update: vi.fn((id: number, d: Record<string, unknown>) => mockApi.put(`/operate/interconnect/configs/${id}`, d)),
    delete: vi.fn((id: number) => mockApi.delete(`/operate/interconnect/configs/${id}`)),
    test: vi.fn((id: number) => mockApi.post(`/operate/interconnect/configs/${id}/test`)),
  },
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import InterconnectConfigs from '../Configs';
import { interconnectAPI } from '../../../../api/operateExternal';

const SAMPLE = {
  id: 1,
  team_id: 0,
  platform_name: '国网郑州充电平台',
  platform_code: 'sgcc',
  api_base_url: 'https://api.sgcc.com',
  auth_type: 'apikey',
  auth_params: { key: 'xxx' },
  revenue_share_ratio: 0.7,
  data_sync_interval: 300,
  protocol_version: 'V1.6',
  sync_direction: 'pull',
  status: 'active',
  remark: null,
  created_at: '2026-07-01T00:00:00',
  updated_at: '2026-07-01T00:00:00',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: { items: [SAMPLE], total: 1, page: 1, page_size: 20 } });
  mockApi.post.mockResolvedValue({ data: { reachable: true, auth_ok: true } });
  mockApi.put.mockResolvedValue({ data: SAMPLE });
  mockApi.delete.mockResolvedValue({ data: { id: 1 } });
});

describe('InterconnectConfigs (Operate)', () => {
  it('渲染平台配置列表', async () => {
    render(<InterconnectConfigs />);
    expect(interconnectAPI.list).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText('国网郑州充电平台')).toBeInTheDocument());
  });

  it('点击新增打开Modal表单', async () => {
    render(<InterconnectConfigs />);
    await waitFor(() => expect(screen.getByText('国网郑州充电平台')).toBeInTheDocument());
    fireEvent.click(screen.getByText('新增平台'));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    expect(screen.getByText('API接入地址')).toBeInTheDocument();
  });

  it('点击联调测试调用test API', async () => {
    render(<InterconnectConfigs />);
    await waitFor(() => expect(screen.getByText('国网郑州充电平台')).toBeInTheDocument());
    fireEvent.click(screen.getByText('联调测试'));
    await waitFor(() => expect(interconnectAPI.test).toHaveBeenCalledWith(1));
  });

  it('点击删除调用delete API', async () => {
    render(<InterconnectConfigs />);
    await waitFor(() => expect(screen.getByText('国网郑州充电平台')).toBeInTheDocument());
    fireEvent.click(screen.getByText('删除'));
    const popconfirmBtns = await waitFor(() => {
      const btns = document.querySelectorAll('.ant-popconfirm-buttons .ant-btn-primary');
      expect(btns.length).toBeGreaterThan(0);
      return btns;
    });
    await act(async () => {
      fireEvent.click(popconfirmBtns[0]);
    });
    await waitFor(() => expect(interconnectAPI.delete).toHaveBeenCalledWith(1));
  });
});
