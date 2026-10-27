/**
 * 数据管理页测试（卡 922b2fba）
 * - 页面渲染：导出/备份表单 + 忘记密码申请队列
 * - 交互：scope 切换租户选择、未选租户提交警告
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DataOpsPage from '../index';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'zh-CN' } }),
}));

const tenantListMock = vi.fn();
const requestsMock = vi.fn();
const exportMock = vi.fn();

vi.mock('../../../api', () => ({
  tenantAPI: { list: (...a: unknown[]) => tenantListMock(...a) },
  forgotPasswordAPI: {
    requests: () => requestsMock(),
    resolve: vi.fn(),
  },
  dataOpsAPI: { export: (...a: unknown[]) => exportMock(...a) },
}));

beforeEach(() => {
  tenantListMock.mockResolvedValue({ data: { data: { items: [{ id: 1, name: '测试运营公司' }] } } });
  requestsMock.mockResolvedValue({ data: { data: { items: [
    { id: 1, account: 'ops_user', status: 'pending', created_at: '2026-10-08T21:00:00' },
    { id: 2, account: 'fleet_admin', status: 'resolved', created_at: '2026-10-08T20:00:00' },
  ] } } });
});

describe('DataOps 数据管理页', () => {
  it('渲染导出与备份区块 + 申请队列', async () => {
    render(<MemoryRouter><DataOpsPage /></MemoryRouter>);
    expect(screen.getByText('数据导出与备份')).toBeInTheDocument();
    expect(screen.getByText('忘记密码申请')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('ops_user')).toBeInTheDocument());
    expect(screen.getByText('1 条待处理')).toBeInTheDocument();
  });

  it('切到指定租户未选择时提交 → 警告且不发请求', async () => {
    render(<MemoryRouter><DataOpsPage /></MemoryRouter>);
    fireEvent.click(screen.getByText('指定租户'));
    fireEvent.click(screen.getByText('导出数据'));
    await waitFor(() => expect(screen.getByText('请先选择要导出的租户')).toBeInTheDocument());
    expect(exportMock).not.toHaveBeenCalled();
  });

  it('全平台导出 → 调 API 并触发下载', async () => {
    const blob = new Blob(['{}'], { type: 'application/json' });
    exportMock.mockResolvedValue({ data: blob });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<MemoryRouter><DataOpsPage /></MemoryRouter>);
    fireEvent.click(screen.getByText('导出数据'));
    await waitFor(() => expect(exportMock).toHaveBeenCalledWith({ scope: 'platform', tenant_id: undefined, mode: 'export' }));
    clickSpy.mockRestore();
  });
});
