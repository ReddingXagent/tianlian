/**
 * AI 助手服务单元测试
 */

import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api from '../api';
import {
  AI_FUNCTIONS,
  executeToolCall,
  sendChatMessage,
  streamChatMessage,
  chat,
  ChatMessage,
} from '../ai';

// Mock expo-secure-store
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);
const TEST_TOKEN = 'test-jwt-token-12345';
const BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ||
  (__DEV__ ? 'http://localhost:8000/api/v1' : 'http://your-server-ip/api/v1');

// =====================
// AI_FUNCTIONS 定义测试
// =====================

describe('AI_FUNCTIONS', () => {
  it('should define all 6 functions', () => {
    expect(AI_FUNCTIONS).toHaveLength(6);
    const names = AI_FUNCTIONS.map((f) => f.name);
    expect(names).toContain('get_device_status');
    expect(names).toContain('list_alarms');
    expect(names).toContain('list_workorders');
    expect(names).toContain('get_revenue_stats');
    expect(names).toContain('get_dashboard_summary');
    expect(names).toContain('control_device');
  });

  it('each function should have name, description, and parameters', () => {
    for (const fn of AI_FUNCTIONS) {
      expect(fn.name).toBeTruthy();
      expect(fn.description).toBeTruthy();
      expect(fn.parameters.type).toBe('object');
      expect(fn.parameters.properties).toBeDefined();
    }
  });

  it('get_device_status should require device_id', () => {
    const fn = AI_FUNCTIONS.find((f) => f.name === 'get_device_status')!;
    expect(fn.parameters.required).toContain('device_id');
    expect(fn.parameters.properties.device_id.type).toBe('number');
  });

  it('list_alarms should have status enum', () => {
    const fn = AI_FUNCTIONS.find((f) => f.name === 'list_alarms')!;
    expect(fn.parameters.properties.status.enum).toEqual([
      'unhandled',
      'processing',
      'resolved',
    ]);
  });

  it('control_device should require device_id and action', () => {
    const fn = AI_FUNCTIONS.find((f) => f.name === 'control_device')!;
    expect(fn.parameters.required).toContain('device_id');
    expect(fn.parameters.required).toContain('action');
    expect(fn.parameters.properties.action.enum).toEqual([
      'start',
      'stop',
      'restart',
      'reset',
    ]);
  });
});

// =====================
// =====================
// executeToolCall 测试
// =====================

