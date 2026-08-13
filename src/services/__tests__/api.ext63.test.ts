/**
 * api ext63 — workOrderActionApi.rate + DeviceReport healthScore
 * POST /work-orders/{id}/rate (response_rating + quality_rating + attitude_rating)
 * GET /reports/devices now includes healthScore/onlineRate/faultRate
 */
import { workOrderActionApi, reportApi } from '../api';
import axios from 'axios';
import type { WorkOrderRating } from '../../types';

jest.mock('axios', () => {
  const mockInstance = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
  };
  return {
    create: jest.fn(() => mockInstance),
    __mockInstance: mockInstance,
  };
});

jest.mock('expo-secure-store', () => ({
  getItemSecure: jest.fn().mockResolvedValue('mock-token'),
  setItemSecure: jest.fn().mockResolvedValue(undefined),
  deleteItemSecure: jest.fn().mockResolvedValue(undefined),
}));

const mockAxios = (axios as unknown as { __mockInstance: Record<string, jest.Mock> }).__mockInstance;

describe('api.ext63 — workOrderActionApi.rate', () => {
  beforeEach(() => jest.clearAllMocks());

  it('rate() sends camelCase→snake_case body with all ratings + comment', async () => {
    mockAxios.post.mockResolvedValue({
      data: { code: 200, message: 'success', data: null },
    });

    const rating: WorkOrderRating = {
      responseRating: 5,
      qualityRating: 4,
      attitudeRating: 5,
      comment: 'great work',
    };

    const result = await workOrderActionApi.rate('WO-123', rating);

    expect(mockAxios.post).toHaveBeenCalledWith('/work-orders/WO-123/rate', {
      response_rating: 5,
      quality_rating: 4,
      attitude_rating: 5,
      comment: 'great work',
    });
    expect(result.code).toBe(200);
    expect(result.data).toBeNull();
  });

  it('rate() omits comment when undefined', async () => {
    mockAxios.post.mockResolvedValue({
      data: { code: 200, message: 'success', data: null },
    });

    await workOrderActionApi.rate('WO-456', {
      responseRating: 3,
      qualityRating: 3,
      attitudeRating: 3,
    });

    const body = mockAxios.post.mock.calls[0][1];
    expect(body).toEqual({
      response_rating: 3,
      quality_rating: 3,
      attitude_rating: 3,
    });
    expect(body).not.toHaveProperty('comment');
  });

  it('rate() returns 409 business error for incomplete WO', async () => {
    mockAxios.post.mockResolvedValue({
      data: { code: 409, message: '工单未完成，暂不可评价', data: null },
    });

    const result = await workOrderActionApi.rate('WO-999', {
      responseRating: 5,
      qualityRating: 5,
      attitudeRating: 5,
    });

    expect(result.code).toBe(409);
    expect(result.data).toBeNull();
  });

  it('rate() endpoint path + payload verification', async () => {
    mockAxios.post.mockResolvedValue({
      data: { code: 200, message: 'success', data: null },
    });

    await workOrderActionApi.rate('WO-ABC', {
      responseRating: 1,
      qualityRating: 1,
      attitudeRating: 1,
    });

    expect(mockAxios.post).toHaveBeenCalledTimes(1);
    const [url, body] = mockAxios.post.mock.calls[0];
    expect(url).toContain('/work-orders/');
    expect(url).toContain('/rate');
    expect(body).toHaveProperty('response_rating');
    expect(body).toHaveProperty('quality_rating');
    expect(body).toHaveProperty('attitude_rating');
  });
});

describe('api.ext63 — DeviceReport healthScore/onlineRate/faultRate', () => {
  beforeEach(() => jest.clearAllMocks());

  it('getDeviceReport() maps healthScore + onlineRate + faultRate', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          period_days: 30,
          total_devices: 50,
          type_distribution: { gateway: 14 },
          status_distribution: { online: 31 },
          station_distribution: [
            { station_id: 1, station_name: '北京光伏电站', device_count: 5 },
          ],
          health_score: {
            average: 85.5,
            distribution: { excellent: 20, good: 15, warning: 10, critical: 5 },
          },
          online_rate: 62.0,
          fault_rate: 14.0,
        },
      },
    });

    const result = await reportApi.getDeviceReport();

    expect(result.data.healthScore).toBeDefined();
    expect(result.data.healthScore!.average).toBe(85.5);
    expect(result.data.healthScore!.distribution).toEqual({
      excellent: 20,
      good: 15,
      warning: 10,
      critical: 5,
    });
    expect(result.data.onlineRate).toBe(62.0);
    expect(result.data.faultRate).toBe(14.0);
  });

  it('getDeviceReport() handles missing healthScore gracefully', async () => {
    mockAxios.get.mockResolvedValue({
      data: {
        code: 200,
        message: 'success',
        data: {
          period_days: 7,
          total_devices: 3,
          type_distribution: {},
          status_distribution: {},
          station_distribution: [],
        },
      },
    });

    const result = await reportApi.getDeviceReport();

    expect(result.data.healthScore).toBeUndefined();
    expect(result.data.onlineRate).toBeUndefined();
    expect(result.data.faultRate).toBeUndefined();
  });
});
