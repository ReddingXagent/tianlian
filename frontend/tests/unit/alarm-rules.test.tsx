/**
 * AlarmRules 组件测试
 *
 * 测试告警规则配置 CRUD 操作
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock react-router-dom
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

// Mock antd message
vi.mock('antd', async () => {
  const actual = await vi.importActual('antd');
  return {
    ...actual,
    message: {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
    },
  };
});

// Mock the API
const mockRulesData = [
  {
    id: 1,
    name: '电池高温告警',
    description: '电池温度超过55度触发',
    device_type: 'battery',
    device_ids: [1, 2, 3],
    station_ids: [1],
    metric: 'battery_temperature',
    operator: '>',
    threshold: 55.0,
    duration: 0,
    level: 'warning',
    alarm_template: '{metric} = {value}, 超过阈值 {threshold}',
    notify_users: [1, 2],
    auto_create_workorder: false,
    workorder_priority: 'medium',
    enabled: true,
    silence_minutes: 5,
    created_at: '2025-01-01T00:00:00',
    updated_at: '2025-01-01T00:00:00',
  },
  {
    id: 2,
    name: '电网电压过高',
    description: 'A相电压超过260V触发',
    device_type: 'inverter',
    device_ids: null,
    station_ids: null,
    metric: 'grid_voltage_a',
    operator: '>=',
    threshold: 260.0,
    duration: 10,
    level: 'critical',
    alarm_template: '{metric} = {value}, 超过阈值 {threshold}',
    notify_users: [1, 2, 3],
    auto_create_workorder: true,
    workorder_priority: 'high',
    enabled: true,
    silence_minutes: 0,
    created_at: '2025-01-02T00:00:00',
    updated_at: '2025-01-02T00:00:00',
  },
  {
    id: 3,
    name: '低SOC',
    description: '',
    device_type: '',
    device_ids: null,
    station_ids: null,
    metric: 'battery_soc',
    operator: '<',
    threshold: 10.0,
    duration: 0,
    level: 'info',
    alarm_template: '{metric} = {value}, 超过阈值 {threshold}',
    notify_users: null,
    auto_create_workorder: false,
    workorder_priority: 'medium',
    enabled: false,
    silence_minutes: 0,
    created_at: '2025-01-03T00:00:00',
    updated_at: '2025-01-03T00:00:00',
  },
];

const mockRuleLogs = {
  items: [
    {
      id: 1,
      rule_id: 1,
      rule_name: '电池高温告警',
      device_id: 1,
      device_name: '逆变器001',
      station_id: 1,
      metric: 'battery_temperature',
      current_value: 60.0,
      threshold: 55.0,
      operator: '>',
      triggered: true,
      alarm_id: 100,
      reason: '',
      checked_at: '2025-01-01T12:00:00',
    },
  ],
};

vi.mock('../../src/api', () => ({
  alarmAPI: {
    rules: {
      list: vi.fn().mockResolvedValue({ data: mockRulesData }),
      get: vi.fn().mockImplementation((id: number) =>
        Promise.resolve({ data: mockRulesData.find((r) => r.id === id) })
      ),
      create: vi.fn().mockResolvedValue({
        data: { id: 4, name: '新规则', metric: 'pv_power_total', operator: '>', threshold: 100.0 },
      }),
      update: vi.fn().mockResolvedValue({ data: { id: 1, name: '更新后的规则' } }),
      del: vi.fn().mockResolvedValue({}),
      toggle: vi.fn().mockResolvedValue({
        data: { ...mockRulesData[0], enabled: !mockRulesData[0].enabled },
      }),
      evaluate: vi.fn().mockResolvedValue({
        data: { triggered: false, message: '未触发', rule_id: 1 },
      }),
    },
    ruleLogs: vi.fn().mockResolvedValue({ data: mockRuleLogs }),
  },
}));

// Mock i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'pages.alarms.all_types': '全部类型',
        'pages.devices.type_pv_inverter': '光伏逆变器',
        'pages.devices.type_pcs': '储能变流器',
        'pages.devices.type_battery': '电池',
        'pages.devices.type_charger_dc': '直流桩',
      };
      return translations[key] || key;
    },
    i18n: { language: 'zh-CN' },
  }),
}));

describe('AlarmRules Component', () => {
  let AlarmRulesTab: any;

  beforeAll(async () => {
    const mod = await import('../../src/pages/Alarms/AlarmRules');
    AlarmRulesTab = mod.default;
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render the component without crashing', async () => {
    const { container } = render(<AlarmRulesTab />);
    expect(container).toBeTruthy();
  });

  it('should show "新建规则" button', async () => {
    render(<AlarmRulesTab />);
    await waitFor(() => {
      expect(screen.getByText('新建规则')).toBeInTheDocument();
    });
  });

  it('should show "刷新" button', async () => {
    render(<AlarmRulesTab />);
    await waitFor(() => {
      expect(screen.getByText('刷新')).toBeInTheDocument();
    });
  });

  it('should show "触发日志" button', async () => {
    render(<AlarmRulesTab />);
    await waitFor(() => {
      expect(screen.getByText('触发日志')).toBeInTheDocument();
    });
  });

  it('should load and display alarm rules in table', async () => {
    render(<AlarmRulesTab />);
    await waitFor(() => {
      expect(screen.getByText('电池高温告警')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('电网电压过高')).toBeInTheDocument();
    });
  });

  it('should display rule levels with correct colors', async () => {
    render(<AlarmRulesTab />);
    await waitFor(() => {
      // Warning level
      expect(screen.getByText('警告')).toBeInTheDocument();
      // Critical level
      expect(screen.getByText('紧急')).toBeInTheDocument();
      // Info level
      expect(screen.getByText('提示')).toBeInTheDocument();
    });
  });

  it('should show enabled/disabled toggle button for each rule', async () => {
    render(<AlarmRulesTab />);
    await waitFor(() => {
      const disableButtons = screen.getAllByText('禁用');
      expect(disableButtons.length).toBeGreaterThan(0);
    });
  });

  it('should show edit button for each rule', async () => {
    render(<AlarmRulesTab />);
    await waitFor(() => {
      const editButtons = screen.getAllByText('编辑');
      expect(editButtons.length).toBeGreaterThan(0);
    });
  });

  it('should show evaluate buttons', async () => {
    render(<AlarmRulesTab />);
    await waitFor(() => {
      const triggerButtons = screen.getAllByText('触发');
      expect(triggerButtons.length).toBeGreaterThan(0);
    });
  });

  it('should open create modal when clicking 新建规则', async () => {
    const user = userEvent.setup();
    render(<AlarmRulesTab />);
    await waitFor(() => {
      expect(screen.getByText('新建规则')).toBeInTheDocument();
    });
    const createBtn = screen.getByText('新建规则');
    await user.click(createBtn);
    // "规则名称" appears both in table header and modal form label
    await waitFor(() => {
      const labels = screen.getAllByText('规则名称');
      expect(labels.length).toBeGreaterThanOrEqual(1);
    });
    // Modal title is present
    expect(screen.getByText('新建告警规则')).toBeInTheDocument();
  });

  it('should display condition info in table rows', async () => {
    render(<AlarmRulesTab />);
    await waitFor(() => {
      // The condition column shows metric label (Chinese) + operator + threshold in a Tag
      // e.g. "电池温度 (℃) > 55" or "电网电压过高 (≥ 260.0)"
      expect(screen.getByText(/55/)).toBeInTheDocument();
      // Should have device_type tags
      expect(screen.getByText('battery')).toBeInTheDocument();
    });
  });

  it('should show informational alert about rule evaluation schedule', async () => {
    render(<AlarmRulesTab />);
    await waitFor(() => {
      const alertText = screen.getByText(/告警规则引擎每分钟自动评估一次/);
      expect(alertText).toBeInTheDocument();
    });
  });
});