describe('executeToolCall', () => {
  beforeEach(() => {
    mockAxios.reset();
    jest.clearAllMocks();
  });

  it('get_device_status should return device info and telemetry', async () => {
    const device = {
      id: 1,
      stationId: 1,
      name: '充电桩A',
      code: 'CH001',
      type: 'charger',
      status: 'online',
      model: 'CH-2000',
      manufacturer: '厂商A',
      lastHeartbeat: '2024-01-01T00:00:00Z',
      createdAt: '2024-01-01T00:00:00Z',
      updatedAt: '2024-01-01T00:00:00Z',
    };
    const telemetry = {
      deviceId: 1,
      power: 50.5,
      voltage: 380,
      current: 133,
      temperature: 35,
      energy: 1200.5,
      timestamp: '2024-01-01T10:00:00Z',
    };

    mockAxios.onGet('/devices/1').reply(200, { code: 0, message: 'ok', data: device });
    mockAxios
      .onGet('/devices/1/telemetry')
      .reply(200, { code: 0, message: 'ok', data: telemetry });

    const result = await executeToolCall('get_device_status', { device_id: 1 });
    const parsed = JSON.parse(result);

    expect(parsed.device.id).toBe(1);
    expect(parsed.device.name).toBe('充电桩A');
    expect(parsed.device.status).toBe('online');
    expect(parsed.telemetry.power).toBe('50.5 kW');
    expect(parsed.telemetry.voltage).toBe('380 V');
    expect(parsed.telemetry.temperature).toBe('35 °C');
  });

  it('list_alarms should return formatted alarm list', async () => {
    // 真云端契约: snake_case + 状态 active + 分页 page_size
    mockAxios
      .onGet('/alarms')
      .reply(200, {
        code: 200, message: 'success',
        data: {
          items: [{
            id: 1,
            station_id: 1,
            station_name: '站A',
            alarm_type: 'high_temperature',
            level: 'critical',
            status: 'active',
            content: '温度异常',
            created_at: '2024-01-01T00:00:00Z',
          }],
          total: 1, page: 1, page_size: 20,
        },
      });

    const result = await executeToolCall('list_alarms', { status: 'unhandled' });
    const parsed = JSON.parse(result);

    expect(parsed.alarms).toHaveLength(1);
    expect(parsed.alarms[0].title).toBe('温度过高');
    expect(parsed.alarms[0].level).toBe('critical');
    expect(parsed.alarms[0].status).toBe('unhandled');
    expect(parsed.total).toBe(1);
  });

  it('list_workorders should return formatted work order list', async () => {
    mockAxios
      .onGet('/work-orders')
      .reply(200, {
        code: 200, message: 'success',
        data: {
          items: [{
            id: 'WO-20240101-0001',
            station_id: 1,
            fault_desc: '维修充电桩',
            type: 'repair',
            level: 'P1',
            status: 'pending',
            creator_id: 1,
            create_time: '2024-01-01T00:00:00Z',
          }],
          total: 1, page: 1, page_size: 20,
        },
      });

    const result = await executeToolCall('list_workorders', { status: 'pending' });
    const parsed = JSON.parse(result);

    expect(parsed.orders).toHaveLength(1);
    expect(parsed.orders[0].title).toBe('维修充电桩');
    expect(parsed.orders[0].priority).toBe('high');
    expect(parsed.orders[0].id).toBe('WO-20240101-0001');
  });

  it('get_revenue_stats with period=day should return summary', async () => {
    // A3 经营域契约: /business/revenue/summary 返回 net_revenue(元) + daily 明细
    mockAxios
      .onGet('/business/revenue/summary')
      .reply(200, { code: 200, message: 'success', data: { order_count: 5, net_revenue: 5000.0 } });
    mockAxios
      .onGet('/business/revenue/daily')
      .reply(200, { code: 200, message: 'success', data: Array.from({ length: 30 }, (_, i) => ({
        date: `2024-01-${String(i + 1).padStart(2, '0')}`,
        order_count: 1,
        net_revenue: i >= 23 ? 100 : 80,
      })) });

    const result = await executeToolCall('get_revenue_stats', { period: 'day' });
    const parsed = JSON.parse(result);

    expect(parsed.today).toBe('¥100.00');
    expect(parsed.week).toBe('¥700.00');
    expect(parsed.total).toBe('¥5000.00');
    expect(parsed.period).toBe('day');
  });

  it('get_revenue_stats with period=month should return records', async () => {
    mockAxios
      .onGet('/business/revenue/daily')
      .reply(200, {
        code: 200, message: 'success',
        data: [
          { date: '2024-01-01', order_count: 10, net_revenue: 10.0 },
          { date: '2024-01-02', order_count: 20, net_revenue: 20.0 },
        ],
      });

    const result = await executeToolCall('get_revenue_stats', { period: 'month' });
    const parsed = JSON.parse(result);

    expect(parsed.records).toHaveLength(2);
    expect(parsed.records[0].amount).toBe('¥10.00');
    expect(parsed.period).toBe('month');
  });

  it('get_dashboard_summary should return dashboard stats', async () => {
    // 真云端无 dashboard 端点: 聚合 work-orders/stats + alarms + stations
    mockAxios.onGet('/work-orders/stats').reply(200, {
      code: 200, message: 'success',
      data: { total: 12, status_distribution: { pending: 2, processing: 1, completed: 9 } },
    });
    mockAxios.onGet('/alarms').reply((config) => {
      const p = config.params ?? {};
      return [200, { code: 200, message: 'success', data: { items: [], total: p.status === 'active' ? 2 : 5, page: 1, page_size: 1 } }];
    });
    mockAxios.onGet('/stations').reply(200, {
      code: 200, message: 'success',
      data: {
        items: Array.from({ length: 8 }, (_, i) => ({ id: i + 1, name: `s${i}`, status: 'normal', lat: 0, lon: 0 }))
          .concat(Array.from({ length: 2 }, (_, i) => ({ id: i + 9, name: `x${i}`, status: 'offline', lat: 0, lon: 0 }))),
        total: 10, page: 1, page_size: 100,
      },
    });

    const result = await executeToolCall('get_dashboard_summary', {});
    const parsed = JSON.parse(result);

    expect(parsed.totalStations).toBe(10);
    expect(parsed.onlineStations).toBe(8);
    expect(parsed.unhandledAlarms).toBe(2);
    expect(parsed.totalAlarms).toBe(5);
  });

  it('control_device should send control command', async () => {
    mockAxios
      .onPost('/devices/1/control', { command: 'restart' })
      .reply(200, { code: 0, message: 'ok', data: { success: true, message: '设备已重启' } });

    const result = await executeToolCall('control_device', {
      device_id: 1,
      action: 'restart',
    });
    const parsed = JSON.parse(result);

    expect(parsed.success).toBe(true);
    expect(parsed.message).toBe('设备已重启');
  });

  it('should handle API errors gracefully', async () => {
    mockAxios.onGet('/devices/999').reply(404, {
      code: 404,
      message: '设备不存在',
    });

    const result = await executeToolCall('get_device_status', { device_id: 999 });
    const parsed = JSON.parse(result);

    expect(parsed.error).toContain('Failed to execute get_device_status');
  });

  it('should handle unknown function name', async () => {
    const result = await executeToolCall('unknown_func', {});
    const parsed = JSON.parse(result);

    expect(parsed.error).toContain('Unknown function: unknown_func');
  });

  it('should handle network errors', async () => {
    mockAxios.onGet('/devices/1').networkError();

    const result = await executeToolCall('get_device_status', { device_id: 1 });
    const parsed = JSON.parse(result);

    expect(parsed.error).toContain('Failed to execute get_device_status');
  });
});

