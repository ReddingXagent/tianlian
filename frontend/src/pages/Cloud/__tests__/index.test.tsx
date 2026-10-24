/**
 * 云服务配置 — Vitest 单元测试
 * 覆盖: 列表渲染 / 新增Modal / 连通性测试 / 删除
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import React from 'react';

const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../api/admin', () => ({
  cloudConfigAPI: {
    list: vi.fn(() => mockApi.get('/admin/cloud-configs')),
    get: vi.fn(),
    create: vi.fn((d: Record<string, unknown>) => mockApi.post('/admin/cloud-configs', d)),
    update: vi.fn((id: number, d: Record<string, unknown>) => mockApi.put(`/admin/cloud-configs/${id}`, d)),
    delete: vi.fn((id: number) => mockApi.delete(`/admin/cloud-configs/${id}`)),
    test: vi.fn((id: number) => mockApi.post(`/admin/cloud-configs/${id}/test`)),
  },
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import CloudPage from '../index';
import { cloudConfigAPI } from '../../../api/admin';

const SAMPLE = {
  id: 1,
  config_name: '云服务商生产环境',
  provider: 'cloud-a',
  config_json: { region: 'cn-hangzhou', endpoint: 'oss-cn-hangzhou.cloud_providercs.com' },
  bucket: 'tianlian-prod',
  sync_strategy: 'realtime',
  status: 'active',
  remark: null,
  created_at: '2026-07-01T00:00:00',
  updated_at: '2026-07-01T00:00:00',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: { items: [SAMPLE], total: 1, page: 1, page_size: 20 } });
  mockApi.post.mockResolvedValue({ data: { reachable: true, storage_ok: true } });
  mockApi.put.mockResolvedValue({ data: SAMPLE });
  mockApi.delete.mockResolvedValue({ data: { id: 1 } });
});

describe('CloudPage', () => {
  it('渲染云服务配置列表', async () => {
    render(<CloudPage />);
    expect(cloudConfigAPI.list).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText('云服务商生产环境')).toBeInTheDocument());
    expect(screen.getByText('tianlian-prod')).toBeInTheDocument();
  });

  it('点击新增打开Modal表单', async () => {
    render(<CloudPage />);
    await waitFor(() => expect(screen.getByText('云服务商生产环境')).toBeInTheDocument());
    fireEvent.click(screen.getByText('新增配置'));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('配置名称')).toBeInTheDocument();
    expect(within(dialog).getByText('存储桶(Bucket)')).toBeInTheDocument();
  });

  it('点击连通性测试调用test API', async () => {
    render(<CloudPage />);
    await waitFor(() => expect(screen.getByText('云服务商生产环境')).toBeInTheDocument());
    fireEvent.click(screen.getByText('连通性测试'));
    await waitFor(() => expect(cloudConfigAPI.test).toHaveBeenCalledWith(1));
  });

  it('点击删除调用delete API', async () => {
    render(<CloudPage />);
    await waitFor(() => expect(screen.getByText('云服务商生产环境')).toBeInTheDocument());
    fireEvent.click(screen.getByText('删除'));
    const popconfirmBtns = await waitFor(() => {
      const btns = document.querySelectorAll('.ant-popconfirm-buttons .ant-btn-primary');
      expect(btns.length).toBeGreaterThan(0);
      return btns;
    });
    await act(async () => {
      fireEvent.click(popconfirmBtns[0]);
    });
    await waitFor(() => expect(cloudConfigAPI.delete).toHaveBeenCalledWith(1));
  });
});
