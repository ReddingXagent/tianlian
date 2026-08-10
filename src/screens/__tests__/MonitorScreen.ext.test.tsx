/**
 * MonitorScreen 扩展测试 — 分支覆盖率提升
 * 目标: 61% → 80%+ branches
 */
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import MonitorScreen from '../MonitorScreen';
import { monitorApi, deviceMonitorApi } from '../../services/api';

jest.mock('../../services/api', () => ({
  monitorApi: {
    getSummary: jest.fn(),
    getFaultDevices: jest.fn(),
    getCriticalAlarms: jest.fn(),
  },
  deviceMonitorApi: {
    getDeviceStatusList: jest.fn(),
    getRealtimeMetrics: jest.fn(),
  },
}));

const SUMMARY = {
  totalDevices: 10, onlineDevices: 7, faultDevices: 2, criticalAlarms: 1,
};
const DEVICE = {
  id: 1, stationId: 1, stationName: '充电站A', name: '设备一', code: 'D1',
  type: 'charger', status: 'online', model: 'M1', manufacturer: 'X',
  lastHeartbeat: '2024-01-15T10:00:00Z', createdAt: '', updatedAt: '',
};
const FAULT_DEVICE = {
  id: 2, stationId: 1, stationName: '充电站B', name: '故障设备二', code: 'D2',
  type: 'inverter', status: 'fault', model: 'M2', manufacturer: 'Y',
  lastHeartbeat: '2024-01-14T10:00:00Z', createdAt: '', updatedAt: '',
};
const CRITICAL_ALARM = {
  id: 1, stationId: 1, stationName: '充电站A', type: 'device_fault',
  level: 'critical', title: '严重告警A', description: '严重告警描述',
  status: 'unhandled', createdAt: '2024-01-15T10:00:00Z', updatedAt: '',
};
const METRICS = {
  deviceId: 1, deviceName: '设备一', temperature: 45, voltage: 220,
  current: 10, power: 2200, status: 'online', lastUpdated: '2024-01-15T10:05:00Z',
};

function setupMocks(opts?: {
  devices?: Record<string, unknown>[]; faults?: Record<string, unknown>[]; alarms?: Record<string, unknown>[]; metrics?: Record<string, unknown>[];
  summaryError?: boolean;
}) {
  if (opts?.summaryError) {
    (monitorApi.getSummary as jest.Mock).mockRejectedValue(new Error('net'));
    (deviceMonitorApi.getDeviceStatusList as jest.Mock).mockRejectedValue(new Error('net'));
  } else {
    (monitorApi.getSummary as jest.Mock).mockResolvedValue({ data: SUMMARY });
    (deviceMonitorApi.getDeviceStatusList as jest.Mock).mockResolvedValue({
      data: { items: opts?.devices ?? [DEVICE], total: (opts?.devices ?? [DEVICE]).length, page: 1, pageSize: 50 },
    });
  }
  (monitorApi.getFaultDevices as jest.Mock).mockResolvedValue({
    data: { items: opts?.faults ?? [FAULT_DEVICE], total: (opts?.faults ?? [FAULT_DEVICE]).length, page: 1, pageSize: 20 },
  });
  (monitorApi.getCriticalAlarms as jest.Mock).mockResolvedValue({
    data: { items: opts?.alarms ?? [CRITICAL_ALARM], total: (opts?.alarms ?? [CRITICAL_ALARM]).length, page: 1, pageSize: 20 },
  });
  (deviceMonitorApi.getRealtimeMetrics as jest.Mock).mockResolvedValue({
    data: opts?.metrics ?? [METRICS],
  });
}

describe('MonitorScreen.ext', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setupMocks();
  });

  it('renders metrics with realtime data', async () => {
    const { findByText } = render(<MonitorScreen />);
    await findByText('设备一');
    await waitFor(() => {
      expect(deviceMonitorApi.getRealtimeMetrics).toHaveBeenCalled();
    });
  });

  it('renders high temperature metric (>65)', async () => {
    setupMocks({ metrics: [{ ...METRICS, temperature: 70 }] });
    const { findByText } = render(<MonitorScreen />);
    await findByText('设备一');
    await waitFor(() => {
      expect(deviceMonitorApi.getRealtimeMetrics).toHaveBeenCalled();
    });
  });

  it('renders medium temperature (>50)', async () => {
    setupMocks({ metrics: [{ ...METRICS, temperature: 55 }] });
    const { findByText } = render(<MonitorScreen />);
    await findByText('设备一');
    await waitFor(() => {
      expect(deviceMonitorApi.getRealtimeMetrics).toHaveBeenCalled();
    });
  });

  it('shows empty fault state', async () => {
    setupMocks({ faults: [] });
    const { findByText } = render(<MonitorScreen />);
    fireEvent.press(await findByText('故障设备'));
    expect(await findByText('暂无故障设备')).toBeTruthy();
  });

  it('shows empty alarm state', async () => {
    setupMocks({ alarms: [] });
    const { findByText, findAllByText } = render(<MonitorScreen />);
    await findByText('监控概览');
    const tabs = await findAllByText('严重告警');
    fireEvent.press(tabs[tabs.length - 1]);
    expect(await findByText('暂无严重告警')).toBeTruthy();
  });

  it('error: shows retry button', async () => {
    setupMocks({ summaryError: true });
    const { findByText } = render(<MonitorScreen />);
    expect(await findByText('重新加载')).toBeTruthy();
  });

  it('error+retry triggers new fetch', async () => {
    setupMocks({ summaryError: true });
    const { findByText } = render(<MonitorScreen />);
    await findByText('重新加载');
    (monitorApi.getSummary as jest.Mock).mockResolvedValue({ data: SUMMARY });
    (deviceMonitorApi.getDeviceStatusList as jest.Mock).mockResolvedValue({
      data: { items: [DEVICE], total: 1, page: 1, pageSize: 50 },
    });
    (monitorApi.getFaultDevices as jest.Mock).mockResolvedValue({
      data: { items: [FAULT_DEVICE], total: 1, page: 1, pageSize: 20 },
    });
    (monitorApi.getCriticalAlarms as jest.Mock).mockResolvedValue({
      data: { items: [CRITICAL_ALARM], total: 1, page: 1, pageSize: 20 },
    });
    fireEvent.press(await findByText('重新加载'));
    await waitFor(() => {
      expect(monitorApi.getSummary).toHaveBeenCalledTimes(2);
    });
  });

  it('renders totalDevices number', async () => {
    const { findByText } = render(<MonitorScreen />);
    expect(await findByText('10')).toBeTruthy();
  });

  it('fault tab renders fault device', async () => {
    const { findByText } = render(<MonitorScreen />);
    fireEvent.press(await findByText('故障设备'));
    expect(await findByText('故障设备二')).toBeTruthy();
  });

  it('alarm tab renders critical alarm', async () => {
    const { findByText, findAllByText } = render(<MonitorScreen />);
    await findByText('监控概览');
    const tabs = await findAllByText('严重告警');
    fireEvent.press(tabs[tabs.length - 1]);
    expect(await findByText('严重告警A')).toBeTruthy();
  });

  it('devices tab empty state', async () => {
    setupMocks({ devices: [] });
    const { findByText } = render(<MonitorScreen />);
    expect(await findByText('暂无设备')).toBeTruthy();
  });

  it('fault tab stationId fallback', async () => {
    setupMocks({ faults: [{ ...FAULT_DEVICE, stationName: '' }] });
    const { findByText } = render(<MonitorScreen />);
    fireEvent.press(await findByText('故障设备'));
    expect(await findByText('故障设备二')).toBeTruthy();
  });
});