// =====================
// sendChatMessage 测试 (新 /chat 端点格式)
// =====================

describe('sendChatMessage', () => {
  beforeEach(() => {
    mockAxios.reset();
    jest.clearAllMocks();
  });

  it('应发送非流式请求并返回回答', async () => {
    const chatResponse = {
      code: 200,
      message: '对话成功',
      data: {
        answer: '你好！有什么可以帮助你的？',
        confidence: 0.95,
        sources: [],
        actions: [],
        needs_human: false,
        usage: { prompt_tokens: 10, completion_tokens: 20, total_tokens: 30 },
      },
      timestamp: Date.now(),
    };

    mockAxios.onPost('/chat').reply(200, chatResponse);

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: '你好', timestamp: Date.now() },
    ];

    const result = await sendChatMessage(messages);

    expect(result.role).toBe('assistant');
    expect(result.content).toBe('你好！有什么可以帮助你的？');
  });

  it('应提取最后一条用户消息作为请求体', async () => {
    mockAxios.onPost('/chat').reply((config) => {
      const body = JSON.parse(config.data);
      expect(body.message).toBe('最新问题');
      expect(body.messages).toBeUndefined();
      return [200, {
        code: 200,
        message: 'ok',
        data: { answer: '回答', confidence: 1, sources: [], actions: [], needs_human: false, usage: null },
        timestamp: 0,
      }];
    });

    await sendChatMessage([
      { id: '1', role: 'user', content: '旧问题', timestamp: Date.now() },
      { id: '2', role: 'assistant', content: '旧回答', timestamp: Date.now() },
      { id: '3', role: 'user', content: '最新问题', timestamp: Date.now() },
    ]);
  });

  it('无用户消息时应返回提示', async () => {
    const result = await sendChatMessage([
      { id: '1', role: 'assistant', content: '你好', timestamp: Date.now() },
    ]);

    expect(result.role).toBe('assistant');
    expect(result.content).toBe('请输入您的问题。');
  });

  it('answer为空时应返回空字符串', async () => {
    mockAxios.onPost('/chat').reply(200, {
      code: 200,
      message: 'ok',
      data: { answer: '', confidence: 0, sources: [], actions: [], needs_human: true, usage: null },
      timestamp: 0,
    });

    const result = await sendChatMessage([
      { id: '1', role: 'user', content: 'hi', timestamp: Date.now() },
    ]);

    expect(result.content).toBe('');
  });
});

// =====================
// streamChatMessage 测试 (新 JSON Lines 流格式)
// =====================

