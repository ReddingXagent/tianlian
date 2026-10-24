import { renderHook, act } from '@testing-library/react';
import { useWebSocket } from '../useWebSocket';

vi.mock('../../config/websocket', () => ({
  WS_CONFIG: {
    reconnectInterval: 3,
    maxReconnectAttempts: 5,
    heartbeatInterval: 30,
    connectionTimeout: 10,
  },
  WSMessage: {} as any,
  WSConnectionState: '' as any,
  WSChannelType: '' as any,
}));

let lastCreatedWsMock: any = null;
let constructorCount = 0;

function createWsMock(): any {
  return {
    readyState: 1,
    onopen: null as ((e?: Event) => void) | null,
    onmessage: null as ((e: { data: string }) => void) | null,
    onerror: null as ((e: Event) => void) | null,
    onclose: null as ((e: CloseEvent) => void) | null,
    send: vi.fn(),
    close: vi.fn(),
  };
}

const MockWebSocketClass = function MockWebSocket(this: any, url: string) {
  const instance = createWsMock();
  lastCreatedWsMock = instance;
  constructorCount++;
  return instance;
} as any;
MockWebSocketClass.OPEN = 1;
MockWebSocketClass.CONNECTING = 0;

beforeEach(() => {
  vi.useFakeTimers();
  lastCreatedWsMock = null;
  constructorCount = 0;
  (global as any).WebSocket = MockWebSocketClass;
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useWebSocket', () => {
  it('should initialize with disconnected state', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );
    expect(result.current.connectionState).toBe('disconnected');
    expect(result.current.isConnected).toBe(false);
    expect(result.current.lastMessage).toBeNull();
  });

  it('should auto-connect when autoConnect is true', () => {
    renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: true })
    );
    expect(lastCreatedWsMock).not.toBeNull();
  });

  it('should not auto-connect when autoConnect is false', () => {
    renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );
    expect(lastCreatedWsMock).toBeNull();
  });

  it('should update state when connected', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );

    act(() => { result.current.connect(); });
    expect(lastCreatedWsMock).not.toBeNull();
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });

    expect(result.current.connectionState).toBe('connected');
    expect(result.current.isConnected).toBe(true);
  });

  it('should handle incoming messages', () => {
    const onMessage = vi.fn();

    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false, onMessage })
    );

    act(() => { result.current.connect(); });
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });

    const testMessage = { type: 'data', channel: 'realtime' as const, payload: { value: 42 }, timestamp: '2026-05-25T14:00:00Z' };

    act(() => {
      if (lastCreatedWsMock.onmessage) lastCreatedWsMock.onmessage({ data: JSON.stringify(testMessage) });
    });

    expect(result.current.lastMessage).toEqual(testMessage);
    expect(onMessage).toHaveBeenCalledWith(testMessage);
  });

  it('should handle connection errors', () => {
    const onError = vi.fn();

    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false, onError })
    );

    act(() => { result.current.connect(); });
    act(() => { if (lastCreatedWsMock.onerror) lastCreatedWsMock.onerror(new Event('error')); });

    expect(result.current.connectionState).toBe('error');
    expect(onError).toHaveBeenCalled();
  });

  it('should handle disconnection', () => {
    const onClose = vi.fn();

    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false, onClose })
    );

    act(() => { result.current.connect(); });
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });
    act(() => {
      if (lastCreatedWsMock.onclose) lastCreatedWsMock.onclose({ code: 1000, reason: 'normal', wasClean: true } as CloseEvent);
    });

    expect(result.current.connectionState).toBe('disconnected');
    expect(result.current.isConnected).toBe(false);
    expect(onClose).toHaveBeenCalled();
  });

  it('should disconnect properly', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );

    act(() => { result.current.connect(); });
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });

    act(() => { result.current.disconnect(); });

    expect(lastCreatedWsMock.close).toHaveBeenCalled();
  });

  it('卡deddf61f: 内联 autoSubscribeChannels 下 rerender 多次不重建连接（构造次数=1）', async () => {
    const { rerender } = renderHook(() =>
      useWebSocket({
        endpoint: 'ws://localhost:8000/ws/v1/dashboard',
        autoConnect: true,
        autoSubscribeChannels: ['dashboard', 'alerts', 'devices'],
      })
    );
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });

    rerender();
    rerender();
    rerender();

    expect(constructorCount).toBe(1);
    expect(lastCreatedWsMock.close).not.toHaveBeenCalled();
  });

  it('卡deddf61f: WS 消息到达触发重渲染后连接不重建', () => {
    renderHook(() =>
      useWebSocket({
        endpoint: 'ws://localhost:8000/ws/v1/dashboard',
        autoConnect: true,
        autoSubscribeChannels: ['dashboard'],
      })
    );
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });

    const msg = { type: 'pong', channel: 'dashboard' as const, payload: null, timestamp: '2026-10-13T00:00:00Z' };
    act(() => {
      if (lastCreatedWsMock.onmessage) lastCreatedWsMock.onmessage({ data: JSON.stringify(msg) });
    });
    act(() => {
      if (lastCreatedWsMock.onmessage) lastCreatedWsMock.onmessage({ data: JSON.stringify(msg) });
    });

    expect(constructorCount).toBe(1);
    expect(lastCreatedWsMock.close).not.toHaveBeenCalled();
  });

  it('卡deddf61f: 重试耗尽后 connectionState=failed 且不再新建连接', () => {
    const onMaxReconnectAttempts = vi.fn();
    const { result } = renderHook(() =>
      useWebSocket({
        endpoint: 'ws://localhost:8000/ws/v1/dashboard',
        autoConnect: true,
        maxReconnectAttempts: 2,
        onMaxReconnectAttempts,
      })
    );
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });
    expect(constructorCount).toBe(1);

    const closeCurrent = () => act(() => {
      lastCreatedWsMock.readyState = 3; // CLOSED，模拟真实 close 语义
      if (lastCreatedWsMock.onclose) lastCreatedWsMock.onclose({ code: 1006, reason: 'abnormal', wasClean: false } as CloseEvent);
    });

    // 第1次close → 重连1次
    closeCurrent();
    act(() => { vi.advanceTimersByTime(3000); });
    expect(constructorCount).toBe(2);

    // 第2次close → 重连2次
    closeCurrent();
    act(() => { vi.advanceTimersByTime(3000); });
    expect(constructorCount).toBe(3);

    // 第3次close → 达到上限，终态 failed，不再新建
    closeCurrent();
    act(() => { vi.advanceTimersByTime(30000); });
    expect(constructorCount).toBe(3);
    expect(result.current.connectionState).toBe('failed');
    expect(onMaxReconnectAttempts).toHaveBeenCalledTimes(1);
  });

  it('卡deddf61f: CONNECTING 态重复 connect 不新建连接', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );
    // 模拟 mock 实例处于 CONNECTING
    act(() => { result.current.connect(); });
    lastCreatedWsMock.readyState = 0;

    act(() => { result.current.connect(); });
    act(() => { result.current.connect(); });

    expect(constructorCount).toBe(1);
  });

  it('卡deddf61f: onMessage 回调变化不产生陈旧闭包（经 ref 调用最新回调）', () => {
    const handler1 = vi.fn();
    const handler2 = vi.fn();
    const { rerender, result } = renderHook(({ h }) =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: true, onMessage: h }),
      { initialProps: { h: handler1 } }
    );
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });

    rerender({ h: handler2 });

    const msg = { type: 'data', channel: 'realtime' as const, payload: { v: 1 }, timestamp: '2026-10-13T00:00:00Z' };
    act(() => {
      if (lastCreatedWsMock.onmessage) lastCreatedWsMock.onmessage({ data: JSON.stringify(msg) });
    });

    expect(handler2).toHaveBeenCalledWith(msg);
    expect(handler1).not.toHaveBeenCalled();
    expect(result.current.lastMessage).toEqual(msg);
  });

  it('should expose connect/send/disconnect methods', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );

    expect(typeof result.current.connect).toBe('function');
    expect(typeof result.current.disconnect).toBe('function');
    expect(typeof result.current.send).toBe('function');
    expect(typeof result.current.subscribe).toBe('function');
    expect(typeof result.current.unsubscribe).toBe('function');
  });
});
