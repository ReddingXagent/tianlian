/**
 * 车队管理页面 — Vitest 单元测试
 * 测试：渲染、Tab切换、表格数据、搜索筛选
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══════════════════════════════════════════
// Mock 数据
// ═══════════════════════════════════════════
const mockEnterprises = [
  { id: 1, name: '顺达物流有限公司', code: 'TL-FLEET-001', contact: '张伟', phone: '13800138001', address: '河南省郑州市金水区农业路72号', vehicle_count: 12, driver_count: 15, status: 'active', description: '主营省内干线运输' },
  { id: 2, name: '鹏程货运公司', code: 'TL-FLEET-002', contact: '李强', phone: '13900139002', address: '广东省广州市天河区天河路385号', vehicle_count: 8, driver_count: 10, status: 'active', description: '华南区域配送' },
  { id: 3, name: '通达运输队', code: 'TL-FLEET-003', contact: '王芳', phone: '13700137003', address: '江苏省南京市鼓楼区中山北路223号', vehicle_count: 5, driver_count: 6, status: 'inactive', description: '临时停运' },
];

const mockVehicles = [
  { id: 1, plate_number: '豫A·12345', brand: '比亚迪', model: 'T5', vehicle_type: '货车', enterprise_id: 1, enterprise_name: '顺达物流有限公司', driver: '赵刚', driver_phone: '13600136001', status: 'active', annual_check_date: '2026-03-15', insurance_expiry: '2026-12-31', mileage: 85600, fuel_type: '柴油', load_capacity: 5.5 },
  { id: 2, plate_number: '豫A·23456', brand: '东风', model: '天龙KL', vehicle_type: '货车', enterprise_id: 1, enterprise_name: '顺达物流有限公司', driver: '钱明', driver_phone: '13500135002', status: 'active', annual_check_date: '2026-06-20', insurance_expiry: '2027-01-15', mileage: 123400, fuel_type: '柴油', load_capacity: 8.0 },
  { id: 3, plate_number: '粤B·34567', brand: '五菱', model: '荣光EV', vehicle_type: '新能源车', enterprise_id: 2, enterprise_name: '鹏程货运公司', driver: '孙磊', driver_phone: '13400134003', status: 'active', annual_check_date: '2025-12-01', insurance_expiry: '2026-11-30', mileage: 45200, fuel_type: '纯电', load_capacity: 2.5 },
  { id: 4, plate_number: '粤B·45678', brand: '江淮', model: '帅铃Q6', vehicle_type: '面包车', enterprise_id: 2, enterprise_name: '鹏程货运公司', driver: '周杰', driver_phone: '13300133004', status: 'maintenance', annual_check_date: '2026-01-10', insurance_expiry: '2026-09-30', mileage: 67800, fuel_type: '汽油', load_capacity: 1.8 },
  { id: 5, plate_number: '苏A·56789', brand: '福田', model: '欧马可S3', vehicle_type: '货车', enterprise_id: 3, enterprise_name: '通达运输队', driver: '吴涛', driver_phone: '13200132005', status: 'inactive', annual_check_date: '2025-08-20', insurance_expiry: '2026-02-28', mileage: 91200, fuel_type: '柴油', load_capacity: 6.0 },
];

const mockFunds = [
  { id: 1, enterprise_id: 1, enterprise_name: '顺达物流有限公司', account_name: '顺达运营资金', account_type: '运营账户', balance: 485600.50, status: 'active', bank_name: '中国工商银行', bank_account: '6222****1234', currency: '¥' },
  { id: 2, enterprise_id: 1, enterprise_name: '顺达物流有限公司', account_name: '顺达维修基金', account_type: '维修基金', balance: 120000.00, status: 'active', bank_name: '中国建设银行', bank_account: '6227****5678', currency: '¥' },
  { id: 3, enterprise_id: 2, enterprise_name: '鹏程货运公司', account_name: '鹏程结算账户', account_type: '结算账户', balance: 325000.75, status: 'active', bank_name: '中国银行', bank_account: '6217****9012', currency: '¥' },
  { id: 4, enterprise_id: 2, enterprise_name: '鹏程货运公司', account_name: '鹏程备用金', account_type: '备用金', balance: 50000.00, status: 'frozen', bank_name: '中国农业银行', bank_account: '6228****3456', currency: '¥', description: '审计冻结中' },
  { id: 5, enterprise_id: 3, enterprise_name: '通达运输队', account_name: '通达保证金', account_type: '保证金', balance: 80000.00, status: 'inactive', bank_name: '交通银行', bank_account: '6222****7890', currency: '¥' },
];

// ═══════════════════════════════════════════
// Mock API
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

// dayjs is used for date formatting in the Fleet page
vi.mock('dayjs', () => {
  const actual = vi.importActual('dayjs');
  return {
    default: actual,
  };
});

import FleetPage from '../index';

// ═══════════════════════════════════════════
// beforeEach
// ═══════════════════════════════════════════
beforeEach(() => {
  // 关键：重置 jsdom URL。FleetPage 用 useSearchParams 读 ?tab 决定 activeTab，
  // 而前序用例的 clickTab→setSearchParams 会写 window.history；
  // BrowserRouter mount 时读 window.location → 拿到上一用例残留的脏 ?tab →
  // activeTab≠enterprises → 企业表格不渲染 → findByText('顺达物流') 超时。
  // 同文件内用例共享 jsdom，必须每用例手动归位。
  window.history.replaceState({}, '', '/');
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url: string) => {
    if (url === '/fleet/enterprises') return Promise.resolve({ data: mockEnterprises });
    if (url === '/fleet/drivers') return Promise.resolve({ data: { items: [] } });
    // FleetVehiclesPage 用企业维度接口（后端字段 driver_name），由 mockVehicles 映射
    if (url.includes('/enterprises/') && url.includes('/vehicles')) {
      const items = mockVehicles.map(v => ({ ...v, driver_name: v.driver, vin: `VIN${v.id}` }));
      return Promise.resolve({ data: { items, total: items.length } });
    }
    if (url === '/fleet/funds') return Promise.resolve({ data: mockFunds });
    return Promise.resolve({ data: [] });
  });
  mockApi.post.mockResolvedValue({});
  mockApi.put.mockResolvedValue({});
  mockApi.delete.mockResolvedValue({});
  mockApi.patch.mockResolvedValue({});
});

// ═══════════════════════════════════════════
// 辅助：点击 Ant Design Tab
// ═══════════════════════════════════════════
function clickTab(label: string) {
  const tabs = document.querySelectorAll('.ant-tabs-tab');
  for (let i = 0; i < tabs.length; i++) {
    if (tabs[i].textContent?.includes(label)) {
      fireEvent.click(tabs[i]);
      return;
    }
  }
}

// ═══════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════

describe('车队管理 — 渲染', () => {
  it('页面可渲染不崩溃', () => {
    const { container } = render(<BrowserRouter><FleetPage /></BrowserRouter>);
    expect(container).toBeTruthy();
  });

  it('默认显示车队企业Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('车队企业')).toBeInTheDocument();
    });
    expect(screen.getByText('车辆管理')).toBeInTheDocument();
    expect(screen.getByText('资金账户')).toBeInTheDocument();
  });

  it('加载后企业表格渲染数据', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    expect(await screen.findByText('顺达物流有限公司')).toBeInTheDocument();
    expect(screen.getByText('鹏程货运公司')).toBeInTheDocument();
    expect(screen.getByText('通达运输队')).toBeInTheDocument();
    expect(screen.getByText('TL-FLEET-001')).toBeInTheDocument();
  });

  it('统计卡片显示', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');
    expect(screen.getByText('企业总数')).toBeInTheDocument();
    expect(screen.getByText('活跃企业')).toBeInTheDocument();
  });
});

describe('车队管理 — Tab切换', () => {
  it('切换到车辆管理Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');

    clickTab('车辆管理');

    await waitFor(() => {
      expect(screen.getByText('豫A·12345')).toBeInTheDocument();
    });
    expect(screen.getByText(/比亚迪/)).toBeInTheDocument();
  });

  it('切换到资金账户Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');

    clickTab('资金账户');

    await waitFor(() => {
      expect(screen.getByText('顺达运营资金')).toBeInTheDocument();
    });
    expect(screen.getByText('鹏程结算账户')).toBeInTheDocument();
  });

  it('在三个Tab之间来回切换', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');

    // 企业 → 车辆
    clickTab('车辆管理');
    await waitFor(() => expect(screen.getByText('豫A·12345')).toBeInTheDocument());

    // 车辆 → 资金
    clickTab('资金账户');
    await waitFor(() => expect(screen.getByText('顺达运营资金')).toBeInTheDocument());

    // 资金 → 企业（切换回来后，顺达物流 appears in multiple tabs）
    clickTab('车队企业');
    await waitFor(() => expect(screen.getAllByText('顺达物流有限公司').length).toBeGreaterThanOrEqual(1));
  });
});

describe('车队管理 — 车辆表格', () => {
  it('车辆Tab显示5条数据', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');

    clickTab('车辆管理');

    await waitFor(() => {
      expect(screen.getByText('豫A·12345')).toBeInTheDocument();
    });
    expect(screen.getByText('豫A·23456')).toBeInTheDocument();
    expect(screen.getByText('粤B·34567')).toBeInTheDocument();
    expect(screen.getByText('粤B·45678')).toBeInTheDocument();
    expect(screen.getByText('苏A·56789')).toBeInTheDocument();
  });

  it('车辆统计卡片显示正确', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');
    clickTab('车辆管理');
    await waitFor(() => expect(screen.getByText('豫A·12345')).toBeInTheDocument());

    expect(screen.getByText('车辆总数')).toBeInTheDocument();
    // FleetVehiclesPage 统计卡片标题为「在役」「维修中」
    expect(screen.getAllByText('在役').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('维修中')).toBeInTheDocument();
  });
});

describe('车队管理 — 资金表格', () => {
  it('资金账户Tab显示5条数据', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');

    clickTab('资金账户');

    await waitFor(() => {
      expect(screen.getByText('顺达运营资金')).toBeInTheDocument();
    });
    expect(screen.getByText('顺达维修基金')).toBeInTheDocument();
    expect(screen.getByText('鹏程结算账户')).toBeInTheDocument();
    expect(screen.getByText('鹏程备用金')).toBeInTheDocument();
    expect(screen.getByText('通达保证金')).toBeInTheDocument();
  });

  it('资金统计卡片显示正确', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');
    clickTab('资金账户');
    await waitFor(() => expect(screen.getByText('顺达运营资金')).toBeInTheDocument());

    expect(screen.getByText('账户总数')).toBeInTheDocument();
    expect(screen.getByText('正常账户')).toBeInTheDocument();
    expect(screen.getByText('总余额')).toBeInTheDocument();
  });
});

describe('车队管理 — 搜索筛选', () => {
  it('企业Tab搜索企业名称过滤', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');

    const searchInput = screen.getByPlaceholderText('搜索企业名称/编码');
    fireEvent.change(searchInput, { target: { value: '顺达' } });

    await waitFor(() => {
      expect(screen.getByText('顺达物流有限公司')).toBeInTheDocument();
    });
    expect(screen.queryByText('鹏程货运公司')).not.toBeInTheDocument();
  });

  it('车辆Tab搜索车牌号过滤', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');
    clickTab('车辆管理');
    await waitFor(() => expect(screen.getByText('豫A·12345')).toBeInTheDocument());

    const searchInput = screen.getByPlaceholderText('搜索车牌/VIN/司机');
    fireEvent.change(searchInput, { target: { value: '豫A·12345' } });

    await waitFor(() => {
      expect(screen.getByText('豫A·12345')).toBeInTheDocument();
    });
    expect(screen.queryByText('豫A·23456')).not.toBeInTheDocument();
  });

  it('资金Tab搜索账户名称过滤', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');
    clickTab('资金账户');
    await waitFor(() => expect(screen.getByText('顺达运营资金')).toBeInTheDocument());

    const searchInput = screen.getByPlaceholderText('搜索账户/企业');
    fireEvent.change(searchInput, { target: { value: '鹏程' } });

    await waitFor(() => {
      expect(screen.getByText('鹏程结算账户')).toBeInTheDocument();
    });
    expect(screen.queryByText('顺达运营资金')).not.toBeInTheDocument();
  });

  it('企业Tab清空搜索恢复全部', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');

    const searchInput = screen.getByPlaceholderText('搜索企业名称/编码');
    fireEvent.change(searchInput, { target: { value: '顺达' } });
    await waitFor(() => {
      expect(screen.queryByText('鹏程货运公司')).not.toBeInTheDocument();
    });

    fireEvent.change(searchInput, { target: { value: '' } });
    await waitFor(() => {
      expect(screen.getByText('通达运输队')).toBeInTheDocument();
    });
  });
});

describe('车队管理 — 状态标签', () => {
  it('企业状态标签正确', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');
    // active → 启用, inactive → 停用
    expect(screen.getAllByText('启用').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('停用')).toBeInTheDocument();
  });

  it('车辆状态标签正确', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');
    clickTab('车辆管理');
    await waitFor(() => expect(screen.getByText('豫A·12345')).toBeInTheDocument());

    // FleetVehiclesPage 状态文本：active→在役, maintenance→维修, inactive→停用
    expect(screen.getAllByText('在役').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('维修').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('停用').length).toBeGreaterThanOrEqual(1);
  });

  it('资金账户状态标签正确', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');
    clickTab('资金账户');
    await waitFor(() => expect(screen.getByText('顺达运营资金')).toBeInTheDocument());

    // active → 启用, frozen → 已冻结, inactive → 停用
    expect(screen.getAllByText('启用').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('已冻结')).toBeInTheDocument();
    expect(screen.getAllByText('停用').length).toBeGreaterThanOrEqual(1);
  });
});

// ═══════════════════════════════════════════
// API 失败 — 错误态（卡947d83d7：禁止catch回退mock假数据）
// ═══════════════════════════════════════════
describe('车队管理 — API失败错误态', () => {
  it('企业接口失败渲染错误提示+空表，不渲染假数据', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url === '/fleet/enterprises') return Promise.reject(new Error('Network Error'));
      if (url === '/fleet/funds') return Promise.resolve({ data: mockFunds });
      return Promise.resolve({ data: [] });
    });
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    // 错误提示出现
    expect(await screen.findByText('车队企业加载失败')).toBeInTheDocument();
    expect(await screen.findByText('Network Error')).toBeInTheDocument();
    // 假数据不出现
    expect(screen.queryByText('顺达物流有限公司')).not.toBeInTheDocument();
    expect(screen.queryByText('鹏程货运公司')).not.toBeInTheDocument();
    expect(screen.queryByText('通达运输队')).not.toBeInTheDocument();
    // 重试按钮存在
    expect(screen.getByText('重试')).toBeInTheDocument();
  });

  it('资金接口失败渲染错误提示+空表，不渲染假数据', async () => {
    window.history.replaceState({}, '', '/?tab=funds');
    mockApi.get.mockImplementation((url: string) => {
      if (url === '/fleet/funds') return Promise.reject(Object.assign(new Error('服务不可用'), { response: { data: { message: '服务不可用' } } }));
      if (url === '/fleet/enterprises') return Promise.resolve({ data: mockEnterprises });
      return Promise.resolve({ data: [] });
    });
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    expect(await screen.findByText('资金账户加载失败')).toBeInTheDocument();
    expect(screen.queryByText('顺达运营资金')).not.toBeInTheDocument();
    expect(screen.queryByText('鹏程结算账户')).not.toBeInTheDocument();
    expect(screen.queryByText('通达保证金')).not.toBeInTheDocument();
    expect(screen.getByText('重试')).toBeInTheDocument();
    window.history.replaceState({}, '', '/');
  });
});

// ═══════════════════════════════════════════
// 移动端响应式布局（Phase1）
// ═══════════════════════════════════════════
describe('车队管理 — 移动端响应式布局', () => {
  it('企业/资金统计卡片采用响应式 Col（移动端2列）', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');
    // 统计卡片 Col 为 xs={12} sm={6}，移动端纵向2列
    expect(document.querySelector('.ant-col-xs-12')).toBeInTheDocument();
  });

  it('新增企业 Modal 表单采用响应式 Col（移动端纵向）', async () => {
    await act(async () => {
      render(<BrowserRouter><FleetPage /></BrowserRouter>);
    });
    await screen.findByText('顺达物流有限公司');

    fireEvent.click(screen.getByText('新增企业'));

    // Modal 打开后，表单 Col 由固定 span={12} 改为 xs={24} sm={12}（移动端纵向）
    // 注：用 .ant-modal/.ant-col-xs-24 而非 getByText('企业名称')，避免 Form.Item
    // label 同时渲染文本与 title 属性导致的多元素匹配
    await waitFor(() => {
      expect(document.querySelector('.ant-modal')).toBeInTheDocument();
      expect(document.querySelector('.ant-col-xs-24')).toBeInTheDocument();
    });
  });
});
