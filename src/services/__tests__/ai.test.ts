/**
 * AI 助手服务单元测试
 */

import axios from 'axios';
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
const BASE_URL = 'http://8.134.106.166/api/v1';

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
    const alarms = {
      items: [
        {
          id: 1,
          stationId: 1,
          stationName: '站A',
          title: '温度过高',
          level: 'critical',
          status: 'unhandled',
          description: '温度异常',
          type: 'temperature_warning',
          createdAt: '2024-01-01T00:00:00Z',
          updatedAt: '2024-01-01T00:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      pageSize: 20,
    };

    mockAxios
      .onGet('/alarms', { params: { status: 'unhandled', pageSize: 20 } })
      .reply(200, { code: 0, message: 'ok', data: alarms });

    const result = await executeToolCall('list_alarms', { status: 'unhandled' });
    const parsed = JSON.parse(result);

    expect(parsed.alarms).toHaveLength(1);
    expect(parsed.alarms[0].title).toBe('温度过高');
    expect(parsed.alarms[0].level).toBe('critical');
    expect(parsed.total).toBe(1);
  });

  it('list_workorders should return formatted work order list', async () => {
    const orders = {
      items: [
        {
          id: 1,
          stationId: 1,
          stationName: '站A',
          title: '维修充电桩',
          description: '需要维修',
          type: 'repair',
          priority: 'high',
          status: 'pending',
          assigneeName: '张三',
          creatorId: 1,
          creatorName: 'admin',
          createdAt: '2024-01-01T00:00:00Z',
          updatedAt: '2024-01-01T00:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      pageSize: 20,
    };

    mockAxios
      .onGet('/work-orders', { params: { status: 'pending', pageSize: 20 } })
      .reply(200, { code: 0, message: 'ok', data: orders });

    const result = await executeToolCall('list_workorders', { status: 'pending' });
    const parsed = JSON.parse(result);

    expect(parsed.orders).toHaveLength(1);
    expect(parsed.orders[0].title).toBe('维修充电桩');
    expect(parsed.orders[0].priority).toBe('high');
  });

  it('get_revenue_stats with period=day should return summary', async () => {
    const summary = { today: 12345, week: 80000, month: 350000, total: 5000000 };

    mockAxios
      .onGet('/revenue/summary')
      .reply(200, { code: 0, message: 'ok', data: summary });

    const result = await executeToolCall('get_revenue_stats', { period: 'day' });
    const parsed = JSON.parse(result);

    expect(parsed.today).toBe('¥123.45');
    expect(parsed.week).toBe('¥800.00');
    expect(parsed.month).toBe('¥3500.00');
    expect(parsed.period).toBe('day');
  });

  it('get_revenue_stats with period=month should return records', async () => {
    const records = [
      { date: '2024-01-01', amount: 1000, orderCount: 10 },
      { date: '2024-01-02', amount: 2000, orderCount: 20 },
    ];

    mockAxios
      .onGet('/revenue/records', { params: { type: 'month' } })
      .reply(200, { code: 0, message: 'ok', data: records });

    const result = await executeToolCall('get_revenue_stats', { period: 'month' });
    const parsed = JSON.parse(result);

    expect(parsed.records).toHaveLength(2);
    expect(parsed.records[0].amount).toBe('¥10.00');
    expect(parsed.period).toBe('month');
  });

  it('get_dashboard_summary should return dashboard stats', async () => {
    const stats = {
      totalStations: 10,
      onlineStations: 8,
      offlineStations: 2,
      totalAlarms: 5,
      unhandledAlarms: 2,
      revenueSummary: { today: 5000, week: 35000, month: 150000, total: 2000000 },
    };

    mockAxios
      .onGet('/dashboard/stats')
      .reply(200, { code: 0, message: 'ok', data: stats });

    const result = await executeToolCall('get_dashboard_summary', {});
    const parsed = JSON.parse(result);

    expect(parsed.totalStations).toBe(10);
    expect(parsed.onlineStations).toBe(8);
    expect(parsed.unhandledAlarms).toBe(2);
    expect(parsed.revenueToday).toBe('¥50.00');
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
// sendChatMessage 测试
// =====================

describe('sendChatMessage', () => {
  beforeEach(() => {
    mockAxios.reset();
    jest.clearAllMocks();
  });

  it('should send non-streaming chat request and return response', async () => {
    const chatResponse = {
      id: 'resp-1',
      choices: [
        {
          message: {
            role: 'assistant',
            content: '你好！有什么可以帮助你的？',
          },
          finishReason: 'stop',
        },
      ],
      usage: { promptTokens: 50, completionTokens: 20, totalTokens: 70 },
    };

    mockAxios.onPost('/ai/chat').reply(200, chatResponse);

    const messages: ChatMessage[] = [
      {
        id: '1',
        role: 'user',
        content: '你好',
        timestamp: Date.now(),
      },
    ];

    const result = await sendChatMessage(messages);

    expect(result.role).toBe('assistant');
    expect(result.content).toBe('你好！有什么可以帮助你的？');
  });

  it('should include function call in response when AI requests it', async () => {
    const chatResponse = {
      id: 'resp-2',
      choices: [
        {
          message: {
            role: 'assistant',
            content: null,
            toolCalls: [
              {
                id: 'call-1',
                type: 'function',
                function: {
                  name: 'get_dashboard_summary',
                  arguments: '{}',
                },
              },
            ],
          },
          finishReason: 'tool_calls',
        },
      ],
    };

    mockAxios.onPost('/ai/chat').reply(200, chatResponse);

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: '仪表盘概览', timestamp: Date.now() },
    ];

    const result = await sendChatMessage(messages);

    expect(result.role).toBe('assistant');
    expect(result.toolCalls).toBeDefined();
    expect(result.toolCalls![0].function.name).toBe('get_dashboard_summary');
  });

  it('should include functions in the request body', async () => {
    mockAxios.onPost('/ai/chat').reply((config) => {
      const body = JSON.parse(config.data);
      expect(body.functions).toBeDefined();
      expect(body.functions.length).toBe(6);
      expect(body.messages[0].role).toBe('system');
      return [200, { id: 'ok', choices: [{ message: { role: 'assistant', content: 'ok' }, finishReason: 'stop' }] }];
    });

    await sendChatMessage([
      { id: '1', role: 'user', content: 'hi', timestamp: Date.now() },
    ]);
  });
});

// =====================
// streamChatMessage 测试
// =====================

describe('streamChatMessage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(TEST_TOKEN);
  });

  it('should yield stream chunks', async () => {
    // Mock fetch for streaming
    const mockReader = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            'data: {"id":"s1","choices":[{"delta":{"content":"你好"}}]}\n\n'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            'data: {"id":"s1","choices":[{"delta":{"content":"，我是AI助手"}}]}\n\n'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('data: [DONE]\n\n'),
        })
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    };

    const mockResponse = {
      ok: true,
      body: {
        getReader: () => mockReader,
      },
    };

    global.fetch = jest.fn().mockResolvedValue(mockResponse as unknown);

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: '你好', timestamp: Date.now() },
    ];

    const chunks: string[] = [];
    for await (const chunk of streamChatMessage(messages)) {
      if (chunk.choices[0]?.delta?.content) {
        chunks.push(chunk.choices[0].delta.content);
      }
    }

    expect(chunks).toEqual(['你好', '，我是AI助手']);
    expect(global.fetch).toHaveBeenCalledTimes(1);

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    expect(fetchCall[0]).toBe(`${BASE_URL}/ai/chat`);
    expect(fetchCall[1].headers.Authorization).toBe(`Bearer ${TEST_TOKEN}`);

    const body = JSON.parse(fetchCall[1].body);
    expect(body.stream).toBe(true);
    expect(body.functions).toBeDefined();
  });

  it('should throw on non-ok response', async () => {
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
        // should throw before yielding
      }
    }).rejects.toThrow('AI API error 500');
  });

  it('should handle request without token', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(null);

    const mockReader = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('data: [DONE]\n\n'),
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
});

