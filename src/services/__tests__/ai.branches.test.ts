/**
 * ai.ts 散分支补测 — F3683 覆盖盲区清零
 * 目标: ai.ts branch 89.58% → 100%
 * 未覆盖分支(基线全量coverage实采): 359(未知function default), 432(无user消息早退),
 * 470(流空行continue), 475(非chunk非done有效JSON行), 478(无效JSON行catch),
 * token缺席header展开, 非Error异常的 || 'Unknown error' fallback
 */

import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api from '../api';
import { executeToolCall, streamChatMessage } from '../ai';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);
const TEST_TOKEN = 'test-jwt-token-12345';

// =====================
// executeToolCall 散分支
// =====================

describe('executeToolCall 散分支补测', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(TEST_TOKEN);
  });

  it('未知function名应返回 Unknown function error', async () => {
    const result = await executeToolCall('nonexistent_function', {});
    expect(JSON.parse(result)).toEqual({
      error: 'Unknown function: nonexistent_function',
    });
  });

  it('非Error异常(无response无message)应fallback到 Unknown error', async () => {
    // axios reject 一个裸字符串 -> err.response undefined, err.message undefined
    mockAxios.onGet().reply(() => Promise.reject('boom'));
    const result = await executeToolCall('get_device_status', { device_id: 1 });
    expect(JSON.parse(result)).toEqual({
      error: 'Failed to execute get_device_status: Unknown error',
    });
  });
});

// =====================
// streamChatMessage 散分支
// =====================

describe('streamChatMessage 散分支补测', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('无user消息应早退且不发起fetch (432分支)', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(TEST_TOKEN);
    global.fetch = jest.fn();

    const messages = [
      { id: '1', role: 'assistant', content: '你好', timestamp: Date.now() },
      { id: '2', role: 'system', content: 'sys', timestamp: Date.now() },
    ];

    const chunks: string[] = [];
    for await (const chunk of streamChatMessage(messages as never)) {
      if (chunk.content) chunks.push(chunk.content);
    }

    expect(chunks).toEqual([]);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('流含空行/无效JSON行/非chunk行应跳过且不影响chunk解析 (470/475/478分支)', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(TEST_TOKEN);
    const mockReader = {
      read: jest
        .fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            '\n{"type":"chunk","content":"第一段"}\nnot-json-line\n{"type":"ping"}\n\n'
          ),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode(
            '{"type":"chunk","content":"第二段"}\n'
          ),
        })
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    };
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    });

    const messages = [
      { id: '1', role: 'user', content: '测试', timestamp: Date.now() },
    ];

    const chunks: string[] = [];
    for await (const chunk of streamChatMessage(messages as never)) {
      if (chunk.content) chunks.push(chunk.content);
    }

    expect(chunks).toEqual(['第一段', '第二段']);
    expect(mockReader.releaseLock).toHaveBeenCalled();
  });

  it('token缺席时header不应含Authorization (token分支)', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(null);
    const mockReader = {
      read: jest
        .fn()
        .mockResolvedValueOnce({ done: true }),
      releaseLock: jest.fn(),
    };
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    });

    const messages = [
      { id: '1', role: 'user', content: 'hi', timestamp: Date.now() },
    ];

    for await (const _ of streamChatMessage(messages as never)) {
      // 空流, 只验证fetch调用
    }

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const headers = (global.fetch as jest.Mock).mock.calls[0][1].headers;
    expect(headers.Authorization).toBeUndefined();
    expect(headers['Content-Type']).toBe('application/json');
  });
});
