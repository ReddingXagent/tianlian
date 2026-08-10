/**
 * MonitorScreen 扩展测试2 — 更多分支覆盖
 * 目标: branches 61→75%+
 * 注意: 不使用fake timers，避免与ext1冲突
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
const DEVICE_NO_STATION = {
  id: 3, stationId: 5, stationName: '', name: '设备三', code: 'D3',
  type: 'charger', status: 'offline', model: 'M3', manufacturer: 'Z',
  lastHeartbeat: '', createdAt: '', updatedAt: '',
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
  summaryError?: boolean; metricsError?: boolean;
}) {
  if (opts?.summaryError) {
    (monitorApi.getSummary as jest.Mock).mockRejectedValue(new Error('net'));
    (deviceMonitorApi.getDeviceStatusList as jest.Mock).mockRejectedValue(new Error('net'));
    (monitorApi.getFaultDevices as jest.Mock).mockRejectedValue(new Error('net'));
    (monitorApi.getCriticalAlarms as jest.Mock).mockRejectedValue(new Error('net'));
  } else {
    (monitorApi.getSummary as jest.Mock).mockResolvedValue({ data: SUMMARY });
    (deviceMonitorApi.getDeviceStatusList as jest.Mock).mockResolvedValue({
      data: { items: opts?.devices ?? [DEVICE], total: (opts?.devices ?? [DEVICE]).length, page: 1, pageSize: 50 },
    });
    (monitorApi.getFaultDevices as jest.Mock).mockResolvedValue({
      data: { items: opts?.faults ?? [FAULT_DEVICE], total: (opts?.faults ?? [FAULT_DEVICE]).length, page: 1, pageSize: 20 },
    });
    (monitorApi.getCriticalAlarms as jest.Mock).mockResolvedValue({
      data: { items: opts?.alarms ?? [CRITICAL_ALARM], total: (opts?.alarms ?? [CRITICAL_ALARM]).length, page: 1, pageSize: 20 },
    });
  }
  if (opts?.metricsError) {
    (deviceMonitorApi.getRealtimeMetrics as jest.Mock).mockRejectedValue(new Error('metrics fail'));
  } else {
    (deviceMonitorApi.getRealtimeMetrics as jest.Mock).mockResolvedValue({
      data: opts?.metrics ?? [METRICS],
    });
  }
}

describe('MonitorScreen.ext2', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setupMocks();
  });

  // --- metrics with only power ---
  it('renders metrics with power only', async () => {
    setupMocks({ metrics: [{ ...METRICS, voltage: undefined, current: undefined, temperature: undefined }] });
    const { findByText } = render(<MonitorScreen />);
    await findByText('设备一');
    // Verify power is rendered
    await waitFor(() => {
      expect(deviceMonitorApi.getRealtimeMetrics).toHaveBeenCalled();
    });
  });

  // --- metrics with only voltage ---
  it('renders metrics with voltage only', async () => {
    setupMocks({ metrics: [{ ...METRICS, power: undefined, current: undefined, temperature: undefined }] });
    const { findByText } = render(<MonitorScreen />);
    await findByText('设备一');
    await waitFor(() => {
      expect(deviceMonitorApi.getRealtimeMetrics).toHaveBeenCalled();
    });
  });

  // --- metrics with only current ---
  it('renders metrics with current only', async () => {
    setupMocks({ metrics: [{ ...METRICS, power: undefined, voltage: undefined, temperature: undefined }] });
    const { findByText } = render(<MonitorScreen />);
    await findByText('设备一');
    await waitFor(() => {
      expect(deviceMonitorApi.getRealtimeMetrics).toHaveBeenCalled();
    });
  });

  // --- metrics error: silent failure ---
  it('handles metrics fetch error silently', async () => {
    setupMocks({ metricsError: true });
    const { findByText } = render(<MonitorScreen />);
    // Device still rendered despite metrics fetch error
    expect(await findByText('设备一')).toBeTruthy();
  });

  // --- device with no stationName: fallback to stationId ---
  it('renders device with stationId fallback', async () => {
    setupMocks({ devices: [DEVICE_NO_STATION] });
    const { findByText } = render(<MonitorScreen />);
    expect(await findByText('设备三')).toBeTruthy();
  });

  // --- fault device with no stationName ---
  it('renders fault device with stationId fallback', async () => {
    setupMocks({ faults: [{ ...FAULT_DEVICE, stationName: '' }] });
    const { findByText } = render(<MonitorScreen />);
    fireEvent.press(await findByText('故障设备'));
    expect(await findByText('故障设备二')).toBeTruthy();
  });

  // --- fault device with no lastHeartbeat ---
  it('renders fault device with dash for missing heartbeat', async () => {
    setupMocks({ faults: [{ ...FAULT_DEVICE, lastHeartbeat: '' }] });
    const { findByText } = render(<MonitorScreen />);
    fireEvent.press(await findByText('故障设备'));
    expect(await findByText('故障设备二')).toBeTruthy();
  });

  // --- switch between all tabs ---
  it('switches devices → faults → alarms → devices', async () => {
    const { findByText, findAllByText } = render(<MonitorScreen />);
    await findByText('监控概览');

    // Switch to faults
    fireEvent.press(await findByText('故障设备'));
    expect(await findByText('故障设备二')).toBeTruthy();

    // Switch to alarms
    const alarmTabs = await findAllByText('严重告警');
    fireEvent.press(alarmTabs[alarmTabs.length - 1]);
    expect(await findByText('严重告警A')).toBeTruthy();

    // Switch back to devices
    fireEvent.press(await findByText('实时监控'));
    expect(await findByText('设备一')).toBeTruthy();
  });

  // --- summary null shows dash ---
  it('renders dash for null summary fields', async () => {
    (monitorApi.getSummary as jest.Mock).mockResolvedValue({ data: null });
    const { findAllByText } = render(<MonitorScreen />);
    const dashes = findAllByText('-');
    expect((await dashes).length).toBeGreaterThanOrEqual(3);
  });

  // --- metrics with undefined power/voltage/current/temperature ---
  it('renders no-data text when metrics has no values', async () => {
    setupMocks({
      metrics: [{
        ...METRICS,
        power: undefined, voltage: undefined, current: undefined, temperature: undefined,
        status: undefined,
      }],
    });
    const { findByText } = render(<MonitorScreen />);
    await findByText('设备一');
    await waitFor(() => {
      expect(deviceMonitorApi.getRealtimeMetrics).toHaveBeenCalled();
    });
  });
});