// =====================
// chat 多轮对话测试
// =====================

describe('chat', () => {
  beforeEach(() => {
    mockAxios.reset();
    jest.clearAllMocks();
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(TEST_TOKEN);
  });

  it('should return plain text response when no tool call needed', async () => {
    // Mock streaming fetch for plain text response
    const mockReader = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            'data: {"id":"s1","choices":[{"delta":{"content":"你好！"}}]}\n\n'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            'data: {"id":"s1","choices":[{"delta":{"content":"有什么可以帮你？"}}]}\n\n'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('data: [DONE]\n\n'),
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

  it('should execute tool calls and return final response', async () => {
    // First response: tool call
    const reader1 = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            'data: {"id":"s1","choices":[{"delta":{"toolCalls":[{"index":0,"id":"call-1","type":"function","function":{"name":"get_dashboard_summary","arguments":"{}"}}]}}]}\n\n'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('data: [DONE]\n\n'),
        })
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    };

    // Second response: final text
    const reader2 = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            'data: {"id":"s2","choices":[{"delta":{"content":"您的站点共10个，在线8个。"}}]}\n\n'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('data: [DONE]\n\n'),
        })
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    };

    global.fetch = jest
      .fn()
      .mockResolvedValueOnce({ ok: true, body: { getReader: () => reader1 } })
      .mockResolvedValueOnce({ ok: true, body: { getReader: () => reader2 } });

    // Mock the tool call API
    mockAxios.onGet('/dashboard/stats').reply(200, {
      code: 0,
      message: 'ok',
      data: {
        totalStations: 10,
        onlineStations: 8,
        offlineStations: 2,
        totalAlarms: 5,
        unhandledAlarms: 2,
        revenueSummary: { today: 5000, week: 35000, month: 150000, total: 2000000 },
      },
    });

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: '仪表盘概览', timestamp: Date.now() },
    ];

    const result = await chat(messages);

    expect(result.role).toBe('assistant');
    expect(result.content).toContain('您的站点');
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('should handle fetch error gracefully', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('Network error'));

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: '测试', timestamp: Date.now() },
    ];

    const result = await chat(messages);

    expect(result.role).toBe('assistant');
    expect(result.content).toContain('AI 服务暂时不可用');
    expect(result.content).toContain('Network error');
  });

  it('should stop after max tool rounds', async () => {
    // Simulate: every response is a tool call to get_dashboard_summary,
    // so the loop keeps going until MAX_TOOL_ROUNDS (5) is reached.
    let fetchCount = 0;

    const makeToolCallReader = (callId: string) => ({
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            `data: {"id":"s1","choices":[{"delta":{"toolCalls":[{"index":0,"id":"${callId}","type":"function","function":{"name":"get_dashboard_summary","arguments":"{}"}}]}}]}\n\n`
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('data: [DONE]\n\n'),
        })
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    });

    // Each fetch returns a tool call (no text content),
    // so the loop runs MAX_TOOL_ROUNDS times then bails out.
    global.fetch = jest.fn().mockImplementation(() => {
      fetchCount++;
      return Promise.resolve({
        ok: true,
        body: { getReader: () => makeToolCallReader(`call-${fetchCount}`) },
      });
    });

    mockAxios.onGet('/dashboard/stats').reply(200, {
      code: 0,
      message: 'ok',
      data: {
        totalStations: 10,
        onlineStations: 8,
        offlineStations: 2,
        totalAlarms: 5,
        unhandledAlarms: 2,
        revenueSummary: { today: 5000, week: 35000, month: 150000, total: 2000000 },
      },
    });

    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: 'test', timestamp: Date.now() },
    ];

    const result = await chat(messages);

    // After 5 rounds of tool-only responses, chat() bails out
    expect(result.content).toContain('查询过于复杂');
  });
});