import { deviceHealthApi } from '../api';
import type { DeviceHealthRanking } from '../../types';

// Mock axios
jest.mock('axios', () => {
  const mockAxios: Record<string, any> = {
    create: jest.fn(() => mockAxios),
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };
  return mockAxios;
});

// Mock SecureStore
jest.mock('expo-secure-store', () => ({
  getItem: jest.fn().mockResolvedValue('mock-token'),
  setItem: jest.fn(),
  deleteItem: jest.fn(),
}));

// Get the mocked axios instance
import axios from 'axios';
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('deviceHealthApi', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const mockRanking = {
    code: 200,
    message: 'success',
    data: {
      overall: {
        totalDevices: 50,
        healthyCount: 45,
        warningCount: 5,
        criticalCount: 0,
        pendingEval: 6,
        overallScore: 89.6,
      },
      rankings: {
        best: [
          { id: 24, deviceName: 'TL-BAT-100AH-024', code: 'BATTERY202600024', type: 'battery_inverter', stationName: '北京光伏电站', score: 93.8, status: 'normal' },
        ],
        worst: [
          { id: 34, deviceName: 'TL-INV-10K-034', code: 'INVERTER202600034', type: 'pv_inverter', stationName: '合肥光伏电站', score: 76.8, status: 'warning' },
        ],
      },
    },
  };

  it('getRanking returns device health ranking data', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({ data: mockRanking });
    const res = await deviceHealthApi.getRanking();
    expect(res.code).toBe(200);
    expect(res.data.overall.totalDevices).toBe(50);
    expect(res.data.overall.healthyCount).toBe(45);
    expect(res.data.overall.warningCount).toBe(5);
    expect(res.data.overall.criticalCount).toBe(0);
    expect(res.data.overall.overallScore).toBe(89.6);
  });

  it('getRanking best rankings parsed correctly', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({ data: mockRanking });
    const res = await deviceHealthApi.getRanking();
    expect(res.data.rankings.best).toHaveLength(1);
    expect(res.data.rankings.best[0].id).toBe(24);
    expect(res.data.rankings.best[0].deviceName).toBe('TL-BAT-100AH-024');
    expect(res.data.rankings.best[0].score).toBe(93.8);
    expect(res.data.rankings.best[0].status).toBe('normal');
  });

  it('getRanking worst rankings parsed correctly', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({ data: mockRanking });
    const res = await deviceHealthApi.getRanking();
    expect(res.data.rankings.worst).toHaveLength(1);
    expect(res.data.rankings.worst[0].id).toBe(34);
    expect(res.data.rankings.worst[0].score).toBe(76.8);
    expect(res.data.rankings.worst[0].status).toBe('warning');
  });

  it('getRanking calls correct endpoint', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({ data: mockRanking });
    await deviceHealthApi.getRanking();
    expect(mockedAxios.get).toHaveBeenCalledWith('/health/devices');
  });

  it('getRanking handles empty rankings', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          overall: { totalDevices: 0, healthyCount: 0, warningCount: 0, criticalCount: 0, pendingEval: 0, overallScore: 0 },
          rankings: { best: [], worst: [] },
        },
      },
    });
    const res = await deviceHealthApi.getRanking();
    expect(res.data.overall.totalDevices).toBe(0);
    expect(res.data.rankings.best).toEqual([]);
    expect(res.data.rankings.worst).toEqual([]);
  });

  it('getRanking handles pending eval field', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValue({ data: mockRanking });
    const res = await deviceHealthApi.getRanking();
    expect(res.data.overall.pendingEval).toBe(6);
  });

  it('getRanking handles network error', async () => {
    (mockedAxios.get as jest.Mock).mockRejectedValue(new Error('Network Error'));
    await expect(deviceHealthApi.getRanking()).rejects.toThrow('Network Error');
  });
});
