/**
 * useWebSocket hook 更全面的测试
 */
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

function createWsMock(): any {
  return {
    readyState: 1,
    onopen: null,
    onmessage: null,
    onerror: null,
    onclose: null,
    send: vi.fn(),
    close: vi.fn(),
  };
}

const MockWebSocketClass = function MockWebSocket(this: any, url: string) {
  const instance = createWsMock();
  lastCreatedWsMock = instance;
  return instance;
} as any;
MockWebSocketClass.OPEN = 1;
MockWebSocketClass.CONNECTING = 0;

beforeEach(() => {
  vi.useFakeTimers();
  lastCreatedWsMock = null;
  (global as any).WebSocket = MockWebSocketClass;
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useWebSocket extended', () => {
  it('should expose connect method', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );
    expect(typeof result.current.connect).toBe('function');
  });

  it('should expose disconnect method', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );
    expect(typeof result.current.disconnect).toBe('function');
  });

  it('should expose send method', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );
    expect(typeof result.current.send).toBe('function');
  });

  it('should expose subscribe method', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );
    expect(typeof result.current.subscribe).toBe('function');
  });

  it('should expose unsubscribe method', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );
    expect(typeof result.current.unsubscribe).toBe('function');
  });

  it('should update state when error occurs', () => {
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false, onError })
    );

    act(() => { result.current.connect(); });
    act(() => { if (lastCreatedWsMock.onerror) lastCreatedWsMock.onerror(new Event('error')); });

    expect(result.current.connectionState).toBe('error');
    expect(onError).toHaveBeenCalled();
  });

  it('should update state when disconnected', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );

    act(() => { result.current.connect(); });
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });

    act(() => {
      if (lastCreatedWsMock.onclose) {
        lastCreatedWsMock.onclose({ code: 1000, reason: 'normal', wasClean: true } as CloseEvent);
      }
    });

    expect(result.current.connectionState).toBe('disconnected');
    expect(result.current.isConnected).toBe(false);
  });

  it('should send message via send method', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );

    act(() => { result.current.connect(); });
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });

    act(() => {
      result.current.send({ type: 'test-message', data: 'hello' });
    });

    expect(lastCreatedWsMock.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'test-message', data: 'hello' })
    );
  });

  it('should subscribe to a channel', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );

    act(() => { result.current.connect(); });
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });

    act(() => {
      result.current.subscribe('alarm' as any, 123);
    });

    expect(lastCreatedWsMock.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'subscribe', channel: 'alarm', target_id: 123 })
    );
  });

  it('should unsubscribe from a channel', () => {
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false })
    );

    act(() => { result.current.connect(); });
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });

    act(() => {
      result.current.unsubscribe('alarm' as any, 123);
    });

    expect(lastCreatedWsMock.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'unsubscribe', channel: 'alarm', target_id: 123 })
    );
  });

  it('should handle messages with onMessage callback', () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() =>
      useWebSocket({ endpoint: 'ws://localhost:8000/ws/v1/dashboard', autoConnect: false, onMessage })
    );

    act(() => { result.current.connect(); });
    act(() => { if (lastCreatedWsMock.onopen) lastCreatedWsMock.onopen(); });

    const msg = { type: 'data', channel: 'realtime', payload: { temp: 25 } };
    act(() => {
      if (lastCreatedWsMock.onmessage) {
        lastCreatedWsMock.onmessage({ data: JSON.stringify(msg) });
      }
    });

    expect(result.current.lastMessage).toEqual(msg);
    expect(onMessage).toHaveBeenCalledWith(msg);
  });
});