describe('streamChatMessage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(TEST_TOKEN);
  });

  it('应解析 JSON Lines chunk 并yield content', async () => {
    const mockReader = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            '{"type":"chunk","content":"你好"}\n'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            '{"type":"chunk","content":"，我是AI助手"}\n'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            '{"type":"done"}\n'
          ),
        })
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    };

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    } as unknown);

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: '你好', timestamp: Date.now() },
    ];

    const chunks: string[] = [];
    for await (const chunk of streamChatMessage(messages)) {
      if (chunk.content) {
        chunks.push(chunk.content);
      }
    }

    expect(chunks).toEqual(['你好', '，我是AI助手']);
    expect(global.fetch).toHaveBeenCalledTimes(1);

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    expect(fetchCall[0]).toBe(`${BASE_URL}/chat`);
    expect(fetchCall[1].headers.Authorization).toBe(`Bearer ${TEST_TOKEN}`);

    const body = JSON.parse(fetchCall[1].body);
    expect(body.message).toBe('你好');
    expect(body.stream).toBe(true);
  });

  it('非200响应应抛出错误', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: () => Promise.resolve('Internal Server Error'),
    });

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: 'test', timestamp: Date.now() },
    ];

    await expect(async () => {
      for await (const _ of streamChatMessage(messages)) {
        // should throw
      }
    }).rejects.toThrow('AI API error 500');
  });

  it('text()拒绝时应回退到空错误体', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 503,
      text: () => Promise.reject(new Error('body read failed')),
    });

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: 'test', timestamp: Date.now() },
    ];

    await expect(async () => {
      for await (const _ of streamChatMessage(messages)) {
        // should throw
      }
    }).rejects.toThrow('AI API error 503: ');
  });

  it('reader done但无done标记时应正常结束', async () => {
    const mockReader = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            '{"type":"chunk","content":"一段"}\n'
          ),
        })
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    };

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    });

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: '你好', timestamp: Date.now() },
    ];

    const chunks: string[] = [];
    for await (const chunk of streamChatMessage(messages)) {
      if (chunk.content) chunks.push(chunk.content);
    }

    expect(chunks).toEqual(['一段']);
    expect(mockReader.releaseLock).toHaveBeenCalledTimes(1);
  });

  it('无token时请求头不应含Authorization', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(null);

    const mockReader = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('{"type":"done"}\n'),
        })
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    };

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    });

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: 'test', timestamp: Date.now() },
    ];

    for await (const _ of streamChatMessage(messages)) {
      // nothing
    }

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    expect(fetchCall[1].headers.Authorization).toBeUndefined();
  });

  it('无body时应抛出Streaming not supported', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: true, body: undefined });

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: 'test', timestamp: Date.now() },
    ];

    await expect(async () => {
      for await (const _ of streamChatMessage(messages)) {
        // should throw
      }
    }).rejects.toThrow('Streaming not supported');
  });

  it('跨块行重组: 不完整行通过buffer拼接', async () => {
    const mockReader = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            '{"type":"chunk","content":"跨块'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('拼接"}\n{"type":"done"}\n'),
        })
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    };

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    });

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: 'hi', timestamp: Date.now() },
    ];
    const contents: string[] = [];
    for await (const chunk of streamChatMessage(messages)) {
      if (chunk.content) contents.push(chunk.content);
    }
    expect(contents).toEqual(['跨块拼接']);
  });

  it('无法解析的行应跳过', async () => {
    const mockReader = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            'invalid json line\n{"type":"chunk","content":"有效"}\n'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('{"type":"done"}\n'),
        })
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    };

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    });

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: 'hi', timestamp: Date.now() },
    ];
    const contents: string[] = [];
    for await (const chunk of streamChatMessage(messages)) {
      if (chunk.content) contents.push(chunk.content);
    }
    expect(contents).toEqual(['有效']);
  });
});

// =====================
// chat 多轮对话测试 (新简化格式, 无function calling)
// =====================

describe('chat', () => {
  beforeEach(() => {
    mockAxios.reset();
    jest.clearAllMocks();
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(TEST_TOKEN);
  });

  it('应返回流式文本响应并通过onToken回调', async () => {
    const mockReader = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            '{"type":"chunk","content":"你好！"}\n'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            '{"type":"chunk","content":"有什么可以帮你？"}\n'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('{"type":"done"}\n'),
        })
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    };

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    });

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: '你好', timestamp: Date.now() },
    ];

    const tokens: string[] = [];
    const result = await chat(messages, (token) => tokens.push(token));

    expect(result.role).toBe('assistant');
    expect(result.content).toBe('你好！有什么可以帮你？');
    expect(tokens).toEqual(['你好！', '有什么可以帮你？']);
  });

  it('fetch错误应返回友好的错误消息', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('Network error'));

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: '测试', timestamp: Date.now() },
    ];

    const result = await chat(messages);

    expect(result.role).toBe('assistant');
    expect(result.content).toContain('AI 服务暂时不可用');
    expect(result.content).toContain('Network error');
  });

  it('非Error异常应返回未知错误', async () => {
    global.fetch = jest.fn().mockRejectedValue('boom');

    const result = await chat([
      { id: '1', role: 'user', content: 'hi', timestamp: Date.now() },
    ]);

    expect(result.content).toContain('未知错误');
  });

  it('流式零内容应返回未理解兜底文案', async () => {
    const mockReader = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('{"type":"done"}\n'),
        })
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    };
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    });

    const result = await chat([
      { id: '1', role: 'user', content: 'hi', timestamp: Date.now() },
    ]);

    expect(result.content).toContain('没有理解您的问题');
  });
});
