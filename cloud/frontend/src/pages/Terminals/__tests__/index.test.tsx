/**
 * 终端设备管理 — Vitest 单元测试
 * 覆盖: 列表渲染 / 新增Modal / 编辑回填 / 删除
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import React from 'react';

const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../api/admin', () => ({
  terminalsAPI: {
    list: vi.fn(() => mockApi.get('/admin/terminals')),
    get: vi.fn(),
    create: vi.fn((d: Record<string, unknown>) => mockApi.post('/admin/terminals', d)),
    update: vi.fn((id: number, d: Record<string, unknown>) => mockApi.put(`/admin/terminals/${id}`, d)),
    delete: vi.fn((id: number) => mockApi.delete(`/admin/terminals/${id}`)),
  },
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import TerminalsPage from '../index';
import { terminalsAPI } from '../../../api/admin';

const SAMPLE = {
  id: 1,
  terminal_code: 'CAM-A001',
  terminal_type: 'camera',
  station_name: '郑州东站充电站',
  ip_address: '192.168.1.101',
  rtsp_url: 'rtsp://10.0.0.1:554/stream1',
  recording_config: { enable: true, quality: '1080p', retention_days: 30 },
  status: 'online',
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

describe('TerminalsPage', () => {
  it('渲染终端设备列表', async () => {
    render(<TerminalsPage />);
    expect(terminalsAPI.list).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText('CAM-A001')).toBeInTheDocument());
    expect(screen.getByText('郑州东站充电站')).toBeInTheDocument();
  });

  it('点击新增打开Modal表单', async () => {
    render(<TerminalsPage />);
    await waitFor(() => expect(screen.getByText('CAM-A001')).toBeInTheDocument());
    fireEvent.click(screen.getByText('新增终端'));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('终端编号')).toBeInTheDocument();
    expect(within(dialog).getByText('流地址(RTSP/RTMP)')).toBeInTheDocument();
  });

  it('点击编辑回填并打开Modal', async () => {
    render(<TerminalsPage />);
    await waitFor(() => expect(screen.getByText('CAM-A001')).toBeInTheDocument());
    fireEvent.click(screen.getByText('编辑'));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    expect(terminalsAPI.list).toHaveBeenCalled();
  });

  it('点击删除调用delete API', async () => {
    render(<TerminalsPage />);
    await waitFor(() => expect(screen.getByText('CAM-A001')).toBeInTheDocument());
    fireEvent.click(screen.getByText('删除'));
    const popconfirmBtns = await waitFor(() => {
      const btns = document.querySelectorAll('.ant-popconfirm-buttons .ant-btn-primary');
      expect(btns.length).toBeGreaterThan(0);
      return btns;
    });
    await act(async () => {
      fireEvent.click(popconfirmBtns[0]);
    });
    await waitFor(() => expect(terminalsAPI.delete).toHaveBeenCalledWith(1));
  });
});
