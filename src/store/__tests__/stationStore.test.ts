import { act } from '@testing-library/react-native';
import { useStationStore } from '../../store/stationStore';
import { stationApi } from '../../services/api';
import { Station, Device, Alarm } from '../../types';

// Mock the API module
jest.mock('../../services/api', () => ({
  stationApi: {
    getList: jest.fn(),
    getDetail: jest.fn(),
    getDevices: jest.fn(),
    getAlarms: jest.fn(),
  },
}));

const MOCK_STATIONS: Station[] = [
  {
    id: 1,
    name: '充电站A',
    code: 'ST001',
    address: '深圳市南山区科技园',
    status: 'online',
    latitude: 22.5431,
    longitude: 113.9427,
    deviceCount: 10,
    onlineDeviceCount: 8,
    alarmCount: 2,
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-01T00:00:00Z',
  },
  {
    id: 2,
    name: '充电站B',
    code: 'ST002',
    address: '深圳市福田区华强北',
    status: 'offline',
    latitude: 22.5461,
    longitude: 114.0549,
    deviceCount: 5,
    onlineDeviceCount: 0,
    alarmCount: 1,
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-01T00:00:00Z',
  },
];

const MOCK_DETAIL_STATION: Station = {
  id: 1,
  name: '充电站A',
  code: 'ST001',
  address: '深圳市南山区科技园',
  status: 'online',
  latitude: 22.5431,
  longitude: 113.9427,
  deviceCount: 10,
  onlineDeviceCount: 8,
  alarmCount: 2,
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
};

describe('useStationStore', () => {
  beforeEach(() => {
    useStationStore.setState({
      stations: [],
      selectedStation: null,
      devices: [],
      alarms: [],
      total: 0,
      page: 1,
      loading: false,
      error: null,
    });
    jest.clearAllMocks();
  });

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useStationStore.getState();
      expect(state.stations).toEqual([]);
      expect(state.selectedStation).toBeNull();
      expect(state.devices).toEqual([]);
      expect(state.alarms).toEqual([]);
      expect(state.total).toBe(0);
      expect(state.page).toBe(1);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });
  });

  describe('fetchStations', () => {
    it('should fetch stations successfully', async () => {
      const response = {
        data: {
          items: MOCK_STATIONS,
          total: 2,
          page: 1,
          pageSize: 10,
        },
      };
      (stationApi.getList as jest.Mock).mockResolvedValue(response);

      await act(async () => {
        await useStationStore.getState().fetchStations({ page: 1, pageSize: 10 });
      });

      const state = useStationStore.getState();
      expect(state.stations).toEqual(MOCK_STATIONS);
      expect(state.total).toBe(2);
      expect(state.page).toBe(1);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('should handle fetch stations failure', async () => {
      const error = new Error('Network Error');
      (stationApi.getList as jest.Mock).mockRejectedValue(error);

      await act(async () => {
        await useStationStore.getState().fetchStations();
      });

      const state = useStationStore.getState();
      expect(state.stations).toEqual([]);
      expect(state.loading).toBe(false);
      expect(state.error).toBe('Network Error');
    });
  });

  describe('fetchStationDetail', () => {
    it('should fetch station detail successfully', async () => {
      const response = { data: MOCK_DETAIL_STATION };
      (stationApi.getDetail as jest.Mock).mockResolvedValue(response);

      await act(async () => {
        await useStationStore.getState().fetchStationDetail(1);
      });

      const state = useStationStore.getState();
      expect(state.selectedStation).toEqual(MOCK_DETAIL_STATION);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('should handle fetch station detail failure', async () => {
      const error = new Error('Station not found');
      (stationApi.getDetail as jest.Mock).mockRejectedValue(error);

      await act(async () => {
        await useStationStore.getState().fetchStationDetail(999);
      });

      const state = useStationStore.getState();
      expect(state.selectedStation).toBeNull();
      expect(state.loading).toBe(false);
      expect(state.error).toBe('Station not found');
    });
  });

  describe('fetchStationDevices', () => {
    const MOCK_DEVICES: Device[] = [
      { id: 1, stationId: 1, name: '充电桩1', code: 'DEV001', status: 'online', type: 'charger', model: 'DC-120kW', manufacturer: '特斯拉', lastHeartbeat: '2024-01-01T00:00:00Z', createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' },
      { id: 2, stationId: 1, name: '充电桩2', code: 'DEV002', status: 'offline', type: 'charger', model: 'AC-7kW', manufacturer: '比亚迪', lastHeartbeat: '2024-01-01T00:00:00Z', createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' },
    ];

    it('should fetch devices successfully', async () => {
      (stationApi.getDevices as jest.Mock).mockResolvedValue({ data: MOCK_DEVICES });

      await act(async () => {
        await useStationStore.getState().fetchStationDevices(1);
      });

      const state = useStationStore.getState();
      expect(stationApi.getDevices).toHaveBeenCalledWith(1);
      expect(state.devices).toEqual(MOCK_DEVICES);
      expect(state.error).toBeNull();
    });

    it('should handle fetch devices failure', async () => {
      (stationApi.getDevices as jest.Mock).mockRejectedValue(new Error('Network error'));

      await act(async () => {
        await useStationStore.getState().fetchStationDevices(1);
      });

      const state = useStationStore.getState();
      expect(state.error).toBe('Network error');
    });
  });

  describe('fetchStationAlarms', () => {
    const MOCK_ALARMS: Alarm[] = [
      { id: 1, stationId: 1, stationName: '充电站A', deviceId: 1, deviceName: '充电桩1', type: 'device_fault', level: 'critical', title: '过压告警', description: '电压超限', status: 'active', createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' },
      { id: 2, stationId: 1, stationName: '充电站A', deviceId: 2, deviceName: '充电桩2', type: 'communication_loss', level: 'warning', title: '通讯中断', description: '设备离线', status: 'active', createdAt: '2024-01-01T00:00:00Z', updatedAt: '2024-01-01T00:00:00Z' },
    ];

    it('should fetch alarms successfully', async () => {
      (stationApi.getAlarms as jest.Mock).mockResolvedValue({ data: { items: MOCK_ALARMS } });

      await act(async () => {
        await useStationStore.getState().fetchStationAlarms(1, { page: 1, pageSize: 20 });
      });

      const state = useStationStore.getState();
      expect(stationApi.getAlarms).toHaveBeenCalledWith(1, { page: 1, pageSize: 20 });
      expect(state.alarms).toEqual(MOCK_ALARMS);
    });

    it('should handle fetch alarms failure', async () => {
      (stationApi.getAlarms as jest.Mock).mockRejectedValue(new Error('Timeout'));

      await act(async () => {
        await useStationStore.getState().fetchStationAlarms(1);
      });

      const state = useStationStore.getState();
      expect(state.error).toBe('Timeout');
    });
  });

  describe('setSelectedStation', () => {
    it('should set selected station and clear devices/alarms', () => {
      useStationStore.setState({
        devices: [{ id: 99 } as Device],
        alarms: [{ id: 88 } as Alarm],
      });

      useStationStore.getState().setSelectedStation(MOCK_STATIONS[0]);

      const state = useStationStore.getState();
      expect(state.selectedStation).toEqual(MOCK_STATIONS[0]);
      expect(state.devices).toEqual([]);
      expect(state.alarms).toEqual([]);
    });

    it('should clear selected station when null', () => {
      useStationStore.setState({ selectedStation: MOCK_STATIONS[0] });

      useStationStore.getState().setSelectedStation(null);

      expect(useStationStore.getState().selectedStation).toBeNull();
    });
  });
});