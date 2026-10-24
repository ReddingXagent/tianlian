/**
 * FleetManagement 组件基础测试
 * 验证：渲染、列表加载、新增/编辑/删除 API 调用
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API
// ═══════════════════════════════════════════
const { mockEnterpriseAPI, mockTeamUtil } = vi.hoisted(() => ({
  mockEnterpriseAPI: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    stations: vi.fn(),
    availableStations: vi.fn(),
    setStations: vi.fn(),
  },
  mockTeamUtil: {
    getCurrentTeamId: vi.fn(() => 1),
  },
}));

vi.mock('../../../../api', () => ({
  enterpriseAPI: mockEnterpriseAPI,
}));

vi.mock('../../../../utils/team', () => mockTeamUtil);

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import FleetManagement from '../index';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  vi.clearAllMocks();
  mockEnterpriseAPI.list.mockResolvedValue({
    data: {
      items: [
        { id: 1, name: '顺丰车队', code: 'FLEET-001', contact: '张三', phone: '13800000001', balance: 5000.00, status: 'active', created_at: '2026-01-15T10:00:00Z' },
        { id: 2, name: '京东物流', code: 'FLEET-002', contact: '李四', phone: '13800000002', balance: 12000.50, status: 'active', created_at: '2026-02-20T14:30:00Z' },
      ],
    },
  });
  mockEnterpriseAPI.create.mockResolvedValue({});
  mockEnterpriseAPI.update.mockResolvedValue({});
  mockEnterpriseAPI.delete.mockResolvedValue({});
  mockEnterpriseAPI.stations.mockResolvedValue({
    data: { code: 200, data: [{ id: 10, name: '北京朝阳站', code: 'STA010' }] },
  });
  mockEnterpriseAPI.availableStations.mockResolvedValue({
    data: {
      code: 200,
      data: [
        { id: 10, name: '北京朝阳站', code: 'STA010' },
        { id: 20, name: '上海浦东站', code: 'STA020' },
      ],
    },
  });
  mockEnterpriseAPI.setStations.mockResolvedValue({ data: { code: 200 } });
});

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
describe('FleetManagement — 渲染与列表加载', () => {
  it('渲染车队管理标题和新增按钮', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetManagement /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('新增车队')).toBeInTheDocument();
    });
  });

  it('加载车队列表并显示数据', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetManagement /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('顺丰车队')).toBeInTheDocument();
      expect(screen.getByText('京东物流')).toBeInTheDocument();
    });
  });

  it('初始加载调用 enterpriseAPI.list', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetManagement /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(mockEnterpriseAPI.list).toHaveBeenCalled();
    });
  });
});

describe('FleetManagement — CRUD 操作', () => {
  it('点击新增按钮打开表单 Modal', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetManagement /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('新增车队')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText('新增车队'));
    });

    await waitFor(() => {
      expect(screen.getByText('新增车队', { selector: '.ant-modal-title' })).toBeInTheDocument();
      expect(screen.getByText('车队名称')).toBeInTheDocument();
      expect(screen.getByText('车队编码')).toBeInTheDocument();
    });
  });

  it('点击编辑按钮打开编辑 Modal', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetManagement /></BrowserRouter>);
    });

    await waitFor(() => {
      expect(screen.getByText('顺丰车队')).toBeInTheDocument();
    });

    // 点击第一个编辑按钮
    const editButtons = screen.getAllByRole('button').filter(btn =>
      btn.querySelector('.anticon-edit'),
    );
    expect(editButtons.length).toBeGreaterThan(0);

    await act(async () => {
      fireEvent.click(editButtons[0]);
    });

    await waitFor(() => {
      expect(screen.getByText('编辑车队', { selector: '.ant-modal-title' })).toBeInTheDocument();
    });
  });
});

describe('FleetManagement — 场站绑定（卡691532f2：写入口迁至运维侧）', () => {
  it('点击场站绑定按钮打开 Modal，加载已绑定/可选场站', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetManagement /></BrowserRouter>);
    });

    await waitFor(() => expect(screen.getByText('顺丰车队')).toBeInTheDocument());

    const bindButtons = screen.getAllByRole('button').filter(btn =>
      btn.querySelector('.anticon-environment'),
    );
    expect(bindButtons.length).toBeGreaterThan(0);

    await act(async () => {
      fireEvent.click(bindButtons[0]);
    });

    await waitFor(() => {
      expect(screen.getByText(/场站绑定 — 顺丰车队/, { selector: '.ant-modal-title' })).toBeInTheDocument();
    });
    expect(mockEnterpriseAPI.stations).toHaveBeenCalledWith(1);
    expect(mockEnterpriseAPI.availableStations).toHaveBeenCalledWith(1);
  });

  it('保存绑定调用 setStations(enterpriseId, stationIds)', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetManagement /></BrowserRouter>);
    });

    await waitFor(() => expect(screen.getByText('顺丰车队')).toBeInTheDocument());

    const bindButtons = screen.getAllByRole('button').filter(btn =>
      btn.querySelector('.anticon-environment'),
    );
    await act(async () => {
      fireEvent.click(bindButtons[0]);
    });

    await waitFor(() =>
      expect(screen.getByText(/场站绑定 — 顺丰车队/, { selector: '.ant-modal-title' })).toBeInTheDocument(),
    );

    // Modal 内"保存绑定"按钮触发 PUT
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /保存绑定/ }));
    });

    await waitFor(() => {
      expect(mockEnterpriseAPI.setStations).toHaveBeenCalledWith(1, [10]);
    });
  });
});
