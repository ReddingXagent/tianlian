/**
 * 车队 - 概览看板 Vitest 组件测试
 *
 * 覆盖：页面渲染不崩溃 / 6 卡片存在 / 近期交易列表渲染 / API 错误兜底
 *
 * 字段契约对齐后端 app/api/v1/fleet_overview.py：
 *   GET /api/v1/fleet/overview?enterprise_id={eid}
 *   响应(success_response 包装)：
 *     data.enterprise        = { id, name, code, balance, status }
 *     data.total_vehicles    = number
 *     data.total_charged_kwh = number
 *     data.total_spent       = number
 *     data.recent_transactions[] = { id, type(recharge/consume/refund), amount, balance_after, created_at }
 *   注：credit_limit / 车辆状态分布 / V2G / 碳减排 后端未返回，页面须兜底(-- 或 0)。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API（与 settings/vehicles 测试一致：mock '../../../api' 默认导出）
// ═══════════════════════════════════════════
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({ default: mockApi }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal() as typeof import('antd');
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

// ═══════════════════════════════════════════
// 测试数据（字段对齐后端 fleet_overview.py + 统一响应包装）
// ═══════════════════════════════════════════
const mockEnterpriseList = {
  code: 200,
  message: 'success',
  data: {
    items: [
      { id: 1, name: '顺达物流有限公司', code: 'TL-FLEET-001', status: 'active' },
      { id: 2, name: '鹏程货运公司', code: 'TL-FLEET-002', status: 'active' },
    ],
    total: 2,
  },
};

const mockOverview = {
  code: 200,
  message: 'success',
  data: {
    enterprise: {
      id: 1,
      name: '顺达物流有限公司',
      code: 'TL-FLEET-001',
      balance: 485600.5,
      status: 'active',
    },
    total_vehicles: 12,
    total_charged_kwh: 15680.5,
    total_spent: 18900.0,
    recent_transactions: [
      { id: 1, type: 'recharge', amount: 1000, balance_after: 485600.5, created_at: '2026-07-20T10:00:00' },
      { id: 2, type: 'consume', amount: -120.5, balance_after: 484600.5, created_at: '2026-07-19T10:00:00' },
      { id: 3, type: 'refund', amount: 50, balance_after: 484650.5, created_at: '2026-07-18T10:00:00' },
    ],
  },
};

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url === '/enterprises') return Promise.resolve({ data: mockEnterpriseList });
    if (url === '/fleet/overview') return Promise.resolve({ data: mockOverview });
    return Promise.resolve({ data: { code: 200, data: { items: [] } } });
  });
  mockApi.put.mockResolvedValue({ data: { code: 200 } });
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
});

import FleetDashboardPage from '../Dashboard';

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════
describe('FleetDashboardPage', () => {
  it('1. 渲染概览看板不崩溃，默认加载首个企业的概览', async () => {
    renderWithRouter(<FleetDashboardPage />);

    // 拉取企业列表
    expect(mockApi.get).toHaveBeenCalledWith('/enterprises');

    // 默认选中首个企业并请求其概览
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/fleet/overview', { params: { enterprise_id: 1 } });
    });
  });

  it('2. 渲染 6 个区块卡片(企业信息/车队规模/充电运营/V2G收益/碳减排/近期交易)', async () => {
    renderWithRouter(<FleetDashboardPage />);

    await waitFor(() => {
      expect(screen.getByText('企业基础信息')).toBeInTheDocument();
    });
    expect(screen.getByText('车队规模')).toBeInTheDocument();
    expect(screen.getByText('充电运营')).toBeInTheDocument();
    expect(screen.getByText('V2G 收益')).toBeInTheDocument();
    expect(screen.getByText('碳减排')).toBeInTheDocument();
    expect(screen.getByText('近期交易')).toBeInTheDocument();
  });

  it('3. 近期交易列表渲染 3 笔记录(类型/金额/余额)', async () => {
    const { container } = renderWithRouter(<FleetDashboardPage />);

    await waitFor(() => {
      expect(screen.getByText('近期交易')).toBeInTheDocument();
    });

    // 表格行数 = mock 的 3 笔
    const rows = container.querySelectorAll('.ant-table-row');
    expect(rows.length).toBe(3);

    // 类型 Tag(recharge→充值 / consume→消费 / refund→退款)
    expect(screen.getByText('充值')).toBeInTheDocument();
    expect(screen.getByText('消费')).toBeInTheDocument();
    expect(screen.getByText('退款')).toBeInTheDocument();
  });

  it('4. 概览 API 失败时不崩溃，兜底展示卡片结构', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url === '/enterprises') return Promise.resolve({ data: mockEnterpriseList });
      if (url === '/fleet/overview') return Promise.reject(new Error('网络错误'));
      return Promise.resolve({ data: {} });
    });

    renderWithRouter(<FleetDashboardPage />);

    // 即使 overview 失败，6 卡片骨架仍应渲染(兜底，不崩溃)
    await waitFor(() => {
      expect(screen.getByText('企业基础信息')).toBeInTheDocument();
    });
    expect(screen.getByText('车队规模')).toBeInTheDocument();
    expect(screen.getByText('近期交易')).toBeInTheDocument();
  });

  it('5. 后端缺失字段(credit_limit / V2G / 碳减排)做兜底展示，不报错', async () => {
    renderWithRouter(<FleetDashboardPage />);

    await waitFor(() => {
      expect(screen.getByText('顺达物流有限公司')).toBeInTheDocument();
    });

    // 信用额度后端不返回 → 兜底 '--'
    expect(screen.getAllByText('--').length).toBeGreaterThanOrEqual(1);
  });
});
