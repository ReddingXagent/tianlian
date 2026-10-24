/**
 * 合规检查报告 — Vitest 单元测试 (迁移至运营平台)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

const { mockApi } = vi.hoisted(() => ({
  mockApi: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock('../../../../api/operateExternal', () => ({
  complianceAPI: {
    list: vi.fn(() => mockApi.get('/operate/supervision/compliance')),
    get: vi.fn(),
    run: vi.fn(),
  },
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import SupervisionCompliance from '../Compliance';
import { complianceAPI } from '../../../../api/operateExternal';

const SAMPLE = {
  id: 1,
  team_id: 0,
  config_id: 1,
  city: '郑州市',
  check_type: 'data_integrity',
  result: 'pass',
  score: 95.5,
  details: null,
  checked_at: '2026-07-20T10:00:00',
  created_at: '2026-07-20T10:00:00',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ data: { items: [SAMPLE], total: 1, page: 1, page_size: 20 } });
});

describe('SupervisionCompliance (Operate)', () => {
  it('渲染合规检查列表', async () => {
    render(<SupervisionCompliance />);
    expect(complianceAPI.list).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText('郑州市')).toBeInTheDocument());
  });
});
