/**
 * 边缘网关 SN 平台台账 — Vitest 单元测试 (任务卡 e940c9f4)
 * 覆盖: 列表渲染 + 状态Tag / 批量生成弹窗 / 绑定场站弹窗 / 出库状态流转
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import React from 'react';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';

// 生产环境 main.tsx 全局 ConfigProvider locale=zhCN, Modal 按钮渲染为中文"确定/取消"。
// 测试直接 render 组件缺 locale 上下文 → 按钮回退英文"OK/Cancel"。
// 包裹 ConfigProvider 对齐生产真实渲染, 断言才能验证用户实际看到的中文文案。
const renderWithLocale = (ui: React.ReactElement) =>
  render(<ConfigProvider locale={zhCN}>{ui}</ConfigProvider>);

const { mockEdge, mockStation } = vi.hoisted(() => ({
  mockEdge: {
    list: vi.fn(),
    generate: vi.fn(),
    ship: vi.fn(),
    bind: vi.fn(),
    unbind: vi.fn(),
    online: vi.fn(),
    decommission: vi.fn(),
  },
  mockStation: { list: vi.fn() },
}));

vi.mock('../../../api/admin', () => ({ edgeGatewayAPI: mockEdge }));
vi.mock('../../../api/index', () => ({ stationAPI: mockStation }));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import EdgeGatewaysPage from '../EdgeGateways';

const SAMPLE = {
  id: 1,
  sn: 'GHN000001',
  batch: 'B202608',
  status: 'inventory',
  station_id: null,
  firmware_version: null,
  last_online_at: null,
  created_at: '2026-08-08T00:00:00',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockEdge.list.mockResolvedValue({ data: { items: [SAMPLE], total: 1, page: 1, page_size: 20 } });
  mockEdge.generate.mockResolvedValue({ data: { sn_list: ['GHN000002', 'GHN000003'], count: 2 } });
  mockEdge.ship.mockResolvedValue({ data: { ...SAMPLE, status: 'shipped' } });
  mockEdge.bind.mockResolvedValue({ data: { ...SAMPLE, status: 'bound', station_id: 7 } });
  mockStation.list.mockResolvedValue({ data: [{ id: 7, name: '郑州东站', code: 'ST007' }] });
});

describe('EdgeGatewaysPage', () => {
  it('渲染 SN 列表与状态Tag', async () => {
    renderWithLocale(<EdgeGatewaysPage />);
    expect(mockEdge.list).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText('GHN000001')).toBeInTheDocument());
    // 状态 Tag 显示中文标签
    expect(screen.getByText('入库')).toBeInTheDocument();
    expect(screen.getByText('B202608')).toBeInTheDocument();
  });

  it('点击批量生成SN打开弹窗', async () => {
    renderWithLocale(<EdgeGatewaysPage />);
    await waitFor(() => expect(screen.getByText('GHN000001')).toBeInTheDocument());
    fireEvent.click(screen.getByText('批量生成SN'));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('生成数量')).toBeInTheDocument();
    expect(within(dialog).getByText('区域码')).toBeInTheDocument();
    expect(within(dialog).getByText('批次号(选填)')).toBeInTheDocument();
  });

  it('提交批量生成调用 generate API', async () => {
    renderWithLocale(<EdgeGatewaysPage />);
    await waitFor(() => expect(screen.getByText('GHN000001')).toBeInTheDocument());
    fireEvent.click(screen.getByText('批量生成SN'));
    const dialog = await waitFor(() => screen.getByRole('dialog'));
    // 默认 count=10, region=HN 已由 form.setFieldsValue 填充 → 点 footer 主按钮提交
    const okBtn = within(dialog).getByRole('button', { name: /确\s*定/ });
    await act(async () => { fireEvent.click(okBtn); });
    await waitFor(() => expect(mockEdge.generate).toHaveBeenCalled());
    const callArg = mockEdge.generate.mock.calls[0][0];
    expect(callArg.region).toBe('HN');
    expect(callArg.count).toBeGreaterThanOrEqual(1);
  });

  it('点击出库触发 ship 流转', async () => {
    renderWithLocale(<EdgeGatewaysPage />);
    await waitFor(() => expect(screen.getByText('GHN000001')).toBeInTheDocument());
    fireEvent.click(screen.getByText('出库'));
    await waitFor(() => expect(mockEdge.ship).toHaveBeenCalledWith('GHN000001'));
  });

  it('点击绑定打开场站选择弹窗并加载场站', async () => {
    renderWithLocale(<EdgeGatewaysPage />);
    await waitFor(() => expect(screen.getByText('GHN000001')).toBeInTheDocument());
    fireEvent.click(screen.getByText('绑定'));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    expect(mockStation.list).toHaveBeenCalled();
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('选择场站')).toBeInTheDocument();
  });

  it('已退役网关的操作按钮禁用', async () => {
    mockEdge.list.mockResolvedValue({
      data: { items: [{ ...SAMPLE, status: 'decommissioned' }], total: 1, page: 1, page_size: 20 },
    });
    renderWithLocale(<EdgeGatewaysPage />);
    await waitFor(() => expect(screen.getByText('已退役')).toBeInTheDocument());
    const shipBtn = screen.getByText('出库').closest('button') as HTMLButtonElement;
    expect(shipBtn.disabled).toBe(true);
  });
});
