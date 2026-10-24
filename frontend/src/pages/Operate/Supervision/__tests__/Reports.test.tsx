/**
 * 监管数据上报状态 — Vitest 单元测试 (迁移至运营平台)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../../api/operateExternal', () => ({
  regulatoryReportAPI: {
    list: vi.fn(() => mockApi.get('/operate/supervision/reports')),
    get: vi.fn(),
    manual: vi.fn(),
    retry: vi.fn((id: number) => mockApi.post(`/operate/supervision/reports/${id}/retry`)),
  },
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import SupervisionReports from '../Reports';
import { regulatoryReportAPI } from '../../../../api/operateExternal';

const SAMPLE_FAILED = {
  id: 10,
  team_id: 0,
  config_id: 1,
  city: '郑州市',
  report_type: 'heartbeat',
  report_content: null,
  status: 'failed',
  retry_count: 1,
  error_message: '连接监管平台超时',
  reported_at: '2026-07-20T10:00:00',
  created_at: '2026-07-20T10:00:00',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: { items: [SAMPLE_FAILED], total: 1, page: 1, page_size: 20 } });
  mockApi.post.mockResolvedValue({ data: { ...SAMPLE_FAILED, status: 'success', retry_count: 2, error_message: null } });
});

describe('SupervisionReports (Operate)', () => {
  it('渲染上报记录列表', async () => {
    render(<SupervisionReports />);
    expect(regulatoryReportAPI.list).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText('郑州市')).toBeInTheDocument());
  });

  it('点击重试调用retry API', async () => {
    render(<SupervisionReports />);
    await waitFor(() => expect(screen.getByText('郑州市')).toBeInTheDocument());
    fireEvent.click(screen.getByText('重试'));
    await waitFor(() => expect(regulatoryReportAPI.retry).toHaveBeenCalledWith(10));
  });
});
