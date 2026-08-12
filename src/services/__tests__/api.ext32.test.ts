import { chatApi, notificationSendApi } from '../api';

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

describe('chatApi.send (POST /chat)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps snake_case response to camelCase correctly', async () => {
    mockedAxios.post.mockResolvedValue({
      data: {
        code: 200,
        message: '对话成功',
        data: {
          answer: '当前有17个充电站在线',
          confidence: 0.95,
          sources: [
            { title: '站点状态报表', url: '/reports/stations', type: 'report' },
          ],
          actions: [
            { type: 'navigate', label: '查看站点', target: '/stations' },
          ],
          needs_human: false,
          usage: {
            prompt_tokens: 50,
            completion_tokens: 120,
            total_tokens: 170,
          },
        },
        timestamp: 1786558629,
      },
    });

    const res = await chatApi.send('有多少充电站在线？');
    expect(mockedAxios.post).toHaveBeenCalledWith('/chat', { message: '有多少充电站在线？' });
    expect(res.data.answer).toBe('当前有17个充电站在线');
    expect(res.data.confidence).toBe(0.95);
    expect(res.data.needsHuman).toBe(false);
    expect(res.data.sources).toHaveLength(1);
    expect(res.data.sources[0]).toEqual({
      title: '站点状态报表',
      url: '/reports/stations',
      type: 'report',
    });
    expect(res.data.actions).toHaveLength(1);
    expect(res.data.actions[0]).toEqual({
      type: 'navigate',
      label: '查看站点',
      target: '/stations',
    });
    expect(res.data.usage).toEqual({
      promptTokens: 50,
      completionTokens: 120,
      totalTokens: 170,
    });
  });

  it('handles needs_human=true with low confidence', async () => {
    mockedAxios.post.mockResolvedValue({
      data: {
        code: 200,
        message: '对话成功',
        data: {
          answer: '抱歉，对话服务暂时不可用，请稍后重试',
          confidence: 0,
          sources: [],
          actions: [],
          needs_human: true,
          usage: null,
        },
        timestamp: 1786558629,
      },
    });

    const res = await chatApi.send('复杂问题');
    expect(res.data.needsHuman).toBe(true);
    expect(res.data.confidence).toBe(0);
    expect(res.data.sources).toEqual([]);
    expect(res.data.actions).toEqual([]);
    expect(res.data.usage).toBeNull();
  });

  it('passes conversation_id and context when provided', async () => {
    mockedAxios.post.mockResolvedValue({
      data: {
        code: 200,
        message: '对话成功',
        data: { answer: 'ok', confidence: 1, sources: [], actions: [], needs_human: false, usage: null },
        timestamp: 0,
      },
    });

    await chatApi.send('test', {
      conversationId: 'conv-001',
      context: { station_id: 1 },
    });

    expect(mockedAxios.post).toHaveBeenCalledWith('/chat', {
      message: 'test',
      conversation_id: 'conv-001',
      context: { station_id: 1 },
    });
  });

  it('handles missing data fields with defaults', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 200, message: 'ok', data: {}, timestamp: 0 },
    });

    const res = await chatApi.send('hi');
    expect(res.data.answer).toBe('');
    expect(res.data.confidence).toBe(0);
    expect(res.data.needsHuman).toBe(false);
    expect(res.data.sources).toEqual([]);
    expect(res.data.actions).toEqual([]);
    expect(res.data.usage).toBeNull();
  });

  it('handles null data field', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 200, message: 'ok', data: null, timestamp: 0 },
    });

    const res = await chatApi.send('hi');
    expect(res.data.answer).toBe('');
    expect(res.data.usage).toBeNull();
  });

  it('maps usage snake_case fields correctly', async () => {
    mockedAxios.post.mockResolvedValue({
      data: {
        code: 200,
        message: 'ok',
        data: {
          answer: 'test',
          confidence: 0.5,
          sources: [],
          actions: [],
          needs_human: false,
          usage: { prompt_tokens: 10, completion_tokens: 20, total_tokens: 30 },
        },
        timestamp: 0,
      },
    });

    const res = await chatApi.send('test');
    expect(res.data.usage).toEqual({
      promptTokens: 10,
      completionTokens: 20,
      totalTokens: 30,
    });
  });
});

describe('notificationSendApi.send (POST /notifications/send)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('sends with required fields and maps response', async () => {
    mockedAxios.post.mockResolvedValue({
      data: {
        code: 200,
        message: '发送成功',
        data: {
          success: true,
          message_id: 'msg-001',
          channel: 'app',
          sent_at: '2026-08-13T02:15:00Z',
        },
        timestamp: 1786558600,
      },
    });

    const res = await notificationSendApi.send({
      userId: 1,
      title: '测试通知',
      content: '这是一条测试通知',
    });

    expect(mockedAxios.post).toHaveBeenCalledWith('/notifications/send', {
      user_id: 1,
      title: '测试通知',
      content: '这是一条测试通知',
    });
    expect(res.data.success).toBe(true);
    expect(res.data.messageId).toBe('msg-001');
    expect(res.data.channel).toBe('app');
    expect(res.data.sentAt).toBe('2026-08-13T02:15:00Z');
  });

  it('includes optional channel and type when provided', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 200, message: 'ok', data: { success: true }, timestamp: 0 },
    });

    await notificationSendApi.send({
      userId: 2,
      title: '告警',
      content: '设备离线',
      channel: 'sms',
      type: 'urgent',
    });

    expect(mockedAxios.post).toHaveBeenCalledWith('/notifications/send', {
      user_id: 2,
      title: '告警',
      content: '设备离线',
      channel: 'sms',
      type: 'urgent',
    });
  });

  it('handles empty response data with defaults', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 200, message: 'ok', data: {}, timestamp: 0 },
    });

    const res = await notificationSendApi.send({
      userId: 1,
      title: 't',
      content: 'c',
    });
    expect(res.data.success).toBe(false);
    expect(res.data.messageId).toBeNull();
    expect(res.data.channel).toBeNull();
    expect(res.data.sentAt).toBeNull();
  });

  it('handles null response data', async () => {
    mockedAxios.post.mockResolvedValue({
      data: { code: 200, message: 'ok', data: null, timestamp: 0 },
    });

    const res = await notificationSendApi.send({
      userId: 1,
      title: 't',
      content: 'c',
    });
    expect(res.data.success).toBe(false);
  });
});
