/**
 * 车队扩展功能模块 — Vitest 组件测试
 *
 * 测试：充电策略 / 告警规则 / 司机考勤 / 碳核证 / 维保保险
 * 覆盖：渲染不崩溃 / 表格数据渲染 / 创建Modal打开 / API错误降级
 *
 * mock 模式对齐 fleet-modules.test.tsx；localStorage 模式对齐 settings.test.tsx
 * 字段契约对齐各模块源码（index.tsx 顶部注释的 API 与类型定义）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

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

vi.mock('echarts-for-react', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }, 'ECharts Mock'),
}));

// ═══════════════════════════════════════════
// 测试数据（字段对齐各模块 interface）
// ═══════════════════════════════════════════
const mockEnterprises = {
  items: [
    { id: 1, name: '顺达物流有限公司' },
    { id: 2, name: '鹏程货运公司' },
  ],
};

const mockDrivers = {
  items: [
    { id: 10, name: '张三', phone: '13800138001' },
    { id: 11, name: '李四', phone: '13900139002' },
  ],
};

const mockPolicies = {
  items: [
    { id: 1, enterprise_id: 1, daily_kwh_limit: 200, allowed_time_slots: ['峰', '平'], allowed_station_ids: [1, 2], enable: true },
    { id: 2, enterprise_id: 1, daily_kwh_limit: 0, allowed_time_slots: [], allowed_station_ids: [], enable: false },
  ],
};

const mockAlertRules = {
  items: [
    { id: 1, enterprise_id: 1, rule_type: 'low_battery', threshold: { soc_below: 20 }, notify_channels: ['im', 'sms'], enable: true },
    { id: 2, enterprise_id: 1, rule_type: 'overtime_parking', threshold: { hours: 48 }, notify_channels: [], enable: false },
  ],
};

const mockAlertRecords = {
  items: [
    { id: 1, rule_id: 1, enterprise_id: 1, vehicle_id: 101, plate_number: '京A12345', triggered_at: '2026-07-21T10:00:00', alert_value: 'SOC=15%', notified: true, status: 'active' },
  ],
};

const mockAttendanceRows = {
  items: [
    { id: 1, driver_id: 10, date: '2026-07-21', shift_type: 'day', hours: 8, status: 'normal', remark: '' },
    { id: 2, driver_id: 10, date: '2026-07-22', shift_type: 'night', hours: 7, status: 'late', remark: '堵车' },
  ],
};

const mockAttendanceSummary = {
  total_days: 22, total_hours: 176, normal_days: 18, late_days: 2, absent_days: 1, rest_days: 8, attendance_rate: 0.9,
};

const mockCerts = {
  items: [
    { id: 1, enterprise_id: 1, summary_id: 5, certificate_no: 'CR-2026-001', status: 'pending', verified_at: null, trade_volume: 0, trade_price: 0, created_at: '2026-07-01T08:00:00' },
    { id: 2, enterprise_id: 1, summary_id: 6, certificate_no: 'CR-2026-002', status: 'verified', verified_at: '2026-07-05T10:00:00', trade_volume: 0, trade_price: 0, created_at: '2026-07-02T08:00:00' },
  ],
};

const mockCarbonReports = {
  items: [
    { id: 5, report_year: 2026, report_month: 6, total_reduction_kg: 12500, verified: true },
  ],
};

const mockVehicles = {
  items: [
    { id: 101, plate_number: '京A12345' },
    { id: 102, plate_number: '京B67890' },
  ],
};

const mockMaintenances = {
  items: [
    { id: 1, vehicle_id: 101, type: 'maintenance', start_at: '2026-07-01', end_at: '2026-07-01', cost: 800.5, mileage: 50000, description: '常规保养', status: 'completed' },
  ],
};

// ═══════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════
const renderWithRouter = (component: React.ReactElement) =>
  render(<BrowserRouter>{component}</BrowserRouter>);

// 默认按 URL 路由返回各模块数据（更具体的路径必须先匹配）
const defaultGet = (url: string): Promise<any> => {
  if (url.includes('/fleet/enterprises')) return Promise.resolve({ data: mockEnterprises });
  if (url.includes('/fleet/drivers')) return Promise.resolve({ data: mockDrivers });
  if (url.includes('/fleet/policies/check')) return Promise.resolve({ data: { allowed: true, reason: '通过' } });
  if (url.includes('/fleet/policies')) return Promise.resolve({ data: mockPolicies });
  if (url.includes('/fleet/alert-records')) return Promise.resolve({ data: mockAlertRecords });
  if (url.includes('/fleet/alert-rules')) return Promise.resolve({ data: mockAlertRules });
  if (url.includes('/fleet/attendance/summary')) return Promise.resolve({ data: mockAttendanceSummary });
  if (url.includes('/fleet/attendance')) return Promise.resolve({ data: mockAttendanceRows });
  if (url.includes('/fleet/carbon/certificates')) return Promise.resolve({ data: mockCerts });
  if (url.includes('/fleet/carbon/reports')) return Promise.resolve({ data: mockCarbonReports });
  if (url.includes('/fleet/vehicles') && url.includes('/profile')) return Promise.resolve({ data: {} });
  if (url.includes('/fleet/vehicles') && url.includes('/maintenance')) return Promise.resolve({ data: mockMaintenances });
  if (url.includes('/fleet/vehicles') && url.includes('/insurance')) return Promise.resolve({ data: { items: [] } });
  if (url.includes('/vehicles')) return Promise.resolve({ data: mockVehicles });
  return Promise.resolve({ data: { items: [] } });
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mockApi.get.mockImplementation(defaultGet);
  mockApi.post.mockResolvedValue({ data: {} });
  mockApi.put.mockResolvedValue({ data: {} });
  mockApi.patch.mockResolvedValue({ data: {} });
  mockApi.delete.mockResolvedValue({ data: {} });
});

// ═══════════════════════════════════════════
// 1. 充电策略
// ═══════════════════════════════════════════
import FleetChargingPoliciesPage from '../ChargingPolicies';

describe('FleetChargingPoliciesPage 充电策略', () => {
  it('1. 渲染页面与统计卡片，拉取企业列表', async () => {
    renderWithRouter(<FleetChargingPoliciesPage />);

    await waitFor(() => {
      expect(screen.getByText('策略总数')).toBeInTheDocument();
    });
    expect(mockApi.get).toHaveBeenCalledWith('/fleet/enterprises');
  });

  it('2. 加载并显示策略列表（日限额/时段）', async () => {
    renderWithRouter(<FleetChargingPoliciesPage />);

    await waitFor(() => {
      expect(screen.getByText('200')).toBeInTheDocument(); // daily_kwh_limit=200
    }, { timeout: 3000 });
  });

  it('3. 点击「新增策略」打开创建Modal', async () => {
    renderWithRouter(<FleetChargingPoliciesPage />);

    await waitFor(() => expect(screen.getByText('新增策略')).toBeInTheDocument());
    fireEvent.click(screen.getByText('新增策略'));

    await waitFor(() => {
      expect(screen.getByText('新增充电策略')).toBeInTheDocument();
      expect(screen.getByText('日充电限额(kWh)')).toBeInTheDocument();
    });
  });

  it('4. 策略接口报错时降级为空态（不崩溃）', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/policies')) return Promise.reject(new Error('boom'));
      return defaultGet(url);
    });

    renderWithRouter(<FleetChargingPoliciesPage />);

    await waitFor(() => {
      expect(screen.getByText('暂无充电策略')).toBeInTheDocument();
    }, { timeout: 3000 });
  });
});

// ═══════════════════════════════════════════
// 2. 告警规则
// ═══════════════════════════════════════════
import FleetAlertRulesPage from '../AlertRules';

describe('FleetAlertRulesPage 告警规则', () => {
  it('1. 渲染页面与统计卡片', async () => {
    renderWithRouter(<FleetAlertRulesPage />);

    await waitFor(() => {
      expect(screen.getByText('规则总数')).toBeInTheDocument();
    });
  });

  it('2. 加载并显示规则列表（低电量规则）', async () => {
    renderWithRouter(<FleetAlertRulesPage />);

    await waitFor(() => {
      expect(screen.getByText('低电量')).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('3. 点击「新增规则」打开创建Modal', async () => {
    renderWithRouter(<FleetAlertRulesPage />);

    await waitFor(() => expect(screen.getByText('新增规则')).toBeInTheDocument());
    fireEvent.click(screen.getByText('新增规则'));

    await waitFor(() => {
      expect(screen.getByText('新增告警规则')).toBeInTheDocument();
      // required Form.Item 的「规则类型」label 会被 antd 渲染出带 title 的副本，故用 getAllByText 断言存在
      expect(screen.getAllByText('规则类型').length).toBeGreaterThan(0);
    });
  });

  it('4. 规则接口报错时降级为空态', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/alert-rules')) return Promise.reject(new Error('boom'));
      return defaultGet(url);
    });

    renderWithRouter(<FleetAlertRulesPage />);

    await waitFor(() => {
      expect(screen.getByText('暂无告警规则')).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('5. 切换到「告警记录」Tab并显示记录', async () => {
    renderWithRouter(<FleetAlertRulesPage />);

    await waitFor(() => expect(screen.getByText('规则管理')).toBeInTheDocument());
    fireEvent.click(screen.getByText('告警记录'));

    await waitFor(() => {
      expect(screen.getByText('京A12345')).toBeInTheDocument();
    }, { timeout: 3000 });
  });
});

// ═══════════════════════════════════════════
// 3. 司机考勤
// ═══════════════════════════════════════════
import FleetAttendancePage from '../Attendance';

describe('FleetAttendancePage 司机考勤', () => {
  it('1. 渲染页面与统计卡片，拉取司机列表', async () => {
    renderWithRouter(<FleetAttendancePage />);

    await waitFor(() => {
      expect(screen.getByText('出勤率')).toBeInTheDocument();
    });
    expect(mockApi.get).toHaveBeenCalledWith('/fleet/drivers');
  });

  it('2. 加载并显示月度考勤列表', async () => {
    renderWithRouter(<FleetAttendancePage />);

    await waitFor(() => {
      expect(screen.getByText('2026-07-21')).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('3. 点击「批量录入」打开Modal', async () => {
    renderWithRouter(<FleetAttendancePage />);

    await waitFor(() => expect(screen.getByText('批量录入')).toBeInTheDocument());
    fireEvent.click(screen.getByText('批量录入'));

    await waitFor(() => {
      expect(screen.getByText('批量录入考勤')).toBeInTheDocument();
      expect(screen.getByText('日期范围')).toBeInTheDocument();
    });
  });

  it('4. 考勤接口报错时降级为空态', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/attendance')) return Promise.reject(new Error('boom'));
      return defaultGet(url);
    });

    renderWithRouter(<FleetAttendancePage />);

    await waitFor(() => {
      expect(screen.getByText('本月暂无考勤记录')).toBeInTheDocument();
    }, { timeout: 3000 });
  });
});

// ═══════════════════════════════════════════
// 4. 碳核证
// ═══════════════════════════════════════════
import FleetCarbonCertificatesPage from '../CarbonCertificates';

describe('FleetCarbonCertificatesPage 碳核证', () => {
  it('1. 渲染页面与统计卡片', async () => {
    renderWithRouter(<FleetCarbonCertificatesPage />);

    await waitFor(() => {
      expect(screen.getByText('核证总数')).toBeInTheDocument();
    });
  });

  it('2. 加载并显示核证列表', async () => {
    renderWithRouter(<FleetCarbonCertificatesPage />);

    await waitFor(() => {
      expect(screen.getByText('CR-2026-001')).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('3. 点击「申请核证」打开Modal', async () => {
    renderWithRouter(<FleetCarbonCertificatesPage />);

    await waitFor(() => expect(screen.getByText('申请核证')).toBeInTheDocument());
    fireEvent.click(screen.getByText('申请核证'));

    await waitFor(() => {
      expect(screen.getByText('申请碳核证')).toBeInTheDocument();
      expect(screen.getByText('碳减排月度汇总')).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('4. 核证接口报错时降级为空态', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/carbon/certificates')) return Promise.reject(new Error('boom'));
      return defaultGet(url);
    });

    renderWithRouter(<FleetCarbonCertificatesPage />);

    await waitFor(() => {
      expect(screen.getByText('暂无碳核证记录')).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('5. 已核证记录可打开交易登记Modal', async () => {
    renderWithRouter(<FleetCarbonCertificatesPage />);

    await waitFor(() => expect(screen.getByText('CR-2026-002')).toBeInTheDocument(), { timeout: 3000 });
    fireEvent.click(screen.getByText('交易登记'));

    await waitFor(() => {
      expect(screen.getByText('交易量(吨CO₂)')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════
// 5. 维保保险
// ═══════════════════════════════════════════
import FleetVehicleMaintenancePage from '../VehicleMaintenance';

describe('FleetVehicleMaintenancePage 维保保险', () => {
  it('1. 渲染页面与统计卡片（企业→车辆联动）', async () => {
    renderWithRouter(<FleetVehicleMaintenancePage />);

    await waitFor(() => {
      expect(screen.getByText('维保次数')).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('2. 加载并显示维保记录列表', async () => {
    renderWithRouter(<FleetVehicleMaintenancePage />);

    await waitFor(() => {
      expect(screen.getByText('常规保养')).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('3. 点击「新增维保」打开创建Modal', async () => {
    renderWithRouter(<FleetVehicleMaintenancePage />);

    await waitFor(() => expect(screen.getByText('新增维保')).toBeInTheDocument(), { timeout: 3000 });
    fireEvent.click(screen.getByText('新增维保'));

    await waitFor(() => {
      expect(screen.getByText('新增维保记录')).toBeInTheDocument();
      expect(screen.getByText('维保类型')).toBeInTheDocument();
    });
  });

  it('4. 维保接口报错时不崩溃（保留工具条，无数据）', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes('/fleet/vehicles') && url.includes('/maintenance')) return Promise.reject(new Error('boom'));
      return defaultGet(url);
    });

    renderWithRouter(<FleetVehicleMaintenancePage />);

    // 该模块未配置 empty 空态，children 始终渲染 → 统计卡片仍在
    await waitFor(() => {
      expect(screen.getByText('维保次数')).toBeInTheDocument();
    }, { timeout: 3000 });
    expect(screen.queryByText('常规保养')).not.toBeInTheDocument();
  });
});
