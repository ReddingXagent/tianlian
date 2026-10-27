import { deviceApi } from '../api';
import type { DeviceHealthSummary } from '../../types';

// Mock expo-secure-store
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// Mock axios
jest.mock('axios', () => {
  const mockAxios: Record<string, any> = {
    create: jest.fn(() => mockAxios),
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
    defaults: { headers: { common: {} } },
  };
  return mockAxios;
});

import axios from 'axios';
const mockAxios = axios as jest.Mocked<typeof axios>;

describe('deviceApi.getHealthList (ext44 — GET /devices/health)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should map snake_case to camelCase correctly', async () => {
    const mockResponse = {
      code: 200,
      message: 'success',
      data: {
        items: [
          {
            id: 1,
            code: 'BATTERY202600001',
            name: 'TL-BAT-100AH-001',
            type: 'battery_inverter',
            health_score: 91.72,
            status: 'online',
          },
          {
            id: 2,
            code: 'CHARGER202600006',
            name: 'TL-CHG-240KW-006',
            type: 'charger_dc',
            health_score: 92.38,
            status: 'online',
          },
        ],
      },
      timestamp: 1786618860,
    };
    (mockAxios.get as jest.Mock).mockResolvedValue({ data: mockResponse });

    const result = await deviceApi.getHealthList();

    expect(mockAxios.get).toHaveBeenCalledWith('/devices/health', { params: undefined });
    expect(result.data.items).toHaveLength(2);
    expect(result.data.items[0]).toEqual({
      id: 1,
      code: 'BATTERY202600001',
      name: 'TL-BAT-100AH-001',
      type: 'battery_inverter',
      healthScore: 91.72,
      status: 'online',
    } as DeviceHealthSummary);
    expect(result.data.items[1]).toEqual({
      id: 2,
      code: 'CHARGER202600006',
      name: 'TL-CHG-240KW-006',
      type: 'charger_dc',
      healthScore: 92.38,
      status: 'online',
    } as DeviceHealthSummary);
  });

  it('should handle empty items list', async () => {
    const mockResponse = {
      code: 200,
      message: 'success',
      data: { items: [] },
      timestamp: 1786618860,
    };
    (mockAxios.get as jest.Mock).mockResolvedValue({ data: mockResponse });

    const result = await deviceApi.getHealthList();

    expect(result.data.items).toEqual([]);
    expect(result.data.total).toBe(0);
  });

  it('should apply null/missing defaults', async () => {
    const mockResponse = {
      code: 200,
      message: 'success',
      data: {
        items: [
          { id: 1, code: 'DEV001' },
        ],
      },
      timestamp: 1786618860,
    };
    (mockAxios.get as jest.Mock).mockResolvedValue({ data: mockResponse });

    const result = await deviceApi.getHealthList();

    expect(result.data.items[0]).toEqual({
      id: 1,
      code: 'DEV001',
      name: '',
      type: '',
      healthScore: 0,
      status: '',
    });
  });

  it('should pass filter params', async () => {
    (mockAxios.get as jest.Mock).mockResolvedValue({
      data: { code: 200, message: 'success', data: { items: [] } },
    });

    await deviceApi.getHealthList({ status: 'online', type: 'meter', page: 1, pageSize: 20 });

    expect(mockAxios.get).toHaveBeenCalledWith('/devices/health', {
      params: { status: 'online', type: 'meter', page: 1, pageSize: 20 },
    });
  });

  it('should call correct endpoint', async () => {
    (mockAxios.get as jest.Mock).mockResolvedValue({
      data: { code: 200, message: 'success', data: { items: [] } },
    });

    await deviceApi.getHealthList();

    expect(mockAxios.get).toHaveBeenCalledTimes(1);
    expect((mockAxios.get as jest.Mock).mock.calls[0][0]).toBe('/devices/health');
  });
});
