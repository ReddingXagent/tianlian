/**
 * 市政监管平台配置 — Vitest 单元测试 (迁移至运营平台)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';

const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../../api/operateExternal', () => ({
  supervisionAPI: {
    list: vi.fn(() => mockApi.get('/operate/supervision/configs')),
    get: vi.fn(),
    create: vi.fn((d: Record<string, unknown>) => mockApi.post('/operate/supervision/configs', d)),
    update: vi.fn((id: number, d: Record<string, unknown>) => mockApi.put(`/operate/supervision/configs/${id}`, d)),
    delete: vi.fn((id: number) => mockApi.delete(`/operate/supervision/configs/${id}`)),
  },
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import SupervisionConfigs from '../Configs';
import { supervisionAPI } from '../../../../api/operateExternal';

const SAMPLE = {
  id: 1,
  team_id: 0,
  city: '郑州市',
  city_code: '410100',
  platform_name: null,
  platform_type: 'generic',
  protocol_type: 'http_push',
  platform_url: 'https://gov.zz.cn/charge',
  auth_config: { token: 'xxx' },
  report_strategy: 'scheduled',
  report_interval_seconds: 60,
  station_endpoints: null,
  heartbeat_enabled: 1,
  status: 'active',
  remark: null,
  created_at: '2026-07-01T00:00:00',
  updated_at: '2026-07-01T00:00:00',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: { items: [SAMPLE], total: 1, page: 1, page_size: 20 } });
  mockApi.post.mockResolvedValue({ data: SAMPLE });
  mockApi.put.mockResolvedValue({ data: SAMPLE });
  mockApi.delete.mockResolvedValue({ data: { id: 1 } });
});

describe('SupervisionConfigs (Operate)', () => {
  it('渲染监管配置列表', async () => {
    render(<SupervisionConfigs />);
    expect(supervisionAPI.list).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText('郑州市')).toBeInTheDocument());
  });

  it('点击新增打开Modal表单', async () => {
    render(<SupervisionConfigs />);
    await waitFor(() => expect(screen.getByText('郑州市')).toBeInTheDocument());
    fireEvent.click(screen.getByText('新增配置'));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    expect(screen.getByText('对接城市')).toBeInTheDocument();
  });

  it('点击编辑回填表单', async () => {
    render(<SupervisionConfigs />);
    await waitFor(() => expect(screen.getByText('郑州市')).toBeInTheDocument());
    fireEvent.click(screen.getByText('编辑'));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    const input = document.querySelector('input#platform_url') as HTMLInputElement;
    expect(input?.value).toBe('https://gov.zz.cn/charge');
  });

  it('点击删除调用delete API', async () => {
    render(<SupervisionConfigs />);
    await waitFor(() => expect(screen.getByText('郑州市')).toBeInTheDocument());
    fireEvent.click(screen.getByText('删除'));
    const popconfirmBtns = await waitFor(() => {
      const btns = document.querySelectorAll('.ant-popconfirm-buttons .ant-btn-primary');
      expect(btns.length).toBeGreaterThan(0);
      return btns;
    });
    await act(async () => {
      fireEvent.click(popconfirmBtns[0]);
    });
    await waitFor(() => expect(supervisionAPI.delete).toHaveBeenCalledWith(1));
  });
});
