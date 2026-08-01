import { render, fireEvent } from '@testing-library/react-native';
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
  totalDevices: 10,
  onlineDevices: 7,
  faultDevices: 2,
  criticalAlarms: 1,
};

const DEVICE = {
  id: 1,
  stationId: 1,
  stationName: '充电站A',
  name: '设备一',
  code: 'D1',
  type: 'charger',
  status: 'online',
  model: 'M1',
  manufacturer: 'X',
  lastHeartbeat: '2024-01-15T10:00:00Z',
  createdAt: '',
  updatedAt: '',
};

const FAULT_DEVICE = {
  id: 2,
  stationId: 1,
  stationName: '充电站B',
  name: '故障设备二',
  code: 'D2',
  type: 'inverter',
  status: 'fault',
  model: 'M2',
  manufacturer: 'Y',
  lastHeartbeat: '2024-01-14T10:00:00Z',
  createdAt: '',
  updatedAt: '',
};

const CRITICAL_ALARM = {
  id: 1,
  stationId: 1,
  stationName: '充电站A',
  type: 'device_fault',
  level: 'critical',
  title: '严重告警A',
  description: '严重告警描述',
  status: 'unhandled',
  createdAt: '2024-01-15T10:00:00Z',
  updatedAt: '',
};

describe('MonitorScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
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
    (deviceMonitorApi.getRealtimeMetrics as jest.Mock).mockResolvedValue({
      data: [],
    });
  });

  it('shows loading spinner initially', () => {
    (monitorApi.getSummary as jest.Mock).mockImplementation(
      () => new Promise(() => {})
    );
    const { getByText } = render(<MonitorScreen />);
    expect(getByText('加载监控数据...')).toBeTruthy();
  });

  it('renders summary and device list', async () => {
    const { findByText } = render(<MonitorScreen />);
    expect(await findByText('监控概览')).toBeTruthy();
    expect(await findByText('设备一')).toBeTruthy();
  });

  it('switches to the faults tab', async () => {
    const { findByText } = render(<MonitorScreen />);
    fireEvent.press(await findByText('故障设备'));
    expect(await findByText('故障设备二')).toBeTruthy();
  });

  it('switches to the alarms tab', async () => {
    const { findAllByText, findByText } = render(<MonitorScreen />);
    const matches = await findAllByText('严重告警');
    fireEvent.press(matches[matches.length - 1]);
    expect(await findByText('严重告警A')).toBeTruthy();
  });

  it('shows error state when load fails', async () => {
    (monitorApi.getSummary as jest.Mock).mockRejectedValue(new Error('x'));
    const { findByText } = render(<MonitorScreen />);
    expect(await findByText('加载失败')).toBeTruthy();
  });

  it('shows empty device state when no devices', async () => {
    (deviceMonitorApi.getDeviceStatusList as jest.Mock).mockResolvedValue({
      data: { items: [], total: 0, page: 1, pageSize: 50 },
    });
    const { findByText } = render(<MonitorScreen />);
    expect(await findByText('暂无设备')).toBeTruthy();
  });
});
