import { stationApi } from '../../services/api';
import { useStationStore } from '../stationStore';
import { Station, PaginatedData } from '../../types';

jest.mock('../../services/api', () => ({
  stationApi: {
    getList: jest.fn(),
    search: jest.fn(),
    getDetail: jest.fn(),
    getChargers: jest.fn(),
  },
}));

const mockStations: Station[] = [
  {
    id: 1,
    name: '天链充电站-中心站',
    address: '北京市朝阳区建国路88号',
    status: 'online',
    latitude: 39.9042,
    longitude: 116.4074,
    distance: 500,
    pricePerKwh: 0.8,
    serviceFee: 0.5,
    totalConnectors: 10,
    availableConnectors: 3,
    chargingConnectors: 5,
    isOpen24h: true,
    rating: 4.5,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  },
  {
    id: 2,
    name: '天链充电站-南站',
    address: '北京市丰台区北京南站地下停车场',
    status: 'online',
    latitude: 39.865,
    longitude: 116.379,
    distance: 1500,
    pricePerKwh: 0.9,
    serviceFee: 0.4,
    totalConnectors: 8,
    availableConnectors: 0,
    chargingConnectors: 8,
    isOpen24h: true,
    rating: 4.2,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  },
];

const mockPaginatedResponse = {
  data: {
    items: mockStations,
    total: 2,
    page: 1,
    pageSize: 20,
  } as PaginatedData<Station>,
};

describe('stationStore', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useStationStore.setState({
      stations: [],
      selectedStation: null,
      chargers: [],
      total: 0,
      page: 1,
      loading: false,
      refreshing: false,
      error: null,
    });
  });

  describe('fetchStations', () => {
    it('should fetch and set station list', async () => {
      (stationApi.getList as jest.Mock).mockResolvedValue(mockPaginatedResponse);

      await useStationStore.getState().fetchStations({ latitude: 39.9, longitude: 116.4 });

      expect(stationApi.getList).toHaveBeenCalledWith({ latitude: 39.9, longitude: 116.4 });
      const state = useStationStore.getState();
      expect(state.stations).toEqual(mockStations);
      expect(state.total).toBe(2);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('should set error on failure', async () => {
      (stationApi.getList as jest.Mock).mockRejectedValue(new Error('网络错误'));

      await useStationStore.getState().fetchStations();

      const state = useStationStore.getState();
      expect(state.loading).toBe(false);
      expect(state.error).toBe('网络错误');
    });

    it('should set loading to true while fetching', async () => {
      (stationApi.getList as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      );

      const promise = useStationStore.getState().fetchStations();
      expect(useStationStore.getState().loading).toBe(true);
      await promise;
    });
  });

  describe('refreshStations', () => {
    it('should refresh stations and set refreshing state', async () => {
      (stationApi.getList as jest.Mock).mockResolvedValue(mockPaginatedResponse);

      await useStationStore.getState().refreshStations();

      expect(useStationStore.getState().refreshing).toBe(false);
      expect(useStationStore.getState().stations.length).toBe(2);
    });
  });

  describe('fetchStationDetail', () => {
    it('should fetch and set station detail', async () => {
      (stationApi.getDetail as jest.Mock).mockResolvedValue({ data: mockStations[0] });

      await useStationStore.getState().fetchStationDetail(1);

      expect(stationApi.getDetail).toHaveBeenCalledWith(1);
      expect(useStationStore.getState().selectedStation).toEqual(mockStations[0]);
      expect(useStationStore.getState().loading).toBe(false);
    });
  });

  describe('fetchChargers', () => {
    it('should fetch chargers for a station', async () => {
      const mockChargers = [
        { id: 1, stationId: 1, name: 'A-01', code: 'CH-001', type: 'dc' as const, status: 'idle' as const, power: 120, pricePerKwh: 0.8, serviceFee: 0.5 },
        { id: 2, stationId: 1, name: 'A-02', code: 'CH-002', type: 'dc' as const, status: 'charging' as const, power: 120, pricePerKwh: 0.8, serviceFee: 0.5 },
      ];
      (stationApi.getChargers as jest.Mock).mockResolvedValue({ data: mockChargers });

      await useStationStore.getState().fetchChargers(1);

      expect(stationApi.getChargers).toHaveBeenCalledWith(1);
      expect(useStationStore.getState().chargers).toEqual(mockChargers);
    });
  });

  describe('searchStations', () => {
    it('should search stations by keyword', async () => {
      (stationApi.search as jest.Mock).mockResolvedValue(mockPaginatedResponse);

      await useStationStore.getState().searchStations('中心站');

      expect(stationApi.search).toHaveBeenCalledWith('中心站');
      expect(useStationStore.getState().stations.length).toBe(2);
    });
  });

  describe('setSelectedStation', () => {
    it('should set selected station and clear chargers', () => {
      useStationStore.getState().setSelectedStation(mockStations[0]);

      expect(useStationStore.getState().selectedStation).toEqual(mockStations[0]);
      expect(useStationStore.getState().chargers).toEqual([]);
    });

    it('should set null and clear chargers', () => {
      useStationStore.getState().setSelectedStation(null);

      expect(useStationStore.getState().selectedStation).toBeNull();
      expect(useStationStore.getState().chargers).toEqual([]);
    });
  });
});