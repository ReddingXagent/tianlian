import { fleetApi } from '../api';

// Mock expo-secure-store before axios mock
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

// Import mocked axios
import axios from 'axios';
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('fleetApi.getDrivers', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case fields to camelCase', async () => {
    const mockData = {
      code: 200,
      message: 'success',
      data: {
        items: [
          {
            id: 1,
            name: '张三',
            phone: '13800138000',
            license_number: 'DL-2024-001',
            vehicle_plate: '京A12345',
            status: 'active',
            created_at: '2024-01-15T08:00:00Z',
            updated_at: '2024-06-20T12:00:00Z',
          },
          {
            id: 2,
            name: '李四',
            phone: '13900139000',
            license_number: 'DL-2024-002',
            vehicle_plate: '京B67890',
            status: 'off_duty',
            created_at: '2024-03-10T10:00:00Z',
            updated_at: '2024-07-01T14:00:00Z',
          },
        ],
        total: 2,
        page: 1,
        page_size: 20,
      },
      timestamp: 1705000000,
    };

    mockedAxios.get.mockResolvedValueOnce({ data: mockData });

    const result = await fleetApi.getDrivers();

    expect(result.data.items).toHaveLength(2);
    expect(result.data.items[0]).toEqual({
      id: 1,
      name: '张三',
      phone: '13800138000',
      licenseNumber: 'DL-2024-001',
      vehiclePlate: '京A12345',
      status: 'active',
      createdAt: '2024-01-15T08:00:00Z',
      updatedAt: '2024-06-20T12:00:00Z',
    });
    expect(result.data.items[1].licenseNumber).toBe('DL-2024-002');
    expect(result.data.items[1].vehiclePlate).toBe('京B67890');
  });

  it('handles empty driver list', async () => {
    const mockData = {
      code: 200,
      message: 'success',
      data: { items: [], total: 0, page: 1, page_size: 20 },
      timestamp: 1705000000,
    };

    mockedAxios.get.mockResolvedValueOnce({ data: mockData });

    const result = await fleetApi.getDrivers();

    expect(result.data.items).toEqual([]);
    expect(result.data.total).toBe(0);
  });

  it('handles null/missing fields with defaults', async () => {
    const mockData = {
      code: 200,
      message: 'success',
      data: {
        items: [{ id: 1 }],
        total: 1,
        page: 1,
        page_size: 20,
      },
      timestamp: 1705000000,
    };

    mockedAxios.get.mockResolvedValueOnce({ data: mockData });

    const result = await fleetApi.getDrivers();

    expect(result.data.items[0]).toEqual({
      id: 1,
      name: '',
      phone: null,
      licenseNumber: null,
      vehiclePlate: null,
      status: 'unknown',
      createdAt: null,
      updatedAt: null,
    });
  });

  it('handles null items array', async () => {
    const mockData = {
      code: 200,
      message: 'success',
      data: { items: null, total: 0, page: 1, page_size: 20 },
      timestamp: 1705000000,
    };

    mockedAxios.get.mockResolvedValueOnce({ data: mockData });

    const result = await fleetApi.getDrivers();

    expect(result.data.items).toEqual([]);
  });

  it('passes page/pageSize params as snake_case', async () => {
    const mockData = {
      code: 200,
      message: 'success',
      data: { items: [], total: 0, page: 2, page_size: 10 },
      timestamp: 1705000000,
    };

    mockedAxios.get.mockResolvedValueOnce({ data: mockData });

    await fleetApi.getDrivers({ page: 2, pageSize: 10 });

    expect(mockedAxios.get).toHaveBeenCalledWith('/fleet/drivers', {
      params: { page: 2, page_size: 10 },
    });
  });

  it('calls correct endpoint without params', async () => {
    const mockData = {
      code: 200,
      message: 'success',
      data: { items: [], total: 0, page: 1, page_size: 20 },
      timestamp: 1705000000,
    };

    mockedAxios.get.mockResolvedValueOnce({ data: mockData });

    await fleetApi.getDrivers();

    expect(mockedAxios.get).toHaveBeenCalledWith('/fleet/drivers', {
      params: {},
    });
  });
});
