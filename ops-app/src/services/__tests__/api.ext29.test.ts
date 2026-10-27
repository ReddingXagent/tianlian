import { notificationUnreadApi } from '../api';

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

import axios from 'axios';
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('notificationUnreadApi.getUnreadCount', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case unread_count → unreadCount', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { unread_count: 7 }, timestamp: 1700000000 },
    });
    const res = await notificationUnreadApi.getUnreadCount();
    expect(res.data.unreadCount).toBe(7);
    expect(mockedAxios.get).toHaveBeenCalledWith('/notifications/unread-count');
  });

  it('handles zero unread', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { unread_count: 0 }, timestamp: 1700000000 },
    });
    const res = await notificationUnreadApi.getUnreadCount();
    expect(res.data.unreadCount).toBe(0);
  });

  it('defaults to 0 when unread_count is missing', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: {}, timestamp: 1700000000 },
    });
    const res = await notificationUnreadApi.getUnreadCount();
    expect(res.data.unreadCount).toBe(0);
  });

  it('defaults to 0 when data is null', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: null, timestamp: 1700000000 },
    });
    const res = await notificationUnreadApi.getUnreadCount();
    expect(res.data.unreadCount).toBe(0);
  });

  it('returns correct endpoint shape with code/message', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { unread_count: 3 }, timestamp: 1700000000 },
    });
    const res = await notificationUnreadApi.getUnreadCount();
    expect(res.code).toBe(200);
    expect(res.message).toBe('success');
    expect(res.data.unreadCount).toBe(3);
  });

  it('handles large unread count', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: { unread_count: 9999 }, timestamp: 1700000000 },
    });
    const res = await notificationUnreadApi.getUnreadCount();
    expect(res.data.unreadCount).toBe(9999);
  });
});
