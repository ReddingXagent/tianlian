/**
 * ext54 — teamApi.addMember/removeMember (POST/DELETE /teams/{id}/members)
 *       + notificationSendApi shape correction (status/channel/userId/title/sentAt)
 * Cases: addMember camelCase, addMember null defaults, addMember endpoint+payload,
 *        addMember without role, removeMember endpoint, notificationSend corrected shape,
 *        notificationSend null defaults
 */
import axios from 'axios';
import { teamApi, notificationSendApi } from '../api';

// Mock axios
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

// Mock SecureStore
jest.mock('expo-secure-store', () => ({
  getItemSecure: jest.fn().mockResolvedValue('mock-token'),
  setItemSecure: jest.fn().mockResolvedValue(undefined),
  deleteItemSecure: jest.fn().mockResolvedValue(undefined),
}));

const mockedAxios = (axios as unknown as {
  __mockInstance: {
    get: jest.Mock;
    post: jest.Mock;
    put: jest.Mock;
    delete: jest.Mock;
  },
}).__mockInstance;

describe('teamApi.addMember (POST /teams/{id}/members)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should map response snake_case to camelCase', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          id: 1,
          user_id: 1,
          username: 'tl',
          real_name: '管理员',
          team_id: 2,
          role: 'super_admin',
          level: null,
          phone: null,
          status: 'active',
          join_date: '2026-07-10T12:14:12.470910+08:00',
        },
        timestamp: 1786634609,
      },
    });

    const res = await teamApi.addMember(2, 1);
    expect(res.data.userId).toBe(1);
    expect(res.data.username).toBe('tl');
    expect(res.data.realName).toBe('管理员');
    expect(res.data.teamId).toBe(2);
    expect(res.data.role).toBe('super_admin');
    expect(res.data.joinDate).toBe('2026-07-10T12:14:12.470910+08:00');
  });

  it('should handle null defaults for missing fields', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { id: 5, user_id: 3 },
        timestamp: 0,
      },
    });

    const res = await teamApi.addMember(1, 3);
    expect(res.data.userId).toBe(3);
    expect(res.data.username).toBe('');
    expect(res.data.realName).toBeNull();
    expect(res.data.level).toBeNull();
    expect(res.data.phone).toBeNull();
    expect(res.data.joinDate).toBeNull();
    expect(res.data.role).toBe('member');
    expect(res.data.status).toBe('active');
  });

  it('should send correct endpoint and payload with role', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: {}, timestamp: 0 },
    });

    await teamApi.addMember(2, 1, 'operator');
    expect(mockedAxios.post).toHaveBeenCalledWith('/teams/2/members', {
      user_id: 1,
      role: 'operator',
    });
  });

  it('should send minimal payload without role', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: {}, timestamp: 0 },
    });

    await teamApi.addMember(2, 1);
    expect(mockedAxios.post).toHaveBeenCalledWith('/teams/2/members', {
      user_id: 1,
    });
  });
});

describe('teamApi.removeMember (DELETE /teams/{id}/members/{userId})', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should call correct endpoint and return null data', async () => {
    mockedAxios.delete.mockResolvedValueOnce({
      data: { code: 200, message: 'success', data: null, timestamp: 0 },
    });

    const res = await teamApi.removeMember(2, 1);
    expect(mockedAxios.delete).toHaveBeenCalledWith('/teams/2/members/1');
    expect(res.data).toBeNull();
    expect(res.code).toBe(200);
  });
});

describe('notificationSendApi.send — corrected shape', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should map response to corrected NotificationSendResult', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: {
          status: 'ok',
          channel: 'app',
          user_id: '1',
          title: 'test',
          sent_at: '2026-08-13 15:23:29',
        },
        timestamp: 1786634609,
      },
    });

    const res = await notificationSendApi.send({
      userId: 1,
      title: 'test',
      content: 'test msg',
    });
    expect(res.data.status).toBe('ok');
    expect(res.data.channel).toBe('app');
    expect(res.data.userId).toBe('1');
    expect(res.data.title).toBe('test');
    expect(res.data.sentAt).toBe('2026-08-13 15:23:29');
  });

  it('should handle null defaults for missing fields', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        code: 200,
        message: 'success',
        data: { status: 'ok' },
        timestamp: 0,
      },
    });

    const res = await notificationSendApi.send({
      userId: 1,
      title: 't',
      content: 'c',
    });
    expect(res.data.status).toBe('ok');
    expect(res.data.channel).toBeNull();
    expect(res.data.userId).toBeNull();
    expect(res.data.title).toBeNull();
    expect(res.data.sentAt).toBeNull();
  });
});
