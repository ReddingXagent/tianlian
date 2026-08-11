import { notificationStatsApi } from '../api';
import type { NotificationStats } from '../../types';

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

describe('notificationStatsApi', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('maps snake_case fields to camelCase', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          total_templates: 5,
          total_messages: 120,
          sent_today: 30,
          failed_count: 2,
          channel_distribution: { sms: 50, email: 40, webhook: 30 },
        },
        timestamp: 1700000000,
      },
    });

    const res = await notificationStatsApi.getStats();
    expect(res.data.totalTemplates).toBe(5);
    expect(res.data.totalMessages).toBe(120);
    expect(res.data.sentToday).toBe(30);
    expect(res.data.failedCount).toBe(2);
    expect(res.data.channelDistribution).toEqual({ sms: 50, email: 40, webhook: 30 });
  });

  it('returns defaults for empty data', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {},
        timestamp: 1700000000,
      },
    });

    const res = await notificationStatsApi.getStats();
    expect(res.data.totalTemplates).toBe(0);
    expect(res.data.totalMessages).toBe(0);
    expect(res.data.sentToday).toBe(0);
    expect(res.data.failedCount).toBe(0);
    expect(res.data.channelDistribution).toEqual({});
  });

  it('returns defaults for null data', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: null,
        timestamp: 1700000000,
      },
    });

    const res = await notificationStatsApi.getStats();
    expect(res.data.totalTemplates).toBe(0);
    expect(res.data.totalMessages).toBe(0);
    expect(res.data.sentToday).toBe(0);
    expect(res.data.failedCount).toBe(0);
    expect(res.data.channelDistribution).toEqual({});
  });

  it('preserves response code and message', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { total_templates: 1 },
        timestamp: 1700000000,
      },
    });

    const res = await notificationStatsApi.getStats();
    expect(res.code).toBe(200);
    expect(res.message).toBe('success');
  });

  it('calls correct endpoint', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: {}, timestamp: 0 },
    });

    await notificationStatsApi.getStats();
    expect(mockedAxios.get).toHaveBeenCalledWith('/notifications/stats');
  });

  it('handles partial data with null fields', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          total_templates: null,
          total_messages: undefined,
          sent_today: 10,
          failed_count: null,
          channel_distribution: null,
        },
        timestamp: 1700000000,
      },
    });

    const res = await notificationStatsApi.getStats();
    expect(res.data.totalTemplates).toBe(0);
    expect(res.data.totalMessages).toBe(0);
    expect(res.data.sentToday).toBe(10);
    expect(res.data.failedCount).toBe(0);
    expect(res.data.channelDistribution).toEqual({});
  });

  it('satisfies NotificationStats type contract', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          total_templates: 3,
          total_messages: 50,
          sent_today: 5,
          failed_count: 1,
          channel_distribution: { email: 30, sms: 20 },
        },
        timestamp: 1700000000,
      },
    });

    const res = await notificationStatsApi.getStats();
    const stats: NotificationStats = res.data;
    expect(stats.totalTemplates).toBe(3);
    expect(stats.totalMessages).toBe(50);
    expect(stats.sentToday).toBe(5);
    expect(stats.failedCount).toBe(1);
    expect(Object.keys(stats.channelDistribution)).toHaveLength(2);
  });
});
