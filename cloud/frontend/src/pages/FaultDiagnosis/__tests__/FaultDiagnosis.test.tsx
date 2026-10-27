/**
 * FaultDiagnosis — Vitest 组件测试
 * 测试: 页面渲染 + 故障码列表 + AI诊断 Tab + 活跃告警 Tab
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import React from 'react';

// ═══ Mock API ═══
const { mockFaultDiagnosisAPI, mockAlarmAPI } = vi.hoisted(() => ({
  mockFaultDiagnosisAPI: {
    faultCodes: vi.fn(),
    getFaultCode: vi.fn(),
    alarmDiagnosis: vi.fn(),
    quickDiagnosis: vi.fn(),
    remoteFix: vi.fn(),
    faultStatistics: vi.fn(),
    initFaultCodes: vi.fn(),
  },
  mockAlarmAPI: {
    list: vi.fn(),
    get: vi.fn(),
    ack: vi.fn(),
    resolve: vi.fn(),
    ignore: vi.fn(),
    del: vi.fn(),
    stats: vi.fn(),
    rules: {
      list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), del: vi.fn(), toggle: vi.fn(), evaluate: vi.fn(),
    },
    ruleLogs: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  faultDiagnosisAPI: mockFaultDiagnosisAPI,
  alarmAPI: mockAlarmAPI,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } };
});

import FaultDiagnosisPage from '../index';

// ═══ beforeEach ═══
beforeEach(() => {
  vi.clearAllMocks();
  mockFaultDiagnosisAPI.faultCodes.mockResolvedValue({
    items: [
      {
        fault_code: 'E001',
        fault_name: '电网过压',
        fault_description: '电网电压超过额定值10%',
        device_type: 'inverter',
        fault_category: 'GRID',
        fault_level: 'WARNING_SERIOUS',
        response_time_minutes: 30,
        auto_stop: true,
        remote_fixable: false,
        possible_causes: ['电网波动', '变压器故障'],
        diagnosis_steps: ['检查电网电压', '确认变压器状态'],
        repair_suggestions: ['联系电网公司', '检修变压器'],
      },
      {
        fault_code: 'E002',
        fault_name: '电池过温',
        fault_description: '电池温度超过安全阈值',
        device_type: 'battery',
        fault_category: 'TEMPERATURE',
        fault_level: 'EMERGENCY',
        response_time_minutes: 5,
        auto_stop: true,
        remote_fixable: true,
        possible_causes: ['散热系统故障', '环境温度过高'],
        diagnosis_steps: ['检查散热风扇', '检查环境温度'],
        repair_suggestions: ['更换散热风扇', '改善通风'],
      },
    ],
  });
  mockAlarmAPI.list.mockResolvedValue({
    items: [
      { id: 1, device_id: 10, device_name: '逆变器010', fault_code: 'E001', fault_name: '电网过压', fault_level: 'WARNING_SERIOUS', status: 'ACTIVE', content: '电网电压超标' },
    ],
  });
});

// ═══ Tests ═══

describe('FaultDiagnosis 页面', () => {
  it('渲染 3 个 Tab（故障码知识库、活跃告警、AI智能诊断）', async () => {
    await act(async () => {
      render(<BrowserRouter><FaultDiagnosisPage /></BrowserRouter>);
    });
    // Tab labels
    const faultTabs = screen.getAllByText('故障码知识库');
    expect(faultTabs.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('活跃告警')).toBeInTheDocument();
    expect(screen.getByText('AI智能诊断')).toBeInTheDocument();
  });

  it('默认显示故障码知识库 Tab 且渲染故障码数据', async () => {
    await act(async () => {
      render(<BrowserRouter><FaultDiagnosisPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('电网过压')).toBeInTheDocument();
    });
    expect(screen.getByText('电池过温')).toBeInTheDocument();
  });

  it('渲染 AI 诊断 Tab 标签', async () => {
    await act(async () => {
      render(<BrowserRouter><FaultDiagnosisPage /></BrowserRouter>);
    });
    expect(screen.getByText('AI智能诊断')).toBeInTheDocument();
  });

  it('故障码列表包含故障等级标签', async () => {
    await act(async () => {
      render(<BrowserRouter><FaultDiagnosisPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('严重告警')).toBeInTheDocument();
    });
    expect(screen.getByText('紧急')).toBeInTheDocument();
  });

  it('点击查看故障码详情弹出 Modal', async () => {
    await act(async () => {
      render(<BrowserRouter><FaultDiagnosisPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('电网过压')).toBeInTheDocument();
    });

    // Click the first "查看详情" button
    const viewButtons = screen.getAllByText('查看详情');
    expect(viewButtons.length).toBeGreaterThan(0);
    await act(async () => {
      fireEvent.click(viewButtons[0]);
    });
    await waitFor(() => {
      expect(document.querySelector('.ant-modal')).toBeTruthy();
    });
  });

  it('切换到活跃告警 Tab', async () => {
    await act(async () => {
      render(<BrowserRouter><FaultDiagnosisPage /></BrowserRouter>);
    });
    await waitFor(() => {
      expect(screen.getByText('电网过压')).toBeInTheDocument();
    });

    // Click the tab (use getAllByText since '活跃告警' appears in both tab and card title)
    const alarmTabs = screen.getAllByText('活跃告警');
    const alarmTab = alarmTabs.find(el => el.closest('.ant-tabs-tab'));
    await act(async () => {
      fireEvent.click(alarmTab!);
    });

    await waitFor(() => {
      const tab = screen.getAllByText('活跃告警').find(el => el.closest('.ant-tabs-tab'));
      expect(tab?.closest('.ant-tabs-tab')?.classList.contains('ant-tabs-tab-active')).toBe(true);
    });
  });
});
